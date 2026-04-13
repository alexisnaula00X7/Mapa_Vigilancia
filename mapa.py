import streamlit as st
import pandas as pd
import plotly.express as px
import geopandas as gpd
import json
import os
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="LIMS - Dashboard Epidemiológico", layout="wide")

# --- 2. CONEXIÓN ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except:
        st.error("Error en credenciales.")
        return None

supabase = init_connection()

# --- 3. CARGA DE MAPAS (SHP con Fallback a JSON) ---
@st.cache_resource
def cargar_mapa_final():
    # Intento 1: Cargar el Shapefile oficial
    if os.path.exists("gadm41_ECU_1.shp"):
        try:
            # Usamos engine="fiona" para evitar el error de pyogrio
            gdf = gpd.read_file("nxprovincias.shp", engine="fiona")
            gdf = gdf.to_crs(epsg=4326)
            return gdf, "DPA_DESPRO" # Usualmente el SHP usa esta columna
        except Exception as e:
            st.warning(f"Error técnico con SHP, intentando GeoJSON... ({e})")
    
    # Intento 2: Si falla el SHP o no existe, usamos el GeoJSON
    if os.path.exists("ec-allgeo.json"):
        with open("ec-allgeo.json", "r", encoding="utf-8") as f:
            return json.load(f), "name"
    
    return None, None

@st.cache_data(ttl=600)
def cargar_datos_db():
    res = supabase.table("registro_resistencia").select("*").execute()
    return pd.DataFrame(res.data)

# Carga inicial
df_raw = cargar_datos_db()
mapa_data, llave_mapa = cargar_mapa_final()

# --- 4. INTERFAZ Y FILTROS ---
st.title("📊 Vigilancia Epidemiológica de Resistencia")

c1, c2, c3, c4 = st.columns([2, 2, 2, 1])

with c3:
    antibioticos = ['ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 'ceftriaxona', 'meropenem', 'ciprofloxacino']
    atb_sel = st.selectbox("💊 Antibiótico", antibioticos)

with c1:
    provincias = ["Todas"] + sorted(df_raw['provincia'].unique().tolist())
    prov_sel = st.selectbox("📍 Provincia", provincias)

with c2:
    if prov_sel != "Todas":
        df_p = df_raw[df_raw['provincia'] == prov_sel]
        cantones = ["Todos"] + sorted(df_p['canton'].unique().tolist())
    else:
        cantones = ["Todos"] + sorted(df_raw['canton'].unique().tolist())
    canton_sel = st.selectbox("🏙️ Cantón", cantones)

# --- 5. LÓGICA DE FILTRADO ---
df = df_raw.copy()
df = df[df[atb_sel].notnull()]

if prov_sel != "Todas":
    df = df[df['provincia'] == prov_sel]
if canton_sel != "Todos":
    df = df[df['canton'] == canton_sel]

# Solo casos Resistentes para el Mapa de Calor
df_res = df[df[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 6. VISUALIZACIÓN ---
m1, m2, m3 = st.columns(3)
m1.metric("Muestras", len(df))
m2.metric("Resistentes (R)", len(df_res))
m3.metric("% Resistencia", f"{(len(df_res)/len(df)*100 if len(df)>0 else 0):.1f}%")

st.divider()

if mapa_data is not None:
    # Agrupar para el mapa
    df_mapa = df_res.groupby('provincia').size().reset_index(name='conteo')
    
    # Normalización: SHP suele venir en MAYÚSCULAS
    df_mapa['provincia_id'] = df_mapa['provincia'].str.strip().str.upper()

    # Si es GeoPandas (SHP), usamos su interface, si no, el dict directo
    geojson_obj = mapa_data.__geo_interface__ if hasattr(mapa_data, '__geo_interface__') else mapa_data

    fig = px.choropleth_mapbox(
        df_mapa,
        geojson=geojson_obj,
        locations='provincia_id',
        featureidkey=f"properties.{llave_mapa}",
        color='conteo',
        color_continuous_scale="YlOrRd",
        mapbox_style="carto-positron",
        center={"lat": -1.8, "lon": -78.5},
        zoom=5.6,
        opacity=0.7
    )
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("No se pudo cargar ningún archivo de mapa (.shp o .json)")
