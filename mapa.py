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

# Estilos personalizados para mejorar la visualización
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    div.block-container { padding-top: 2rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; color: #1f77b4; }
    </style>
    """, unsafe_allow_html=True)

# Función para normalizar texto (Elimina tildes y eñes, clave para el cruce de datos)
def normalizar_texto(texto):
    if not texto: return ""
    texto = str(texto).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', texto)
                  if unicodedata.category(c) != 'Mn')

# --- 2. CONEXIÓN Y CARGA DE DATOS ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("Error en las credenciales de Supabase. Revisa los Secrets.")
        return None

@st.cache_data(ttl=600)
def cargar_datos_base():
    supabase = init_connection()
    if supabase:
        res = supabase.table("registro_resistencia").select("*").execute()
        df = pd.DataFrame(res.data)
        # ID normalizado para cruce con mapa
        df['provincia_id'] = df['provincia'].apply(normalizar_texto)
        return df
    return pd.DataFrame()

@st.cache_resource
def cargar_cartografia():
    """Intenta cargar Shapefile de GADM, si falla busca el GeoJSON local"""
    base_name = "gadm41_ECU_1"
    
    # Intento 1: Shapefile (GADM)
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
            st.warning(f"Error con SHP, intentando fallback: {e}")

    # Intento 2: Fallback a GeoJSON local
    ruta_geojson = "ec-all.geo.json"
    if os.path.exists(ruta_geojson):
        with open(ruta_geojson, "r", encoding="utf-8") as f:
            return json.load(f), "properties.name" # Llave típica en Highcharts/GeoJSON
            
    return None, None

# Carga inicial
df_raw = cargar_datos_base()
geojson_data, feature_key = cargar_cartografia()

# --- 3. FILTROS Y LÓGICA ---
st.title("📊 Vigilancia Epidemiológica de Resistencia (RAM)")

if df_raw.empty:
    st.warning("No hay datos disponibles en Supabase.")
    st.stop()

# Identificar columnas de antibióticos automáticamente
cols_fijas = ["id", "created_at", "provincia", "canton", "microorganismo", "provincia_id"]
lista_atbs = [c for c in df_raw.columns if c not in cols_fijas]

with st.sidebar:
    st.header("⚙️ Configuración")
    micro_sel = st.selectbox("🦠 Microorganismo", sorted(df_raw['microorganismo'].unique().tolist()))
    atb_sel = st.selectbox("💊 Antibiótico", lista_atbs)
    
    st.divider()
    prov_sel = st.selectbox("📍 Filtrar Provincia", ["Todas"] + sorted(df_raw['provincia'].unique().tolist()))
    
    if st.button("🔄 Refrescar Datos"):
        st.cache_data.clear()
        st.rerun()

# Filtrado de datos
df_f = df_raw[df_raw['microorganismo'] == micro_sel].copy()
if prov_sel != "Todas":
    df_f = df_f[df_f['provincia'] == prov_sel]

# Solo registros que tengan resultado para el ATB seleccionado
df_atb = df_f[df_f[atb_sel].notnull()].copy()
df_res = df_atb[df_atb[atb_sel].astype(str).str.upper() == 'R'].copy()

# --- 4. DASHBOARD VISUAL ---

# Fila 1: Métricas
m1, m2, m3, m4 = st.columns(4)
total_n = len(df_atb)
total_r = len(df_res)
pct = (total_r / total_n * 100) if total_n > 0 else 0

m1.metric("Aislamientos", total_n)
m2.metric("Resistentes (R)", total_r)
m3.metric("% Resistencia", f"{pct:.1f}%")
m4.metric("Provincia Top", df_res['provincia'].mode()[0] if not df_res.empty else "N/A")

st.divider()

# Fila 2: Tabs de Análisis
tab_mapa, tab_graficos, tab_datos = st.tabs(["🗺️ Mapa Epidemiológico", "📈 Gráficos de Perfil", "📋 Tabla de Datos"])

with tab_mapa:
    col_map, col_info = st.columns([2, 1])
    
    with col_map:
        if geojson_data:
            # Agrupar por ID normalizado para el mapa
            df_mapa_final = df_res.groupby('provincia_id').size().reset_index(name='Casos_R')
            
            fig_map = px.choropleth_mapbox(
                df_mapa_final,
                geojson=geojson_data,
                locations='provincia_id',
                featureidkey=feature_key,
                color='Casos_R',
                color_continuous_scale="YlOrRd",
                mapbox_style="carto-positron",
                center={"lat": -1.8, "lon": -78.5},
                zoom=5.3,
                opacity=0.7,
                title=f"Distribución de Resistencia: {atb_sel.replace('_', ' ').upper()}"
            )
            fig_map.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.error("No se encontró cartografía (gadm41_ECU_1 o ec-all.geo.json)")

    with col_info:
        st.write("### Resumen por Provincia")
        if not df_res.empty:
            resumen_prov = df_res['provincia'].value_counts().reset_index()
            resumen_prov.columns = ['Provincia', 'Casos R']
            st.dataframe(resumen_prov, use_container_width=True, hide_index=True)
        else:
            st.info("No hay casos resistentes para los filtros seleccionados.")

with tab_graficos:
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        # Gráfico de barras horizontal (Estilo RStudio)
        st.subheader("Perfil de Resistencia General")
        conteo_atbs = df_f[lista_atbs].apply(lambda x: x.str.upper().eq('R').sum()).reset_index()
        conteo_atbs.columns = ['Antibiótico', 'Resistencias']
        conteo_atbs = conteo_atbs.sort_values('Resistencias', ascending=True)
        
        fig_bar = px.bar(conteo_atbs, x='Resistencias', y='Antibiótico', orientation='h',
                         color='Resistencias', color_continuous_scale='RdYlGn_r')
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_g2:
        st.subheader("Top Cantones afectados")
        if not df_res.empty:
            fig_pie = px.pie(df_res, names='canton', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)

with tab_datos:
    st.subheader("Registros filtrados")
    st.dataframe(df_atb, use_container_width=True)
    
    csv = df_atb.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Descargar Datos CSV", csv, "datos_ram.csv", "text/csv")
