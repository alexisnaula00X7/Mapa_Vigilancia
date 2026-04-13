import streamlit as st
import pandas as pd
import plotly.express as px
import shapefile
import unicodedata
import os
import json
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="LIMS - Vigilancia RAM Ecuador", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    div.block-container { padding-top: 2rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; color: #1f77b4; }
    </style>
    """, unsafe_allow_html=True)

def normalizar_texto(texto):
    if not texto: return ""
    texto = str(texto).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', texto)
                  if unicodedata.category(c) != 'Mn')

# --- 2. CONEXIÓN Y CARGA DE DATOS ---
@st.cache_resource
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception:
        st.error("Error en credenciales de Supabase.")
        return None

@st.cache_data(ttl=600)
def cargar_datos_base():
    supabase = init_connection()
    if supabase:
        res = supabase.table("registro_resistencia").select("*").execute()
        df = pd.DataFrame(res.data)
        df['provincia_id'] = df['provincia'].apply(normalizar_texto)
        return df
    return pd.DataFrame()

@st.cache_resource
def cargar_cartografia():
    # Usando el nombre exacto de tus archivos: gadm41_ECU_1
    base_name = "gadm41_ECU_1"
    
    if os.path.exists(f"{base_name}.shp"):
        try:
            sf = shapefile.Reader(base_name)
            fields = [x[0] for x in sf.fields][1:]
            features = []
            for sr in sf.shapeRecords():
                atr = dict(zip(fields, sr.record))
                nombre_prov = atr.get('NAME_1') or str(list(atr.values())[0])
                atr['ID_NORMALIZADO'] = normalizar_texto(nombre_prov)
                geom = sr.shape.__geo_interface__
                features.append(dict(type="Feature", geometry=geom, properties=atr, id=atr['ID_NORMALIZADO']))
            return {"type": "FeatureCollection", "features": features}, "id"
        except Exception as e:
            st.error(f"Error cargando SHP: {e}")

    # Fallback si el SHP falla
    if os.path.exists("ec-allgeo.json"):
        with open("ec-allgeo.json", "r", encoding="utf-8") as f:
            return json.load(f), "properties.name"
    return None, None

df_raw = cargar_datos_base()
geojson_data, feature_key = cargar_cartografia()

# --- 3. DEFINICIÓN ESTRICTA DE ANTIBIÓTICOS (SEGÚN TU FOTO) ---
lista_atbs_foto = [
    'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima',
    'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina',
    'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina',
    'nitrofurantoina', 'trimetoprim_sulfametoxazol'
]

# Filtrar solo los que realmente existan en el DataFrame por si acaso
antibioticos = [atb for atb in lista_atbs_foto if atb in df_raw.columns]

# --- 4. INTERFAZ Y FILTROS ---
st.title("🧪 Vigilancia Epidemiológica de Resistencia (RAM)")

with st.sidebar:
    st.header("⚙️ Configuración")
    micro_sel = st.selectbox("🦠 Microorganismo", ["Todas"] + sorted(df_raw['microorganismo'].unique().tolist()))
    atb_sel = st.selectbox("💊 Antibiótico", antibioticos)
        
    st.divider()
    prov_sel = st.selectbox("📍 Filtrar Provincia", ["Todas"] + sorted(df_raw['provincia'].unique().tolist()))
    
    if st.button("🔄 Refrescar Datos"):
        st.cache_data.clear()
        st.rerun()

# Lógica de filtrado
df_f = df_raw[df_raw['microorganismo'] == micro_sel].copy()
if prov_sel != "Todas":
    df_f = df_f[df_f['provincia'] == prov_sel]

df_atb = df_f[df_f[atb_sel].notnull()].copy()
df_res = df_atb[df_atb[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 5. DASHBOARD ---
m1, m2, m3, m4 = st.columns(4)
total_n = len(df_atb)
total_r = len(df_res)
pct = (total_r / total_n * 100) if total_n > 0 else 0

m1.metric("Aislamientos", total_n)
m2.metric("Resistentes (R)", total_r)
m3.metric("% Resistencia", f"{pct:.1f}%")
m4.metric("Microorganismo Top", micro_sel)

st.divider()

tab_mapa, tab_perfil, tab_detalles = st.tabs(["🗺️ Mapa de Calor", "📈 Perfil de Resistencia", "📋 Datos Detallados"])

with tab_mapa:
    if geojson_data:
        df_mapa = df_res.groupby('provincia_id').size().reset_index(name='conteo')
        
        fig_map = px.choropleth_mapbox(
            df_mapa,
            geojson=geojson_data,
            locations='provincia_id',
            featureidkey=feature_key,
            color='conteo',
            color_continuous_scale="Reds",
            mapbox_style="carto-positron",
            center={"lat": -1.8, "lon": -78.5},
            zoom=5.5,
            opacity=0.7,
            title=f"Mapa de Calor: Resistencia a {atb_sel.replace('_', ' ').title()}"
        )
        fig_map.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.warning("No se pudo cargar la cartografía.")

with tab_perfil:
    st.subheader(f"Resistencia acumulada: {micro_sel}")
    # Calculamos R para todos los ATBs de la foto
    conteo_total = df_f[antibioticos].apply(lambda x: x.str.upper().eq('R').sum()).reset_index()
    conteo_total.columns = ['Antibiótico', 'Resistencias']
    conteo_total = conteo_total.sort_values('Resistencias', ascending=True)
    
    fig_bar = px.bar(conteo_total, x='Resistencias', y='Antibiótico', orientation='h',
                     color='Resistencias', color_continuous_scale='RdYlGn_r')
    st.plotly_chart(fig_bar, use_container_width=True)

with tab_detalles:
    st.dataframe(df_atb, use_container_width=True)
