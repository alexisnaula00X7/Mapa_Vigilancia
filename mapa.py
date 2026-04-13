import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

# --- 1. CONEXIÓN A SUPABASE ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    SUPABASE_URL = "TU_URL_AQUI"
    SUPABASE_KEY = "TU_KEY_AQUI"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Mapa Epidemiológico Ecuador", layout="wide")

# --- 3. EXTRACCIÓN DE DATOS ---
@st.cache_data(ttl=600)  # Se actualiza cada 10 min
def cargar_datos():
    res = supabase.table("registros_resistencia").select("*").execute()
    return pd.DataFrame(res.data)

df = cargar_datos()

# --- 4. INTERFAZ ---
st.title("🧬 Vigilancia Epidemiológica de Resistencia Bacteriana")

if df.empty:
    st.info("No hay datos registrados aún. Registra una muestra para visualizar el mapa.")
else:
    # --- 5. FILTROS PARA EL MAPA ---
    col_f1, col_f2 = st.columns(2)
    
    with col_f1:
        # Extraemos solo las columnas de antibióticos para el selector
        lista_atb = [
            'ampicilina_sulbactam', 'cefalotina', 'cefazolina', 'ceftazidima', 
            'ceftriaxona', 'cefepima', 'ertapenem', 'meropenem', 'amicacina', 
            'gentamicina', 'ciprofloxacino', 'norfloxacino', 'fosfomicina', 
            'nitrofurantoina', 'trimetoprim_sulfametoxazol'
        ]
        atb_seleccionado = st.selectbox("Selecciona Antibiótico para el mapa:", lista_atb)

    # Filtrar solo casos resistentes 'R' para el mapa
    df_resistentes = df[df[atb_seleccionado].str.upper() == 'R'].copy()

    # --- 6. VISUALIZACIÓN ---
    tab1, tab2 = st.tabs(["🗺️ Mapa de Resistencia", "📊 Tabla de Datos"])

    with tab1:
        if not df_resistentes.empty:
            # Agrupar por ubicación
            df_geo = df_resistentes.groupby(['provincia', 'canton']).size().reset_index(name='Casos Resistentes')
            
            fig = px.treemap(
                df_geo, 
                path=['provincia', 'canton'], 
                values='Casos Resistentes',
                color='Casos Resistentes',
                color_continuous_scale='Reds',
                title=f"Distribución de Resistencia a: {atb_seleccionado}"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"No se registran casos de resistencia (R) para {atb_seleccionado} en la base de datos.")

    with tab2:
        st.subheader("Registros Completos")
        st.dataframe(df, use_container_width=True)

# --- 7. BOTÓN PARA REFRESCAR ---
if st.button("🔄 Actualizar Datos"):
    st.cache_data.clear()
    st.rerun()
