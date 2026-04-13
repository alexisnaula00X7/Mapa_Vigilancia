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
    res = supabase.table("registro_resistencia").select("*").execute()
    df = pd.DataFrame(res.data)
    ruta_geojson = "ec-allgeo.json" 
    geojson = None
    if os.path.exists(ruta_geojson):
        with open(ruta_geojson, "r", encoding="utf-8") as f:
            geojson = json.load(f)
    return df, geojson

df_raw, geojson_ecuador = cargar_todo()

# --- 3. CONFIGURACIÓN DE ANTIBIÓTICOS (Lista exacta de tu imagen) ---
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
    # IMPORTANTE: Seleccionar Microorganismo es clave para la gráfica
    micro_list = sorted(df_raw['microorganismo'].unique().tolist())
    micro_sel = st.selectbox("🦠 Microorganismo", micro_list)

with c3:
    atb_sel = st.selectbox("💊 Antibiótico (Mapa)", ["TODOS"] + antibioticos_base)

with c4:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Actualizar"):
        st.cache_data.clear()
        st.rerun()

# --- 5. LÓGICA DE FILTRADO ---
# Filtro base por microorganismo
df_f = df_raw[df_raw['microorganismo'] == micro_sel].copy()

# Filtro por ubicación para los KPIs y el Mapa
df_geo = df_f.copy()
if prov_sel != "Todas":
    df_geo = df_geo[df_geo['provincia'] == prov_sel]

# Casos Resistentes para el Mapa
if atb_sel == "TODOS":
    mask_r = df_geo[antibioticos_base].astype(str).apply(lambda x: x.str.upper()).eq('R').any(axis=1)
    df_res_mapa = df_geo[mask_r].copy()
else:
    df_res_mapa = df_geo[df_geo[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 6. INDICADORES (KPIs) ---
m1, m2, m3, m4 = st.columns(4)
m1.metric("Muestras Analizadas", len(df_geo))
m2.metric("Casos Resistentes (Filtro)", len(df_res_mapa))
porc = (len(df_res_mapa)/len(df_geo)*100) if len(df_geo)>0 else 0
m3.metric("% Resistencia", f"{porc:.1f}%")
m4.metric("Microorganismo", micro_sel)

st.divider()

# --- 7. GRÁFICO DE BARRAS (PERFIL DE RESISTENCIA) ---
# Lo mostramos antes del mapa para que sea protagonista
st.subheader(f"📈 Perfil de Resistencia Global para: {micro_sel}")

conteo_atb = []
for atb in antibioticos_base:
    if atb in df_f.columns:
        # Aquí contamos sobre df_f (todo el país para ese micro) para que la gráfica siempre tenga datos
        n_r = df_f[df_f[atb].astype(str).str.upper() == 'R'].shape[0]
        conteo_atb.append({'Antibiótico': atb.replace('_', ' ').title(), 'Casos R': n_r})

df_plot = pd.DataFrame(conteo_atb).sort_values('Casos R', ascending=True)

if df_plot['Casos R'].sum() > 0:
    fig_bar = px.bar(
        df_plot, x='Casos R', y='Antibiótico', orientation='h',
        color='Casos R', color_continuous_scale='Reds',
        text='Casos R', labels={'Casos R': 'Frecuencia de Resistencia'}
    )
    fig_bar.update_layout(height=450, margin=dict(l=20, r=20, t=10, b=10))
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.info(f"No hay datos de resistencia registrados para {micro_sel}.")

st.divider()

# --- 8. MAPA Y TABLA ---
col_mapa, col_tabla = st.columns([2, 1])

with col_mapa:
    if geojson_ecuador:
        df_mapa = df_res_mapa.copy()
        df_mapa['provincia_id'] = df_mapa['provincia'].str.strip().str.title()
        conteo_prov = df_mapa.groupby('provincia_id').size().reset_index(name='conteo')

        fig_map = px.choropleth_mapbox(
            conteo_prov, geojson=geojson_ecuador, locations='provincia_id',
            featureidkey='properties.name', color='conteo',
            color_continuous_scale="YlOrRd", mapbox_style="carto-positron",
            center={"lat": -1.8, "lon": -78.5}, zoom=5.2, opacity=0.7,
            title=f"Mapa de Calor: {atb_sel}"
        )
        fig_map.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)

with col_tabla:
    st.subheader("📋 Top Cantones (R)")
    if not df_res_mapa.empty:
        res_c = df_res_mapa['canton'].value_counts().reset_index()
        res_c.columns = ['Cantón', 'Casos R']
        st.dataframe(res_c, use_container_width=True, hide_index=True)
    else:
        st.info("Sin casos en esta ubicación.")
