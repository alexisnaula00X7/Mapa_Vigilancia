import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="LIMS - Dashboard Epidemiológico", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    div.block-container { padding-top: 2rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXIÓN Y CARGA ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        st.error("Error en las credenciales de Supabase. Revisa los Secrets.")
        return None

supabase = init_connection()

@st.cache_data(ttl=600)
def cargar_todo():
    res = supabase.table("registro_resistencia").select("*").execute()
    df = pd.DataFrame(res.data)
    
    ruta_geojson = "ec-allgeo.json" 
    if os.path.exists(ruta_geojson):
        with open(ruta_geojson, "r", encoding="utf-8") as f:
            geojson = json.load(f)
    else:
        geojson = None
        
    return df, geojson

df_raw, geojson_ecuador = cargar_todo()

# --- 3. CONFIGURACIÓN DE ANTIBIÓTICOS ---
antibioticos_base = [
    'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 
    'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina', 
    'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina', 
    'nitrofurantoina', 'trimetoprim_sulfametoxazol'
]

# --- 4. BARRA SUPERIOR DE FILTROS ---
st.title("📊 Vigilancia Epidemiológica de Resistencia")

if df_raw.empty:
    st.warning("La base de datos está vacía.")
    st.stop()

c1, c2, c3, c4 = st.columns([2, 2, 2, 1])

with c3:
    atb_sel = st.selectbox("💊 Antibiótico (Mapa)", ["TODOS"] + antibioticos_base)

with c1:
    provincias = ["Todas"] + sorted(df_raw['provincia'].unique().tolist())
    prov_sel = st.selectbox("📍 Provincia", provincias)

with c2:
    microorganismos = sorted(df_raw['microorganismo'].unique().tolist())
    micro_sel = st.selectbox("🦠 Microorganismo", microorganismos)

with c4:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Actualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 5. LÓGICA DE FILTRADO ---
df_f = df_raw[df_raw['microorganismo'] == micro_sel].copy()

if prov_sel != "Todas":
    df_f = df_f[df_f['provincia'] == prov_sel]

# Datos para el Mapa
if atb_sel == "TODOS":
    df_res_mapa = df_f[df_f[antibioticos_base].astype(str).apply(lambda x: x.str.upper()).eq('R').any(axis=1)].copy()
else:
    df_res_mapa = df_f[df_f[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 6. INDICADORES RÁPIDOS ---
m1, m2, m3 = st.columns(3)
total_muestras = len(df_f)
total_res = len(df_res_mapa)
porcentaje = (total_res / total_muestras * 100) if total_muestras > 0 else 0

m1.metric("Aislamientos Totales", total_muestras)
m2.metric("Casos Resistentes (Filtro)", total_res)
m3.metric("% Resistencia", f"{porcentaje:.1f}%")

st.divider()

# --- 7. GRÁFICA DE BARRAS (PERFIL DE RESISTENCIA) ---
st.subheader(f"📈 Perfil de Resistencia: {micro_sel}")

# Procesamos el conteo de "R" para cada antibiótico
conteo_atb = []
for atb in antibioticos_base:
    if atb in df_f.columns:
        # Contamos cuántos registros tienen "R" (ignorando mayúsculas/minúsculas)
        n_r = df_f[df_f[atb].astype(str).str.upper() == 'R'].shape[0]
        conteo_atb.append({
            'Antibiótico': atb.replace('_', ' ').title(),
            'Resistencias': n_r
        })

df_plot = pd.DataFrame(conteo_atb).sort_values('Resistencias', ascending=True)

if not df_plot.empty and df_plot['Resistencias'].sum() > 0:
    fig_barras = px.bar(
        df_plot,
        x='Resistencias',
        y='Antibiótico',
        orientation='h',
        color='Resistencias',
        color_continuous_scale='Reds',
        text='Resistencias',
        labels={'Resistencias': 'Número de casos R'}
    )
    fig_barras.update_layout(height=500, margin=dict(l=20, r=20, t=30, b=20))
    st.plotly_chart(fig_barras, use_container_width=True)
else:
    st.info(f"No se detectaron resistencias para {micro_sel} con los filtros actuales.")

st.divider()

# --- 8. MAPA Y TABLA ---
col_mapa, col_tabla = st.columns([2, 1])

with col_mapa:
    if geojson_ecuador:
        df_mapa = df_res_mapa.copy()
        df_mapa['provincia_id'] = df_mapa['provincia'].str.strip().str.title()
        conteo_prov = df_mapa.groupby('provincia_id').size().reset_index(name='conteo')

        fig_map = px.choropleth_mapbox(
            conteo_prov,
            geojson=geojson_ecuador,
            locations='provincia_id',
            featureidkey='properties.name', 
            color='conteo',
            color_continuous_scale="YlOrRd", 
            mapbox_style="carto-positron",
            center={"lat": -1.8, "lon": -78.5},
            zoom=5.5,
            opacity=0.7,
            title=f"Distribución Geográfica: {atb_sel}"
        )
        fig_map.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.error("Error al cargar el mapa.")

with col_tabla:
    st.subheader("📋 Detalle por Cantón (R)")
    if not df_res_mapa.empty:
        resumen_canton = df_res_mapa['canton'].value_counts().reset_index()
        resumen_canton.columns = ['Cantón', 'Casos R']
        st.dataframe(resumen_canton, use_container_width=True, hide_index=True)
    else:
        st.info("Sin registros coincidentes.")
