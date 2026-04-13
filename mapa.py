import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="LIMS - Dashboard Epidemiológico", layout="wide")

# Estilo para imitar el modo oscuro y las pestañas de tu referencia
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    div.block-container { padding-top: 2rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: bold; }
    [data-testid="stSidebar"] { background-color: #1e2630; }
    /* Estilo de las pestañas */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        white-space: pre-wrap;
        background-color: #262730;
        border-radius: 4px 4px 0px 0px;
        color: #afb1b6;
    }
    .stTabs [aria-selected="true"] {
        background-color: #373944 !important;
        color: #ffffff !important;
        border-bottom: 2px solid #ff4b4b;
    }
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
# Basado en los encabezados de tu imagen adjunta
antibioticos_base = [
    'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 
    'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina', 
    'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina', 
    'nitrofurantoina', 'trimetoprim_sulfametoxazol'
]

# --- 4. FILTROS (LADO IZQUIERDO) ---
with st.sidebar:
    st.header("🔍 Navegación")
    
    provincias = ["Todas"] + sorted(df_raw['provincia'].unique().tolist())
    prov_sel = st.selectbox("📍 Seleccionar Provincia", provincias)

    if prov_sel != "Todas":
        cantones_lista = ["Todos"] + sorted(df_raw[df_raw['provincia'] == prov_sel]['canton'].unique().tolist())
    else:
        cantones_lista = ["Todos"] + sorted(df_raw['canton'].unique().tolist())
    canton_sel = st.selectbox("🏙️ Seleccionar Cantón", cantones_lista)

    micro_list = sorted(df_raw['microorganismo'].unique().tolist())
    micro_sel = st.selectbox("🦠 Seleccionar Microorganismo", micro_list)

    atb_sel = st.selectbox("💊 Antibiótico para Mapa", ["TODOS"] + antibioticos_base)
    
    if st.button("🔄 Refrescar Datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 5. LÓGICA DE FILTRADO ---
df_f = df_raw[df_raw['microorganismo'] == micro_sel].copy()
if prov_sel != "Todas": df_f = df_f[df_f['provincia'] == prov_sel]
if canton_sel != "Todos": df_f = df_f[df_f['canton'] == canton_sel]

# Filtrado para casos R (Resistentes)
if atb_sel == "TODOS":
    mask_r = df_f[antibioticos_base].astype(str).apply(lambda x: x.str.upper()).eq('R').any(axis=1)
    df_res_filtrado = df_f[mask_r].copy()
else:
    df_res_filtrado = df_f[df_f[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 6. DISEÑO PRINCIPAL CON PESTAÑAS ---
st.title("📊 Vigilancia Epidemiológica de Resistencia")

# KPIs siempre visibles arriba
k1, k2, k3, k4 = st.columns(4)
total = len(df_f)
res_count = len(df_res_filtrado)
porcentaje = (res_count / total * 100) if total > 0 else 0

k1.metric("Muestras Analizadas", total)
k2.metric("Casos Resistentes (R)", res_count)
k3.metric("% Resistencia", f"{porcentaje:.1f}%")
k4.metric("Patógeno", micro_sel)

st.markdown("---")

# Creación de las pestañas solicitadas
tab_grafico, tab_mapa, tab_detalles = st.tabs(["📈 Gráfico", "🗺️ Mapa Provincia", "📋 Reportes Detallados"])

# --- CONTENIDO: PESTAÑA GRÁFICO ---
with tab_grafico:
    st.subheader(f"Número de resistencias - {prov_sel} - {micro_sel}")
    
    conteo_data = []
    for atb in antibioticos_base:
        if atb in df_f.columns:
            n_r = (df_f[atb].astype(str).str.upper() == "R").sum()
            conteo_data.append({'antibiotico': atb.replace('_', ' ').title(), 'resistencias': int(n_r)})

    df_plot = pd.DataFrame(conteo_data).sort_values('resistencias', ascending=True)

    fig_bar = px.bar(
        df_plot, x='resistencias', y='antibiotico', orientation='h',
        color='resistencias',
        color_continuous_scale=['#32CD32', '#FFD700', '#FF0000'], # Verde a Rojo
        text='resistencias',
        labels={'resistencias': 'Aislamientos Resistentes', 'antibiotico': 'Antibiótico'}
    )
    fig_bar.update_layout(height=600, plot_bgcolor='rgba(0,0,0,0)', coloraxis_showscale=False)
    fig_bar.update_traces(textposition='outside')
    st.plotly_chart(fig_bar, use_container_width=True)

# --- CONTENIDO: PESTAÑA MAPA ---
with tab_mapa:
    st.subheader(f"Mapa de Distribución: {atb_sel}")
    if geojson_ecuador:
        df_mapa = df_res_filtrado.copy()
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
        st.info("Cargue el archivo GeoJSON para visualizar el mapa.")

# --- CONTENIDO: PESTAÑA REPORTES DETALLADOS ---
with tab_detalles:
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        st.subheader("🦠 Top Microorganismos (R)")
        if not df_res_filtrado.empty:
            df_micro = df_res_filtrado['microorganismo'].value_counts().reset_index()
            df_micro.columns = ['Microorganismo', 'Casos R']
            st.dataframe(df_micro, use_container_width=True, hide_index=True)
        else:
            st.write("Sin datos disponibles.")

    with col_t2:
        st.subheader("💊 Top Antibióticos (R)")
        if not df_plot.empty:
            df_top_atb = df_plot.sort_values('resistencias', ascending=False)
            df_top_atb.columns = ['Antibiótico', 'Casos R']
            st.dataframe(df_top_atb, use_container_width=True, hide_index=True)
        else:
            st.write("Sin datos disponibles.")
            
    st.markdown("---")
    st.subheader("📋 Registros Crudos")
    st.dataframe(df_f, use_container_width=True)
