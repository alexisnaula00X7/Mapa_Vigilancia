import streamlit as st
import plotly.express as px

def app_mapa_epidemiologico(df):
    st.title("📊 Análisis Geográfico de Resistencia")
    
    # 1. Filtros laterales
    with st.sidebar:
        st.header("Filtros de Análisis")
        atb_select = st.selectbox("Selecciona Antibiótico", 
                                  ['ampicilina_sulbactam', 'ceftriaxona', 'meropenem', 'amicacina'])
        tipo_filtro = st.radio("Mostrar:", ["Solo Resistentes", "Todos los Resultados"])

    # 2. Lógica de filtrado
    mask = df[atb_select] == "R" if tipo_filtro == "Solo Resistentes" else df[atb_select].notnull()
    df_mapa = df[mask].groupby(['provincia', 'canton']).size().reset_index(name='conteo')

    # 3. Creación del Mapa (Treemap como alternativa visual de densidad)
    fig = px.treemap(df_mapa, 
                     path=['provincia', 'canton'], 
                     values='conteo',
                     color='conteo',
                     color_continuous_scale='Reds',
                     hover_data=['conteo'])
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 4. Tabla de focos calientes
    st.subheader("📍 Focos Detectados")
    st.table(df_mapa.sort_values(by='conteo', ascending=False).head(10))
