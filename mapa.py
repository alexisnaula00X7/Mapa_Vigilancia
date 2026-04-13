import streamlit as st
import pandas as pd
import plotly.express as px
import shapefile
from shapely.geometry import shape
import unicodedata
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="LIMS - Vigilancia RAM", layout="wide")

# Función para normalizar texto (Equivalente a Latin-ASCII en R)
def normalizar_texto(texto):
    if not texto: return ""
    texto = str(texto).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', texto)
                  if unicodedata.category(c) != 'Mn')

# --- 2. CARGA DE DATOS ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_data(ttl=600)
def cargar_db():
    supabase = init_connection()
    res = supabase.table("registro_resistencia").select("*").execute()
    df = pd.DataFrame(res.data)
    # Crear ID de provincia normalizado
    df['provincia_id'] = df['provincia'].apply(normalizar_texto)
    return df

@st.cache_resource
def cargar_mapa_shp():
    # Leemos el SHP y lo convertimos a GeoJSON para Plotly
    sf = shapefile.Reader("nxprovincias.shp")
    fields = [x[0] for x in sf.fields][1:]
    features = []
    for sr in sf.shapeRecords():
        atr = dict(zip(fields, sr.record))
        # Normalizamos el nombre de la provincia del mapa (columna DPA_DESPRO)
        atr['DPA_NORMALIZADO'] = normalizar_texto(atr.get('DPA_DESPRO', ''))
        geom = sr.shape.__geo_interface__
        features.append(dict(type="Feature", geometry=geom, properties=atr, id=atr['DPA_NORMALIZADO']))
    return {"type": "FeatureCollection", "features": features}

# --- 3. PROCESAMIENTO INICIAL ---
df_raw = cargar_db()
geojson_data = cargar_mapa_shp()

# Identificar columnas de antibióticos (asumiendo que son las que no son fijas)
cols_fijas = ["id", "created_at", "provincia", "canton", "microorganismo", "provincia_id"]
antibioticos = [c for c in df_raw.columns if c not in cols_fijas]

# --- 4. INTERFAZ (UI) ---
st.title("🧪 Vigilancia de Resistencia Antimicrobiana")

with st.sidebar:
    st.header("Filtros")
    prov_sel = st.selectbox("📍 Seleccionar Provincia", ["TODAS"] + sorted(df_raw['provincia'].unique().tolist()))
    micro_sel = st.selectbox("🦠 Microorganismo", sorted(df_raw['microorganismo'].unique().tolist()))
    atb_sel = st.selectbox("💊 Antibiótico para Mapa de Calor", antibioticos)

# Filtrado reactivo
df_filtrado = df_raw[df_raw['microorganismo'] == micro_sel]
if prov_sel != "TODAS":
    df_filtrado = df_filtrado[df_filtrado['provincia'] == prov_sel]

# --- 5. TABS (Como en tu Shiny) ---
tab1, tab2, tab3, tab4 = st.tabs(["Datos", "Gráfico de Barras", "Mapa de Calor", "Mapa de Aislamientos"])

with tab1:
    st.subheader("Registros Individuales")
    st.dataframe(df_filtrado, use_container_width=True)
    
    st.subheader("Solo Resistentes (R)")
    df_r = df_filtrado[df_filtrado[antibioticos].eq("R").any(axis=1)]
    st.dataframe(df_r, use_container_width=True)

with tab2:
    # Gráfico de barras (Número de resistencias)
    # Contamos cuántas "R" hay por cada columna de antibiótico
    conteo_r = df_filtrado[antibioticos].apply(lambda x: x.str.upper().eq('R').sum()).reset_index()
    conteo_r.columns = ['Antibiotico', 'Resistencias']
    conteo_r = conteo_r.sort_values('Resistencias', ascending=True)

    fig_bar = px.bar(conteo_r, x='Resistencias', y='Antibiotico', orientation='h',
                     color='Resistencias', color_continuous_scale='RdYlGn_r',
                     title=f"Número de Resistencias - {micro_sel}")
    st.plotly_chart(fig_bar, use_container_width=True)

with tab3:
    # Mapa de Calor (Basado en el antibiótico seleccionado en el sidebar)
    st.subheader(f"Distribución de Resistencia: {atb_sel}")
    
    # Agrupar por provincia para contar cuántos "R" hay
    df_mapa = df_filtrado[df_filtrado[atb_sel].str.upper() == 'R'].groupby('provincia_id').size().reset_index(name='n')
    
    fig_mapa = px.choropleth_mapbox(
        df_mapa,
        geojson=geojson_data,
        locations='provincia_id',
        featureidkey="id", # Usamos el ID normalizado que creamos en cargar_mapa_shp
        color='n',
        color_continuous_scale="YlOrRd",
        mapbox_style="carto-positron",
        center={"lat": -1.8, "lon": -78.5},
        zoom=5.5,
        opacity=0.7
    )
    fig_mapa.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig_mapa, use_container_width=True)

with tab4:
    # Mapa simple de aislamiento seleccionado
    st.subheader(f"Presencia de {micro_sel} por Provincia")
    df_aisla = df_filtrado.groupby('provincia_id').size().reset_index(name='cantidad')
    
    fig_aisla = px.choropleth_mapbox(
        df_aisla,
        geojson=geojson_data,
        locations='provincia_id',
        featureidkey="id",
        color='cantidad',
        color_continuous_scale="Blues",
        mapbox_style="carto-positron",
        center={"lat": -1.8, "lon": -78.5},
        zoom=5.5,
        opacity=0.7
    )
    fig_aisla.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig_aisla, use_container_width=True)
