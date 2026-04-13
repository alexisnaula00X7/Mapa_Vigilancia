import streamlit as st
import pandas as pd
import plotly.express as px
import shapefile
import unicodedata
import os
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="LIMS - Vigilancia RAM", layout="wide")

# Función para normalizar texto (Equivalente a Latin-ASCII en R)
def normalizar_texto(texto):
    if not texto: return ""
    texto = str(texto).upper().strip()
    # Elimina tildes y eñes
    return ''.join(c for c in unicodedata.normalize('NFD', texto)
                  if unicodedata.category(c) != 'Mn')

# --- 2. CONEXIÓN Y CARGA ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_data(ttl=600)
def cargar_datos():
    supabase = init_connection()
    res = supabase.table("registro_resistencia").select("*").execute()
    df = pd.DataFrame(res.data)
    # Creamos el ID normalizado igual que hacías en R
    df['provincia_id'] = df['provincia'].apply(normalizar_texto)
    return df

@st.cache_resource
def cargar_mapa_shp():
    # Nombre base que me indicaste
    base_name = "gadm41_ECU_1"
    
    if not os.path.exists(f"{base_name}.shp"):
        st.error(f"No se encontró el archivo {base_name}.shp. Verifica las mayúsculas en GitHub.")
        return None

    try:
        sf = shapefile.Reader(base_name)
        fields = [x[0] for x in sf.fields][1:]
        features = []
        for sr in sf.shapeRecords():
            atr = dict(zip(fields, sr.record))
            
            # En GADM la columna es NAME_1
            nombre_prov = atr.get('NAME_1') or str(list(atr.values())[0])
            
            # Creamos el ID para el cruce (Join)
            atr['ID_NORMALIZADO'] = normalizar_texto(nombre_prov)
            
            geom = sr.shape.__geo_interface__
            features.append(dict(
                type="Feature", 
                geometry=geom, 
                properties=atr, 
                id=atr['ID_NORMALIZADO']
            ))
        return {"type": "FeatureCollection", "features": features}
    except Exception as e:
        st.error(f"Error al leer el Shapefile: {e}")
        return None

# --- 3. LÓGICA PRINCIPAL ---
df_raw = cargar_datos()
geojson_data = cargar_mapa_shp()

# Identificar antibióticos
cols_fijas = ["id", "created_at", "provincia", "canton", "microorganismo", "provincia_id"]
antibioticos = [c for c in df_raw.columns if c not in cols_fijas]

st.title("📊 Vigilancia Epidemiológica RAM (Ecuador)")

# Filtros
with st.sidebar:
    st.header("Filtros")
    micro_sel = st.selectbox("🦠 Microorganismo", sorted(df_raw['microorganismo'].unique().tolist()))
    atb_sel = st.selectbox("💊 Antibiótico (Mapa de Calor)", antibioticos)

# Filtrado
df_filtrado = df_raw[df_raw['microorganismo'] == micro_sel]

# --- 4. VISUALIZACIÓN ---
tab1, tab2 = st.tabs(["📈 Análisis de Resistencia", "🗺️ Mapa de Calor"])

with tab1:
    # Gráfico de barras horizontal (Igual que tu RStudio)
    conteo_r = df_filtrado[antibioticos].apply(lambda x: x.str.upper().eq('R').sum()).reset_index()
    conteo_r.columns = ['Antibiotico', 'Resistencias']
    conteo_r = conteo_r.sort_values('Resistencias', ascending=True)

    fig_bar = px.bar(conteo_r, x='Resistencias', y='Antibiotico', orientation='h',
                     color='Resistencias', color_continuous_scale='RdYlGn_r',
                     title=f"Número de Resistencias detectadas para {micro_sel}")
    st.plotly_chart(fig_bar, use_container_width=True)

with tab2:
    if geojson_data:
        # Contamos cuántos "R" hay por provincia para el ATB seleccionado
        df_mapa = df_filtrado[df_filtrado[atb_sel].str.upper() == 'R'].groupby('provincia_id').size().reset_index(name='n')
        
        fig_map = px.choropleth_mapbox(
            df_mapa,
            geojson=geojson_data,
            locations='provincia_id',
            featureidkey="id",
            color='n',
            color_continuous_scale="YlOrRd",
            mapbox_style="carto-positron",
            center={"lat": -1.8, "lon": -78.5},
            zoom=5.5,
            opacity=0.7,
            title=f"Casos Resistentes a {atb_sel.upper()} por Provincia"
        )
        fig_map.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.warning("Archivos cartográficos no encontrados o corruptos.")
