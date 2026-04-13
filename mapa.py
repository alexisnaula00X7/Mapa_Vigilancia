import streamlit as st
import pandas as pd
import plotly.express as px
import requests
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
    except Exception as e:
        st.error("No se encontraron las credenciales en st.secrets")
        return None

supabase = init_connection()

# --- 3. CARGA DE DATOS (MUESTRAS Y GEOJSON) ---
@st.cache_data(ttl=600)
def cargar_datos_desde_db():
    try:
        # Consultamos la tabla (asegúrate que el nombre coincida: registro_resistencia)
        res = supabase.table("registro_resistencia").select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Error al conectar con la tabla: {e}")
        return pd.DataFrame()

@st.cache_resource
def cargar_geojson_ecuador():
    # GeoJSON oficial de provincias de Ecuador
    url = "https://raw.githubusercontent.com/andres-torres/ecuador-geojson/master/provincias.geojson"
    return requests.get(url).json()

# --- 4. PROCESAMIENTO ---
st.title("🧪 Mapa Epidemiológico de Resistencia - Ecuador")

df = cargar_datos_desde_db()
geojson_ecuador = cargar_geojson_ecuador()

if df.empty:
    st.info("Esperando datos de la base de datos... Asegúrate de tener registros en la tabla 'registro_resistencia'.")
    st.stop()

# Estandarización de nombres para que coincidan con el mapa
df['provincia_mapa'] = df['provincia'].str.upper().str.strip()

# --- 5. FILTROS Y LÓGICA DE RESISTENCIA ---
with st.sidebar:
    st.header("Configuración del Mapa")
    
    # Lista de antibióticos según tu imagen
    antibioticos = [
        'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 
        'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina', 
        'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina', 
        'nitrofurantoina', 'trimetoprim_sulfametoxazol'
    ]
    
    atb_sel = st.selectbox("Selecciona Antibiótico para analizar:", antibioticos)
    ver_solo_resistentes = st.checkbox("Ver solo casos resistentes (R)", value=True)

# Filtrado dinámico
if ver_solo_resistentes:
    # Filtramos donde el resultado sea 'R'
    df_filtrado = df[df[atb_sel].str.upper() == 'R'].copy()
    label_mapa = f"Casos Resistentes a {atb_sel}"
else:
    # Contamos todas las muestras que tienen algún resultado en ese antibiótico
    df_filtrado = df[df[atb_sel].notnull()].copy()
    label_mapa = f"Muestras Analizadas para {atb_sel}"

# Agrupación por provincia para el color
df_conteo = df_filtrado.groupby('provincia_mapa').size().reset_index(name='conteo')

# --- 6. GENERACIÓN DEL MAPA ---
if not df_conteo.empty:
    fig = px.choropleth_mapbox(
        df_conteo,
        geojson=geojson_ecuador,
        locations='provincia_mapa',
        featureidkey='properties.PROVINCIA', # Campo clave en el GeoJSON
        color='conteo',
        color_continuous_scale="Reds",
        mapbox_style="carto-positron",
        center={"lat": -1.8, "lon": -78.2},
        zoom=5.5,
        opacity=0.6,
        labels={'conteo': 'Cantidad'},
        title=f"Distribución Geográfica: {label_mapa}"
    )

    fig.update_layout(margin={"r":0,"t":50,"l":0,"b":0})
    
    # Mostrar Mapa
    st.plotly_chart(fig, use_container_width=True)
    
    # Mostrar tabla de focos calientes
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📍 Desglose por Provincia")
        st.dataframe(df_conteo.sort_values(by='conteo', ascending=False), use_container_width=True)
    with col2:
        st.subheader("🦠 Microorganismos detectados")
        st.write(df_filtrado['microorganismo'].value_counts())
else:
    st.warning(f"No se encontraron datos que coincidan con los filtros para {atb_sel}.")

# --- 7. BOTÓN DE ACTUALIZACIÓN ---
if st.sidebar.button("🔄 Refrescar Base de Datos"):
    st.cache_data.clear()
    st.rerun()
