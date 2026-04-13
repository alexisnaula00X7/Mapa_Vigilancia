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
        return None

supabase = init_connection()

@st.cache_data(ttl=600)
def cargar_todo():
    # Carga de datos desde Supabase
    res = supabase.table("registro_resistencia").select("*").execute()
    df = pd.DataFrame(res.data)
    
    # Carga de GeoJSON para el mapa
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

# --- 4. FILTROS ---
st.title("📊 Vigilancia Epidemiológica de Resistencia")

c1, c2, c3, c4 = st.columns([2, 2, 2, 1])

with c1:
    provincias = ["Todas"] + sorted(df_raw['provincia'].unique().tolist())
    prov_sel = st.selectbox("📍 Provincia", provincias)

with c2:
    # Filtro dinámico de Cantones según Provincia
    if prov_sel != "Todas":
        cantones_lista = ["Todos"] + sorted(df_raw[df_raw['provincia'] == prov_sel]['canton'].unique().tolist())
    else:
        cantones_lista = ["Todos"] + sorted(df_raw['canton'].unique().tolist())
    canton_sel = st.selectbox("🏙️ Cantón", cantones_lista)

with c3:
    micro_list = sorted(df_raw['microorganismo'].unique().tolist())
    micro_sel = st.selectbox("🦠 Microorganismo", micro_list)

with c4:
    atb_sel = st.selectbox("💊 Antibiótico (Mapa)", ["TODOS"] + antibioticos_base)
    if st.button("🔄 Actualizar Datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 5. LÓGICA DE FILTRADO ---
# A. Filtro para Perfil Global (Solo Microorganismo)
df_micro = df_raw[df_raw['microorganismo'] == micro_sel].copy()

# B. Filtro para KPIs, Mapa y Gráfica Local (Micro + Ubicación)
df_f = df_micro.copy()
if prov_sel != "Todas":
    df_f = df_f[df_f['provincia'] == prov_sel]
if canton_sel != "Todos":
    df_f = df_f[df_f['canton'] == canton_sel]

# C. Identificación de Casos Resistentes (R) para el Mapa
if atb_sel == "TODOS":
    mask_r = df_f[antibioticos_base].astype(str).apply(lambda x: x.str.upper()).eq('R').any(axis=1)
    df_res_mapa = df_f[mask_r].copy()
else:
    df_res_mapa = df_f[df_f[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 6. INDICADORES (KPIs) ---
m1, m2, m3, m4 = st.columns(4)
m1.metric("Muestras Analizadas", len(df_f))
m2.metric("Casos Resistentes (Filtro)", len(df_res_mapa))
porc = (len(df_res_mapa)/len(df_f)*100) if len(df_f)>0 else 0
m3.metric("% Resistencia Local", f"{porc:.1f}%")
m4.metric("Microorganismo", micro_sel)

st.divider()

# --- 7. GRÁFICA DE BARRAS DINÁMICA (ESTILO PERSONALIZADO) ---
st.subheader(f"Número de resistencias - {prov_sel}/{canton_sel} - {micro_sel}")

conteo_local = []
for atb in antibioticos_base:
    if atb in df_f.columns:
        n_res = df_f[df_f[atb].astype(str).str.upper() == 'R'].shape[0]
        conteo_local.append({'Antibiótico': atb.replace('_', ' ').title(), 'Resistencias': n_res})

df_grafico_local = pd.DataFrame(conteo_local)

if not df_grafico_local.empty and df_grafico_local['Resistencias'].sum() > 0:
    fig_bar_local = px.bar(
        df_grafico_local,
        x='Resistencias',
        y='Antibiótico',
        orientation='h',
        color='Resistencias',
        # Escala: Verde (Bajo) -> Amarillo -> Rojo (Alto)
        color_continuous_scale=['#32CD32', '#FFD700', '#FF0000'], 
        text='Resistencias',
        category_orders={"Antibiótico": df_grafico_local.sort_values('Resistencias')['Antibiótico'].tolist()}
    )
    fig_bar_local.update_layout(
        plot_bgcolor='white',
        xaxis=dict(showgrid=True, gridcolor='lightgrey'),
        yaxis=dict(title="Antibiótico", showgrid=False),
        height=500,
        margin=dict(l=20, r=20, t=30, b=20)
    )
    fig_bar_local.update_traces(textposition='outside', marker_line_color='grey', marker_line_width=0.5)
    st.plotly_chart(fig_bar_local, use_container_width=True)
else:
    st.info("No hay datos de resistencia suficientes en esta ubicación para generar la gráfica local.")

st.divider()

# --- 8. MAPA Y TABLA DETALLADA ---
col_mapa, col_tabla = st.columns([2, 1])

with col_mapa:
    st.subheader(f"📍 Distribución Geográfica: {atb_sel}")
    if geojson_ecuador:
        df_mapa = df_res_mapa.copy()
        df_mapa['provincia_id'] = df_mapa['provincia'].str.strip().str.title()
        conteo_prov = df_mapa.groupby('provincia_id').size().reset_index(name='conteo')

        fig_map = px.choropleth_mapbox(
            conteo_prov, geojson=geojson_ecuador, locations='provincia_id',
            featureidkey='properties.name', color='conteo',
            color_continuous_scale="YlOrRd", mapbox_style="carto-positron",
            center={"lat": -1.8, "lon": -78.5}, zoom=5.2, opacity=0.7
        )
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500)
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.error("Archivo GeoJSON no encontrado. El mapa no puede mostrarse.")

with col_tabla:
    st.subheader("📋 Resumen por Cantón")
    if not df_res_mapa.empty:
        res_c = df_res_mapa['canton'].value_counts().reset_index()
        res_c.columns = ['Cantón', 'Casos R']
        st.dataframe(res_c, use_container_width=True, hide_index=True, height=450)
    else:
        st.info("Sin casos resistentes registrados en los filtros seleccionados.")

# --- 9. PERFIL GLOBAL (PIE DE PÁGINA) ---
with st.expander("📊 Ver Perfil de Resistencia Nacional para este Microorganismo"):
    conteo_global = []
    for atb in antibioticos_base:
        n_g = df_micro[df_micro[atb].astype(str).str.upper() == 'R'].shape[0]
        conteo_global.append({'Antibiótico': atb.replace('_', ' ').title(), 'Total Nacional R': n_g})
    
    df_global = pd.DataFrame(conteo_global).sort_values('Total Nacional R', ascending=True)
    fig_global = px.bar(df_global, x='Total Nacional R', y='Antibiótico', orientation='h', color_discrete_sequence=['#4682B4'])
    st.plotly_chart(fig_global, use_container_width=True)
