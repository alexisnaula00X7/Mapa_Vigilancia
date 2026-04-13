import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import json

# --- 1. CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Mapa Coroplético de Muestras", layout="wide")
st.title("🗺️ Distribución Geográfica de Muestras Tomadas")

# --- 2. CARGA DE DATOS (MUESTRAS) ---
@st.cache_data(ttl=600)  # Caché de 10 min
def cargar_datos_muestras():
    """
    IMPORTANTE: Reemplaza esto con tu consulta real a Supabase.
    Si usas el script anterior, sería:
    # res = supabase.table("registro_resistencia").select("id, provincia, canton").execute()
    # return pd.DataFrame(res.data)
    """
    # DATOS DE PRUEBA (Borrar cuando conectes Supabase)
    data = {
        'id': range(1, 101),
        'provincia': ['PICHINCHA']*40 + ['GUAYAS']*25 + ['MANABI']*15 + ['AZUAY']*10 + ['ESMERALDAS']*5 + ['LOJA']*3 + ['ORELLANA']*2,
        'canton': ['QUITO']*30 + ['MEJIA']*10 + ['GUAYAQUIL']*20 + ['SAMBORONDON']*5 + ['MANTA']*10 + ['CUENCA']*10 + ['ESMERALDAS']*5 + ['LOJA']*3 + ['ORELLANA']*2
    }
    return pd.DataFrame(data)

# --- 3. CARGA DEL MAPA (GEOJSON) ---
@st.cache_resource
def cargar_geojson_provincias():
    """
    Descarga un GeoJSON oficial de las provincias de Ecuador.
    Fuente: https://github.com/andres-torres/ecuador-geojson
    """
    url = "https://raw.githubusercontent.com/andres-torres/ecuador-geojson/master/provincias.geojson"
    try:
        response = requests.get(url)
        geojson = response.json()
        return geojson
    except Exception as e:
        st.error(f"Error al descargar el GeoJSON: {e}")
        return None

# --- 4. EJECUCIÓN Y PROCESAMIENTO ---
df_muestras = cargar_datos_muestras()
geojson_ecuador = cargar_geojson_provincias()

# Verificación de datos cargados
if df_muestras.empty or not geojson_ecuador:
    st.warning("No se pudieron cargar los datos o el mapa. Revisa las conexiones.")
    st.stop()

# Limpieza de datos (Clave para que coincidan con el mapa)
# Convertimos a mayúsculas y quitamos espacios para estandarizar
df_muestras['provincia_id'] = df_muestras['provincia'].str.upper().str.strip()

# --- 5. LÓGICA DEL MAPA ---
st.sidebar.header("Filtros")

# Contar muestras por provincia
df_conteo = df_muestras.groupby('provincia_id').size().reset_index(name='Total_Muestras')

# Definir la paleta de colores (ej: Reds, Blues, Viridis)
paleta_color = st.sidebar.selectbox("Selecciona Paleta de Color", ["Reds", "Blues", "Viridis"], index=0)

# --- 6. CREACIÓN DEL MAPA CON PLOTLY CHOROPLETH ---
# 'featureidkey' debe coincidir con la propiedad que identifica la provincia en el GeoJSON
# En el GeoJSON descargado, la propiedad es 'DPA_PROVIN' (código) o 'PROVINCIA' (nombre)
# Para usar nombres, configuramos featureidkey='properties.PROVINCIA'

fig_mapa = px.choropleth_mapbox(
    df_conteo, 
    geojson=geojson_ecuador, 
    locations='provincia_id',         # Columna en df con el ID
    featureidkey='properties.PROVINCIA', # Propiedad en el GeoJSON con el ID
    color='Total_Muestras',          # Columna que define el color
    color_continuous_scale=paleta_color, # Escala de color
    mapbox_style="carto-positron",   # Estilo del mapa base (limpio)
    center={"lat": -1.8, "lon": -78.2}, # Centro de Ecuador
    zoom=5.8,                         # Nivel de zoom inicial
    opacity=0.7,                     # Transparencia de los colores
    labels={'Total_Muestras': 'Muestras'},
    title=f"Muestras totales registradas por Provincia (Total: {len(df_muestras)})"
)

# Ajustes de diseño
fig_mapa.update_layout(
    margin={"r":0,"t":40,"l":0,"b":0},
    coloraxis_colorbar_title_side="top"
)

# --- 7. VISUALIZACIÓN ---
tab1, tab2 = st.tabs(["🗺️ Mapa de Intensidad", "📊 Datos Numéricos"])

with tab1:
    st.plotly_chart(fig_mapa, use_container_width=True)

with tab2:
    st.subheader("Registros por Provincia")
    st.dataframe(df_conteo.sort_values(by='Total_Muestras', ascending=False), use_container_width=True)

# Botón para refrescar caché
if st.button("🔄 Actualizar Datos"):
    st.cache_data.clear()
    st.rerun()
