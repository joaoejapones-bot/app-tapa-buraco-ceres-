import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import sqlite3
from datetime import datetime
from geopy.geocoders import Nominatim
import urllib.parse # Para criar o link do Google Maps

# --- 1. BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('dados_ceres.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS buracos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 rua TEXT, bairro TEXT, gravidade TEXT, lat REAL, lon REAL, status TEXT, data_conclusao TEXT)''')
    try:
        c.execute("ALTER TABLE buracos ADD COLUMN data_conclusao TEXT")
    except:
        pass
    conn.commit()
    return conn

conn = init_db()

# --- 2. FUNÇÃO BUSCAR RUA ---
def buscar_nome_rua(lat, lon):
    try:
        geolocator = Nominatim(user_agent="cityfix_ceres_final_route")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        if location:
            address = location.raw.get('address', {})
            return address.get('road') or address.get('pedestrian') or "Rua não identificada"
        return "Local não mapeado"
    except:
        return ""

# --- 3. CONFIGURAÇÃO ---
st.set_page_config(page_title="CityFix Ceres - Gestão", layout="wide")
st.title("🚚 CityFix Ceres: Gestão e Rota")

USINA_COORD = [-15.310306, -49.6175]

# --- 4. BARRA LATERAL (HISTÓRICO) ---
st.sidebar.header("📜 Histórico de Obras")
data_consulta = st.sidebar.date_input("Consultar dia:", datetime.now())
data_str = data_consulta.strftime('%Y-%m-%d')

if 'modo' not in st.session_state:
    st.session_state.modo = "Gestao"

if st.sidebar.button("🔍 Ver Relatório do Dia"):
    st.session_state.modo = "Historico"
    st.session_state.data_ver = data_str

if st.sidebar.button("🏠 Voltar para Hoje"):
    st.session_state.modo = "Gestao"
    st.rerun()

# --- 5. LÓGICA DE EXIBIÇÃO ---

if st.session_state.modo == "Historico":
    st.header(f"📅 Relatório de Obras: {st.session_state.data_ver}")
    df_hist = pd.read_sql_query(f"SELECT * FROM buracos WHERE status = 'Tapado' AND data_conclusao = '{st.session_state.data_ver}'", conn)
    
    if not df_hist.empty:
        col_h1, col_h2 = st.columns([1, 2])
        with col_h1:
            st.write(f"Neste dia foram tapados **{len(df_hist)}** buracos.")
            st.table(df_hist[['rua', 'gravidade']])
        with col_h2:
            m_hist = folium.Map(location=[-15.3072, -49.5975], zoom_start=14)
            for _, row in df_hist.iterrows():
                folium.Marker([row['lat'], row['lon']], popup=row['rua'], icon=folium.Icon(color="blue", icon="check")).add_to(m_hist)
            st_folium(m_hist, width="100%", height=400, key="mapa_hist")
    else:
        st.warning("Nenhum registro de obra finalizada nesta data.")

else:
    # --- INTERFACE DE GESTÃO ---
    col1, col2 = st.columns([1, 2])
    df_pendentes = pd.read_sql_query("SELECT * FROM buracos WHERE status = 'Pendente'", conn)

    with col2:
        m = folium.Map(location=[-15.3072, -49.5975], zoom_start=14)
        folium.Marker(USINA_COORD, icon=folium.Icon(color="black", icon="truck", prefix="fa")).add_to(m)
        
        for _, row in df_pendentes.iterrows():
            cor = {"Baixa": "green", "Média": "orange", "Alta": "red", "Crítica": "black"}[row['gravidade']]
            folium.Marker([row['lat'], row['lon']], popup=row['rua'], icon=folium.Icon(color=cor)).add_to(m)
        
        if 'clique_atual' in st.session_state and st.session_state.clique_atual:
            folium.Marker(st.session_state.clique_atual, icon=folium.Icon(color="purple")).add_to(m)
        
        mapa_saida = st_folium(m, width="100%", height=450, key="mapa_gestao")
        
        if mapa_saida and mapa_saida.get("last_clicked"):
            lat = mapa_saida["last_clicked"]["lat"]
            lng = mapa_saida["last_clicked"]["lng"]
            if st.session_state.get('clique_atual') != [lat, lng]:
                st.session_state.clique_atual = [lat, lng]
                st.session_state.rua_detectada = buscar_nome_rua(lat, lng)
                st.rerun()

    with col1:
        st.header("📍 Novo Registro")
        with st.form("form_novo", clear_on_submit=True):
            rua_auto = st.session_state.get('rua_detectada', "")
            rua = st.text_input("Rua/Referência:", value=rua_auto)
            gravidade = st.select_slider("Gravidade:", options=["Baixa", "Média", "Alta", "Crítica"])
            if st.form_submit_button("Salvar"):
                if 'clique_atual' in st.session_state and st.session_state.clique_atual:
                    c = conn.cursor()
                    c.execute("INSERT INTO buracos (rua, gravidade, lat, lon, status) VALUES (?, ?, ?, ?, ?)",
                              (rua, gravidade, st.session_state.clique_atual[0], st.session_state.clique_atual[1], "Pendente"))
                    conn.commit()
                    st.session_state.clique_atual = None
                    st.session_state.rua_detectada = ""
                    st.rerun()

        # --- NOVA FUNÇÃO: GERAR ROTA GOOGLE MAPS ---
        if not df_pendentes.empty:
            st.divider()
            st.subheader("🛠️ Ações da Rota")
            
            # Criando o link do Google Maps
            # Formato: https://www.google.com/maps/dir/USINA/PONTO1/PONTO2...
            base_url = "https://www.google.com/maps/dir/"
            pontos = f"{USINA_COORD[0]},{USINA_COORD[1]}/" # Começa na Usina
            for _, row in df_pendentes.iterrows():
                pontos += f"{row['lat']},{row['lon']}/"
            
            link_final = base_url + pontos
            
            st.link_button("📲 ENVIAR ROTA PARA O GPS (Google Maps)", link_final, type="primary")

            if st.button("✅ FINALIZAR TODAS AS OBRAS"):
                hoje = datetime.now().strftime('%Y-%m-%d')
                conn.execute(f"UPDATE buracos SET status = 'Tapado', data_conclusao = '{hoje}' WHERE status = 'Pendente'").connection.commit()
                st.success("Trabalho concluído!")
                st.rerun()

    # Tabela com botão de excluir individual
    st.divider()
    st.subheader("📋 Lista de Controle")
    for index, row in df_pendentes.iterrows():
        c1, c2, c3 = st.columns([4, 1, 1])
        c1.write(f"🏠 **{row['rua']}** ({row['gravidade']})")
        if c3.button("❌", key=f"del_{row['id']}"):
            conn.cursor().execute("DELETE FROM buracos WHERE id = ?", (row['id'],)).connection.commit()
            st.rerun()