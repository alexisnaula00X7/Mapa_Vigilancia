import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Vigilancia Epidemiológica Ecuador", layout="wide")

# --- 2. CONEXIÓN A SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        st.error("No se encontraron las credenciales en st.secrets")
        return None

supabase = init_connection()

# --- 3. CARGA DE DATOS (DB Y GEOJSON LOCAL) ---
@st.cache_data(ttl=600)
def cargar_datos_desde_db():
    try:
        res = supabase.table("registro_resistencia").select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Error al conectar con la tabla: {e}")
        return pd.DataFrame()

@st.cache_resource
def cargar_geojson_ecuador():
    # Usamos el archivo que conseguiste y subiste
    archivo_ruta = "ec-all.geo.json"
    if os.path.exists(archivo_ruta):
        with open(archivo_ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        st.error(f"No se encontró el archivo {archivo_ruta} en la carpeta del proyecto.")
        return None

# --- 4. PROCESAMIENTO ---
st.title("🧪 Mapa Epidemiológico de Resistencia - Ecuador")

df = cargar_datos_desde_db()
geojson_ecuador = cargar_geojson_ecuador()

if df.empty:
    st.info("Esperando datos de la base de datos... Asegúrate de tener registros en la tabla.")
    st.stop()

if not geojson_ecuador:
    st.stop()

# Estandarización: El archivo ec-all suele usar nombres tipo "Pichincha" (Capitalized)
# Convertimos "PICHINCHA" de la DB a "Pichincha" para que coincida con el mapa
df['provincia_mapa'] = df['provincia'].str.strip().str.title()

# --- 5. FILTROS ---
with st.sidebar:
    st.header("Configuración")
    antibioticos = [
        'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 
        'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina', 
        'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina', 
        'nitrofurantoina', 'trimetoprim_sulfametoxazol'
    ]
    atb_sel = st.selectbox("Antibiótico:", antibioticos)
    ver_solo_resistentes = st.checkbox("Ver solo resistentes (R)", value=True)

# Lógica de filtrado
if ver_solo_resistentes:
    df_filtrado = df[df[atb_sel].astype(str).str.upper() == 'R'].copy()
    label_mapa = f"Resistencia a {atb_sel}"
else:
    df_filtrado = df[df[atb_sel].notnull()].copy()
    label_mapa = f"Análisis de {atb_sel}"

# Agrupación por provincia
df_conteo = df_filtrado.groupby('provincia_mapa').size().reset_index(name='conteo')

# --- 6. GENERACIÓN DEL MAPA ---
if not df_conteo.empty:
    fig = px.choropleth_mapbox(
        df_conteo,
        geojson=geojson_ecuador,
        locations='provincia_mapa',
        featureidkey='properties.name', # Esta es la llave estándar en archivos de Highcharts/Natural Earth
        color='conteo',
        color_continuous_scale="Reds",
        mapbox_style="carto-positron",
        center={"lat": -1.8312, "lon": -78.1834},
        zoom=5.5,
        opacity=0.6,
        labels={'conteo': 'Casos'},
        title=label_mapa
    )

    fig.update_layout(margin={"r":0,"t":50,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📍 Casos por Provincia")
        st.dataframe(df_conteo.sort_values(by='conteo', ascending=False), use_container_width=True)
    with col2:
        st.subheader("🦠 Microorganismos")
        if 'microorganismo' in df_filtrado.columns:
            st.write(df_filtrado['microorganismo'].value_counts())
else:
    st.warning(f"No hay datos de resistencia para {atb_sel} en las provincias registradas.")

# --- 7. BOTÓN DE ACTUALIZACIÓN ---
if st.sidebar.button("🔄 Refrescar"):
    st.cache_data.clear()
    st.rerun()
