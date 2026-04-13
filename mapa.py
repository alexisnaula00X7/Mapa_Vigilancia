import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="LIMS - Dashboard Epidemiológico", layout="wide")

# Estilo CSS para que se vea más limpio (opcional)
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    div.block-container { padding-top: 2rem; }
    </style>
    """, unsafe_allow_name=True)

# --- 2. CONEXIÓN Y CARGA ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

@st.cache_data(ttl=600)
def cargar_todo():
    res = supabase.table("registro_resistencia").select("*").execute()
    df = pd.DataFrame(res.data)
    with open("ec-all.geo.json", "r", encoding="utf-8") as f:
        geojson = json.load(f)
    return df, geojson

df_raw, geojson_ecuador = cargar_todo()

# --- 3. BARRA SUPERIOR DE FILTROS (Estilo Dashboard) ---
st.title("📊 Vigilancia Epidemiológica de Resistencia")

# Creamos 3 columnas para los selectores principales
c1, c2, c3, c4 = st.columns([2, 2, 2, 1])

with c1:
    antibioticos = [
        'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 
        'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina', 
        'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina', 
        'nitrofurantoina', 'trimetoprim_sulfametoxazol'
    ]
    atb_sel = st.selectbox("💊 Antibiótico", antibioticos)

with c2:
    provincias = ["Todas"] + sorted(df_raw['provincia'].unique().tolist())
    prov_sel = st.selectbox("📍 Provincia", provincias)

with c3:
    # Filtro dinámico de cantones según la provincia elegida
    if prov_sel != "Todas":
        cantones = ["Todos"] + sorted(df_raw[df_raw['provincia'] == prov_sel]['canton'].unique().tolist())
    else:
        cantones = ["Todos"] + sorted(df_raw['canton'].unique().tolist())
    canton_sel = st.selectbox("🏙️ Cantón", cantones)

with c4:
    st.write("") # Espaciador
    if st.button("🔄 Actualizar"):
        st.cache_data.clear()
        st.rerun()

# --- 4. LÓGICA DE FILTRADO ---
df = df_raw.copy()

# Filtrar por Antibiótico (Solo los que tienen datos)
df = df[df[atb_sel].notnull()]

# Filtrar por Provincia
if prov_sel != "Todas":
    df = df[df['provincia'] == prov_sel]

# Filtrar por Cantón
if canton_sel != "Todos":
    df = df[df['canton'] == canton_sel]

# Definir casos resistentes para el conteo del mapa
df_res = df[df[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 5. INDICADORES RÁPIDOS (Cards) ---
m1, m2, m3, m4 = st.columns(4)
total_muestras = len(df)
total_res = len(df_res)
porcentaje = (total_res / total_muestras * 100) if total_muestras > 0 else 0

m1.metric("Muestras Totales", total_muestras)
m2.metric("Casos Resistentes (R)", total_res, delta_color="inverse")
m3.metric("% Resistencia", f"{porcentaje:.1f}%")
m4.metric("Microorganismo Top", df['microorganismo'].mode()[0] if not df.empty else "N/A")

st.divider()

# --- 6. MAPA Y TABLA ---
col_mapa, col_tabla = st.columns([2, 1])

with col_mapa:
    # Agrupamos por provincia para el mapa (usando .title() para tu archivo geojson)
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
        title=f"Distribución de Resistencia: {atb_sel}"
    )
    fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

with col_tabla:
    st.subheader("📋 Resumen de Datos")
    # Mostramos los microorganismos más frecuentes en la zona filtrada
    if not df.empty:
        resumen_micro = df_res['microorganismo'].value_counts().reset_index()
        st.dataframe(resumen_micro, use_container_width=True, hide_index=True)
    else:
        st.write("Sin datos para los filtros seleccionados.")

# --- 7. TABLA DETALLADA AL FINAL ---
with st.expander("🔍 Ver registros detallados"):
    st.dataframe(df, use_container_width=True)
