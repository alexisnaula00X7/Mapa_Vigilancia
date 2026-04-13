import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="LIMS - Dashboard Epidemiológico", layout="wide")

# CORRECCIÓN: Se cambió 'unsafe_allow_name' por 'unsafe_allow_html'
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    div.block-container { padding-top: 2rem; }
    /* Estilo para las métricas */
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXIÓN Y CARGA ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("Error en las credenciales de Supabase. Revisa los Secrets.")
        return None

supabase = init_connection()

@st.cache_data(ttl=600)
def cargar_todo():
    # Carga desde Supabase
    res = supabase.table("registro_resistencia").select("*").execute()
    df = pd.DataFrame(res.data)
    
    # Carga del GeoJSON local
    ruta_geojson = "ec-allgeo.json"
    if os.path.exists(ruta_geojson):
        with open(ruta_geojson, "r", encoding="utf-8") as f:
            geojson = json.load(f)
    else:
        st.error(f"No se encontró el archivo {ruta_geojson}")
        geojson = None
        
    return df, geojson

df_raw, geojson_ecuador = cargar_todo()

# --- 3. BARRA SUPERIOR DE FILTROS ---
st.title("📊 Vigilancia Epidemiológica de Resistencia")

if df_raw.empty:
    st.warning("La base de datos está vacía. Registra muestras para visualizar el dashboard.")
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

# Filtrar por Antibiótico (registros que tengan resultado)
df = df[df[atb_sel].notnull()]

# Filtros geográficos
if prov_sel != "Todas":
    df = df[df['provincia'] == prov_sel]
if canton_sel != "Todos":
    df = df[df['canton'] == canton_sel]

# Casos Resistentes
df_res = df[df[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 5. INDICADORES RÁPIDOS (Cards) ---
m1, m2, m3, m4 = st.columns(4)
total_muestras = len(df)
total_res = len(df_res)
porcentaje = (total_res / total_muestras * 100) if total_muestras > 0 else 0

m1.metric("Muestras Analizadas", total_muestras)
m2.metric("Casos Resistentes (R)", total_res)
m3.metric("% Resistencia", f"{porcentaje:.1f}%")

if not df_res.empty:
    top_micro = df_res['microorganismo'].mode()[0]
    m4.metric("Microorganismo Crítico", top_micro)
else:
    m4.metric("Microorganismo Crítico", "N/A")

st.divider()

# --- 6. MAPA Y TABLA ---
col_mapa, col_tabla = st.columns([2, 1])

with col_mapa:
    if not df_res.empty and geojson_ecuador:
        # Normalizar para el GeoJSON (Ej: PICHINCHA -> Pichincha)
        df_mapa = df_res.groupby('provincia').size().reset_index(name='conteo')
        df_mapa['provincia_id'] = df_mapa['provincia'].str.strip().str.title()

        fig = px.choropleth_mapbox(
            df_mapa,
            geojson=geojson_ecuador,
            locations='provincia_id',
            featureidkey='properties.name',
            color='conteo',
            color_continuous_scale="Reds",
            mapbox_style="carto-positron",
            center={"lat": -1.8, "lon": -78.5},
            zoom=5.5,
            opacity=0.7,
            title=f"Mapa de Calor: Resistencia a {atb_sel.replace('_', ' ').title()}"
        )
        fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos de resistencia (R) para mostrar en el mapa con los filtros actuales.")

with col_tabla:
    st.subheader("📋 Resumen Microbiano")
    if not df_res.empty:
        # Mostrar conteo de microorganismos resistentes
        resumen_micro = df_res['microorganismo'].value_counts().reset_index()
        resumen_micro.columns = ['Microorganismo', 'Casos R']
        st.dataframe(resumen_micro, use_container_width=True, hide_index=True)
    else:
        st.write("No se detectaron aislamientos resistentes.")

# --- 7. TABLA DETALLADA ---
with st.expander("🔍 Ver registros detallados del análisis"):
    st.dataframe(df, use_container_width=True)
