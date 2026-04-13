import streamlit as st
import pandas as pd
import plotly.express as px
import geopandas as gpd
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="LIMS - Dashboard Epidemiológico", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    div.block-container { padding-top: 2rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXIÓN Y CARGA DE DATOS ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        st.error("Error en las credenciales de Supabase.")
        return None

supabase = init_connection()

@st.cache_data(ttl=600)
def cargar_datos_db():
    res = supabase.table("registro_resistencia").select("*").execute()
    return pd.DataFrame(res.data)

@st.cache_resource
def cargar_mapa_oficial():
    # Cargamos el archivo .shp que subiste
    # GeoPandas lee automáticamente los archivos .dbf y .shx asociados
    gdf = gpd.read_file("nxprovincias.shp")
    
    # IMPORTANTE: Convertir a coordenadas geográficas (WGS84) para Plotly
    gdf = gdf.to_crs(epsg=4326)
    return gdf

df_raw = cargar_datos_db()
mapa_gdf = cargar_mapa_oficial()

# --- 3. BARRA SUPERIOR DE FILTROS ---
st.title("📊 Vigilancia Epidemiológica de Resistencia")

if df_raw.empty:
    st.warning("La base de datos está vacía.")
    st.stop()

c1, c2, c3, c4 = st.columns([2, 2, 2, 1])

with c3:
    antibioticos = [
        'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 
        'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina', 
        'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina', 
        'nitrofurantoina', 'trimetoprim_sulfametoxazol'
    ]
    atb_sel = st.selectbox("💊 Antibiótico", antibioticos)

with c1:
    provincias = ["Todas"] + sorted(df_raw['provincia'].unique().tolist())
    prov_sel = st.selectbox("📍 Provincia", provincias)

with c2:
    if prov_sel != "Todas":
        df_prov = df_raw[df_raw['provincia'] == prov_sel]
        cantones = ["Todos"] + sorted(df_prov['canton'].unique().tolist())
    else:
        cantones = ["Todos"] + sorted(df_raw['canton'].unique().tolist())
    canton_sel = st.selectbox("🏙️ Cantón", cantones)

with c4:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Actualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 4. LÓGICA DE FILTRADO ---
df = df_raw.copy()
df = df[df[atb_sel].notnull()]

if prov_sel != "Todas":
    df = df[df['provincia'] == prov_sel]
if canton_sel != "Todos":
    df = df[df['canton'] == canton_sel]

# Casos Resistentes para el Mapa
df_res = df[df[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 5. INDICADORES ---
m1, m2, m3, m4 = st.columns(4)
total_muestras = len(df)
total_res = len(df_res)
porcentaje = (total_res / total_muestras * 100) if total_muestras > 0 else 0

m1.metric("Muestras Analizadas", total_muestras)
m2.metric("Casos Resistentes (R)", total_res)
m3.metric("% Resistencia", f"{porcentaje:.1f}%")
m4.metric("Microorganismo Top", df_res['microorganismo'].mode()[0] if not df_res.empty else "N/A")

st.divider()

# --- 6. MAPA DE CALOR Y TABLA ---
col_mapa, col_tabla = st.columns([2, 1])

with col_mapa:
    # Agrupamos datos de la DB
    df_mapa = df_res.groupby('provincia').size().reset_index(name='conteo')
    
    # Normalización para el SHP:
    # En nxprovincias.shp, la columna suele llamarse 'DPA_DESPRO' o 'NAME_1'
    # Ajustamos tu columna 'provincia' para que coincida (usualmente MAYÚSCULAS)
    df_mapa['provincia_id'] = df_mapa['provincia'].str.strip().str.upper()

    fig = px.choropleth_mapbox(
        df_mapa,
        geojson=mapa_gdf.__geo_interface__,
        locations='provincia_id',
        featureidkey='properties.DPA_DESPRO', # ESTA ES LA LLAVE EN EL SHP OFICIAL
        color='conteo',
        color_continuous_scale="YlOrRd",
        mapbox_style="carto-positron",
        center={"lat": -1.8, "lon": -78.5},
        zoom=5.6,
        opacity=0.7,
        title=f"Mapa de Calor: Resistencia a {atb_sel.replace('_', ' ').title()}"
    )
    fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

with col_tabla:
    st.subheader("📋 Detalle Microbiano")
    if not df_res.empty:
        resumen = df_res['microorganismo'].value_counts().reset_index()
        resumen.columns = ['Microorganismo', 'Casos R']
        st.dataframe(resumen, use_container_width=True, hide_index=True)
    else:
        st.info("Sin casos resistentes.")

# --- 7. TABLA DETALLADA ---
with st.expander("🔍 Ver registros detallados"):
    st.dataframe(df, use_container_width=True)
