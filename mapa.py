import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="LIMS - Dashboard Epidemiológico", layout="wide")

# CSS para imitar el estilo de tu imagen (letras blancas/naranjas y subrayado rojo)
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div.block-container { padding-top: 1rem; }
    
    /* Estilo de las pestañas (Tabs) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 20px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        background-color: transparent;
        border: none;
        color: #ffffff;
        font-family: sans-serif;
        font-weight: 400;
    }
    .stTabs [aria-selected="true"] {
        color: #ff4b4b !important; /* Color de texto activo */
        border-bottom: 2px solid #ff4b4b !important; /* Línea roja inferior */
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
antibioticos_base = [
    'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 
    'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina', 
    'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina', 
    'nitrofurantoina', 'trimetoprim_sulfametoxazol'
]

# --- 4. TÍTULO Y PESTAÑAS (COMO EN TU IMAGEN) ---
st.title("🧪 Vigilancia Epidemiológica de Resistencia")

# Definición de pestañas con iconos
tab_ingresos, tab_procesados, tab_resumen, tab_avanzado = st.tabs([
    "📥 Ingresos", 
    "⚙️ Procesados", 
    "📊 Resumen General", 
    "📈 Análisis Avanzado"
])

# --- 5. FILTROS (MANTENEMOS EN SIDEBAR PARA LIMPIEZA) ---
with st.sidebar:
    st.header("Filtros")
    prov_sel = st.selectbox("📍 Provincia", ["Todas"] + sorted(df_raw['provincia'].unique().tolist()))
    
    if prov_sel != "Todas":
        cantones = ["Todos"] + sorted(df_raw[df_raw['provincia'] == prov_sel]['canton'].unique().tolist())
    else:
        cantones = ["Todos"] + sorted(df_raw['canton'].unique().tolist())
    canton_sel = st.selectbox("🏙️ Cantón", cantones)
    
    micro_sel = st.selectbox("🦠 Microorganismo", sorted(df_raw['microorganismo'].unique().tolist()))
    atb_sel = st.selectbox("💊 Antibiótico (Mapa)", ["TODOS"] + antibioticos_base)

# Lógica de datos filtrados
df_f = df_raw[df_raw['microorganismo'] == micro_sel].copy()
if prov_sel != "Todas": df_f = df_f[df_f['provincia'] == prov_sel]
if canton_sel != "Todos": df_f = df_f[df_f['canton'] == canton_sel]

mask_r = df_f[antibioticos_base].astype(str).apply(lambda x: x.str.upper()).eq('R').any(axis=1)
df_res = df_f[mask_r].copy()

# --- 6. CONTENIDO DE LAS PESTAÑAS ---

with tab_ingresos:
    st.subheader("Datos de Ingreso de Muestras")
    st.dataframe(df_f, use_container_width=True)

with tab_procesados:
    st.subheader("Estado de Procesamiento")
    # Aquí puedes poner tablas de eficiencia o estados
    st.info("Sección configurada para mostrar tiempos de respuesta y estados de laboratorio.")

with tab_resumen:
    # KPIs Rápidos
    c1, c2, c3 = st.columns(3)
    c1.metric("Muestras Total", len(df_f))
    c2.metric("Casos Resistentes", len(df_res))
    c3.metric("% Resistencia", f"{(len(df_res)/len(df_f)*100):.1f}%" if len(df_f)>0 else "0%")
    
    st.divider()
    
    col_map, col_top = st.columns([2, 1])
    with col_map:
        if geojson_ecuador:
            df_mapa = df_res.copy()
            df_mapa['provincia_id'] = df_mapa['provincia'].str.strip().str.title()
            conteo = df_mapa.groupby('provincia_id').size().reset_index(name='n')
            fig = px.choropleth_mapbox(conteo, geojson=geojson_ecuador, locations='provincia_id',
                                      featureidkey='properties.name', color='n',
                                      mapbox_style="carto-positron", center={"lat": -1.8, "lon": -78.5},
                                      zoom=5, color_continuous_scale="Reds")
            fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig, use_container_width=True)
            
    with col_top:
        st.subheader("📋 Top Microorganismos (R)")
        if not df_res.empty:
            st.dataframe(df_res['microorganismo'].value_counts(), use_container_width=True)
        else:
            st.write("Sin casos resistentes.")

with tab_avanzado:
    st.subheader(f"Perfil de Resistencia: {micro_sel}")
    
    conteo_data = []
    for atb in antibioticos_base:
        if atb in df_f.columns:
            n_r = (df_f[atb].astype(str).str.upper() == "R").sum()
            conteo_data.append({'antibiotico': atb.replace('_', ' ').title(), 'resistencias': int(n_r)})
    
    df_plot = pd.DataFrame(conteo_data).sort_values('resistencias', ascending=True)
    
    fig_bar = px.bar(df_plot, x='resistencias', y='antibiotico', orientation='h',
                     color='resistencias', color_continuous_scale=['#32CD32', '#FFD700', '#FF0000'],
                     text='resistencias')
    fig_bar.update_layout(plot_bgcolor='rgba(0,0,0,0)', height=600, coloraxis_showscale=False)
    st.plotly_chart(fig_bar, use_container_width=True)
