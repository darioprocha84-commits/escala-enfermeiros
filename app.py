import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import io
import datetime
import calendar

# --- 1. CONFIGURAÇÃO DE UTILIZADORES VIA SECRETS ---
if "credentials" in st.secrets:
    credentials = st.secrets["credentials"].to_dict()
else:
    st.error("Erro: Credenciais não configuradas nos Secrets.")
    st.stop()

stauth.Hasher.hash_passwords(credentials)

# --- 2. INICIALIZAÇÃO DO AUTENTICADOR ---
authenticator = stauth.Authenticate(
    credentials,
    "gestao_turnos_multiplos",
    "chave_mestra_2026",
    cookie_expiry_days=1
)

authenticator.login(location='main')

# --- 3. VERIFICAÇÃO DE ESTADO DE AUTENTICAÇÃO ---
if st.session_state["authentication_status"] is False:
    st.error("Utilizador ou palavra-passe incorretos.")
elif st.session_state["authentication_status"] is None:
    st.info("Introduza as suas credenciais para aceder ao sistema.")
else:
    nome_atual = st.session_state['name']
    username_atual = st.session_state['username']
    is_admin = (username_atual == "admin")

    st.sidebar.title(f"Bem-vindo, {nome_atual}")
    authenticator.logout("Sair", "sidebar")

    # --- LIGAÇÃO À GOOGLE SHEET ---
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    def carregar_dados():
        try:
            data = conn.read(worksheet="Folha1", ttl=0)
            return data.dropna(how='all')
        except Exception:
            return pd.DataFrame(columns=['Data', 'Turno', 'Enfermeiro'])

    df_base = carregar_dados()
    df_base['Data'] = df_base['Data'].astype(str)

    st.title("Escala de Trabalho - Linha de Saúde Açores")

    # --- NOVO: PAINEL DE DISPONIBILIDADE (RESUMO DE VAGAS) ---
    st.header("Vagas Disponíveis para o Mês")
    
    # Lógica para gerar todos os dias do mês atual
    hoje = datetime.date.today()
    _, ultimo_dia = calendar.monthrange(hoje.year, hoje.month)
    datas_mes = [datetime.date(hoje.year, hoje.month, dia).strftime('%Y-%m-%d') for dia in range(1, ultimo_dia + 1)]
    
    # Criar DataFrame de estrutura de vagas
    estrutura = []
    for d in datas_mes:
        for t, lim in [("Manhã", 3), ("Tarde", 3), ("Noite", 1)]:
            estrutura.append({"Data": d, "Turno": t, "Limite": lim})
    
    df_vagas = pd.DataFrame(estrutura)
    
    # Contar ocupação atual
    if not df_base.empty:
        ocupacao = df_base.groupby(['Data', 'Turno']).size().reset_index(name='Ocupados')
        df_vagas = df_vagas.merge(ocupacao, on=['Data', 'Turno'], how='left').fillna(0)
    else:
        df_vagas['Ocupados'] = 0

    df_vagas['Vagas'] = (df_vagas['Limite'] - df_vagas['Ocupados']).astype(int)
    
    # Criar a grelha de visualização de vagas
    df_vagas['Data_Curta'] = pd.to_datetime(df_vagas['Data']).dt.strftime('%d/%m')
    mapa_vagas = df_vagas.pivot(index='Turno', columns='Data_Curta', values='Vagas')
    
    # Reordenar linhas para a ordem natural
    mapa_vagas = mapa_vagas.reindex(["Manhã", "Tarde", "Noite"])
    
    st.write("O número em cada célula indica quantas vagas ainda existem:")
    st.dataframe(mapa_vagas, use_container_width=True)

    st.divider()

    # --- 4. ÁREA DE REGISTO ---
    with st.expander("Marcar Disponibilidade"):
        with st.form("registo_disponibilidade"):
            data_sel = st.date_input("Selecione o Dia:", datetime.date.today())
            turno_sel = st.selectbox("Selecione o Turno:", ["Manhã", "Tarde", "Noite"])
            btn_submeter = st.form_submit_button("Confirmar")

        if btn_submeter:
            limite_vagas = 1 if turno_sel == "Noite" else 3
            data_str = data_sel.strftime('%Y-%m-%d')
            
            ocupacao_atual = len(df_base[(df_base['Data'] == data_str) & (df_base['Turno'] == turno_sel)])
            
            ja_tem_este_turno = not df_base[
                (df_base['Data'] == data_str) & 
                (df_base['Turno'] == turno_sel) &
                (df_base['Enfermeiro'] == nome_atual)
            ].empty

            if ja_tem_este_turno:
                st.error(f"Já registou disponibilidade para o turno da {turno_sel} no dia {data_str}.")
            elif ocupacao_atual < limite_vagas:
                novo_registo = pd.DataFrame({'Data': [data_str], 'Turno': [turno_sel], 'Enfermeiro': [nome_atual]})
                df_final = pd.concat([df_base, novo_registo], ignore_index=True)
                conn.update(worksheet="Folha1", data=df_final)
                st.success("Disponibilidade registada!")
                st.rerun()
            else:
                st.error(f"Lotação esgotada para {turno_sel} no dia {data_str}.")

    # --- 5. GESTÃO DE TURNOS PRÓPRIOS ---
    st.subheader("As Minhas Marcações")
    meus_turnos = df_base[df_base['Enfermeiro'] == nome_atual]
    
    if not meus_turnos.empty:
        for idx, row in meus_turnos.iterrows():
            col_info, col_btn = st.columns([4, 1])
            col_info.write(f"📅 {row['Data']} | 🕒 {row['Turno']}")
            if col_btn.button("Retirar", key=f"btn_{idx}"):
                df_apos_remocao = df_base.drop(idx).reset_index(drop=True)
                conn.update(worksheet="Folha1", data=df_apos_remocao)
                st.rerun()
    else:
        st.write("Sem turnos marcados.")

    # --- 6. VISUALIZAÇÃO EM GRELHA (QUEM ESTÁ ONDE) ---
    st.divider()
    st.header("Escala Nominal (Quem está escalado)")

    if not df_base.empty:
        df_vis = df_base.copy()
        df_vis['Data_DT'] = pd.to_datetime(df_vis['Data'])
        df_vis = df_vis.sort_values(by='Data_DT')
        df_vis['Data_Label'] = df_vis['Data_DT'].dt.strftime('%d/%m')
        df_vis['Sigla'] = df_vis['Turno'].map({'Manhã': 'M', 'Tarde': 'T', 'Noite': 'N'})
        
        try:
            grelha = df_vis.pivot_table(
                index='Enfermeiro', 
                columns='Data_Label', 
                values='Sigla', 
                aggfunc=lambda x: ', '.join(sorted(x)),
                sort=False
            ).fillna('')
            st.dataframe(grelha, use_container_width=True)
        except Exception:
            st.warning("Erro ao gerar o mapa nominal.")

        # --- 7. EXPORTAÇÃO ---
        st.subheader("Exportar para Excel")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            if is_admin:
                if 'grelha' in locals():
                    grelha.to_excel(writer, sheet_name='Escala_Nominal')
                mapa_vagas.to_excel(writer, sheet_name='Vagas_Disponiveis')
                df_base.to_excel(writer, index=False, sheet_name='Dados_Brutos')
                file_out = "escala_completa_LSA.xlsx"
            else:
                meus_turnos.to_excel(writer, index=False, sheet_name='Meus_Turnos')
                file_out = f"escala_{username_atual}.xlsx"

        st.download_button("Descarregar Excel", buffer.getvalue(), file_out)
