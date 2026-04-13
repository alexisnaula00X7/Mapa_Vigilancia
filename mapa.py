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
    [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: bold; }
    [data-testid="stSidebar"] { background-color: #1e2630; color: white; }
    /* Estilo para las pestañas */
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px 4px 0px 0px; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #1e2630 !important; color: white !important; }
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
        return None

supabase = init_connection()

@st.cache_data(ttl=600)
def cargar_todo():
    res = supabase.table("registro_resistencia").select("*").execute()
    df = pd.DataFrame(res.data)
    ruta_geojson = "ec-allgeo.json" 
    geojson = None
    if os.path.exists(ruta_geojson):
        with open(ruta_geojson, "r", encoding="utf-8") as f:
            geojson = json.load(f)
    return df, geojson

df_raw, geojson_ecuador = cargar_todo()

# --- 3. CONFIGURACIÓN DE ANTIBIÓTICOS ---
antibioticos_base = [
    'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 
    'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina', 
    'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina', 
    'nitrofurantoina', 'trimetoprim_sulfametoxazol'
]

# --- 4. FILTROS (BARRA LATERAL IZQUIERDA) ---
with st.sidebar:
    st.header("🔍 Filtros")
    
    provincias = ["Todas"] + sorted(df_raw['provincia'].unique().tolist())
    prov_sel = st.selectbox("📍 Provincia", provincias)

    if prov_sel != "Todas":
        cantones_lista = ["Todos"] + sorted(df_raw[df_raw['provincia'] == prov_sel]['canton'].unique().tolist())
    else:
        cantones_lista = ["Todos"] + sorted(df_raw['canton'].unique().tolist())
    canton_sel = st.selectbox("🏙️ Cantón", cantones_lista)

    micro_list = sorted(df_raw['microorganismo'].unique().tolist())
    micro_sel = st.selectbox("🦠 Microorganismo", micro_list)

    atb_sel = st.selectbox("💊 Antibiótico (Mapa)", ["TODOS"] + antibioticos_base)
    
    st.markdown("---")
    if st.button("🔄 Actualizar Tablero", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 5. LÓGICA DE FILTRADO ---
df_f = df_raw[df_raw['microorganismo'] == micro_sel].copy()

if prov_sel != "Todas":
    df_f = df_f[df_f['provincia'] == prov_sel]
if canton_sel != "Todos":
    df_f = df_f[df_f['canton'] == canton_sel]

# Casos Resistentes (R) para Mapa y Tops
if atb_sel == "TODOS":
    mask_r = df_f[antibioticos_base].astype(str).apply(lambda x: x.str.upper()).eq('R').any(axis=1)
    df_res_mapa = df_f[mask_r].copy()
else:
    df_res_mapa = df_f[df_f[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 6. CUERPO PRINCIPAL ---
st.title("📊 Vigilancia Epidemiológica de Resistencia")

# KPIs principales (Siempre visibles)
m1, m2, m3, m4 = st.columns(4)
total_muestras = len(df_f)
total_res = len(df_res_mapa)
porc = (total_res / total_muestras * 100) if total_muestras > 0 else 0

m1.metric("Muestras Analizadas", total_muestras)
m2.metric("Casos Resistentes (R)", total_res)
m3.metric("% Resistencia", f"{porc:.1f}%")
m4.metric("Microorganismo", micro_sel)

st.divider()

# --- 7. DEFINICIÓN DE PESTAÑAS ---
tab1, tab2, tab3 = st.tabs(["📈 Gráfica de Resistencias", "🗺️ Mapa Geográfico", "📋 Reportes Detallados"])

# --- PESTAÑA 1: GRÁFICA DE BARRAS ---
with tab1:
    st.subheader(f"Perfil de Resistencia - {prov_sel} - {micro_sel}")
    
    conteo_data = []
    for atb in antibioticos_base:
        if atb in df_f.columns:
            n_r = (df_f[atb].astype(str).str.upper() == "R").sum()
            conteo_data.append({
                'antibiotico': atb.replace('_', ' ').title(), 
                'resistencias': int(n_r)
            })

    df_plot = pd.DataFrame(conteo_data).sort_values('resistencias', ascending=True)

    fig_res = px.bar(
        df_plot, x='resistencias', y='antibiotico', orientation='h',
        color='resistencias',
        color_continuous_scale=['#32CD32', '#FFD700', '#FF0000'],
        labels={'resistencias': 'Aislamientos Resistentes', 'antibiotico': 'Antibiótico'},
        text='resistencias'
    )
    fig_res.update_layout(plot_bgcolor='white', height=650, coloraxis_showscale=False)
    fig_res.update_traces(textposition='outside', marker_line_color='grey', marker_line_width=0.5)
    st.plotly_chart(fig_res, use_container_width=True)

# --- PESTAÑA 2: MAPA ---
with tab2:
    st.subheader(f"Distribución Geográfica de Resistencia: {atb_sel}")
    if geojson_ecuador:
        df_mapa = df_res_mapa.copy()
        df_mapa['provincia_id'] = df_mapa['provincia'].str.strip().str.title()
        conteo_prov = df_mapa.groupby('provincia_id').size().reset_index(name='conteo')

        fig_map = px.choropleth_mapbox(
            conteo_prov, geojson=geojson_ecuador, locations='provincia_id',
            featureidkey='properties.name', color='conteo',
            color_continuous_scale="YlOrRd", mapbox_style="carto-positron",
            center={"lat": -1.8, "lon": -78.5}, zoom=5.5, opacity=0.7
        )
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=600)
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.warning("GeoJSON no disponible.")

# --- PESTAÑA 3: TABLAS Y TOPS ---
with tab3:
    c_tab1, c_tab2 = st.columns(2)
    
    with c_tab1:
        st.subheader("🏙️ Top Cantones (R)")
        if not df_res_mapa.empty:
            res_c = df_res_mapa['canton'].value_counts().reset_index()
            res_c.columns = ['Cantón', 'Casos R']
            st.dataframe(res_c, use_container_width=True, hide_index=True, height=400)
        else:
            st.info("Sin datos.")

    with c_tab2:
        st.subheader("💊 Top Antibióticos (R)")
        if not df_plot.empty:
            top_atb = df_plot.sort_values('resistencias', ascending=False).copy()
            top_atb.columns = ['Antibiótico', 'Casos R']
            st.dataframe(top_atb, use_container_width=True, hide_index=True, height=400)
        else:
            st.info("Sin datos.")
