import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import io
import datetime

# --- 1. CONFIGURAÇÃO DE UTILIZADORES VIA SECRETS ---
if "credentials" in st.secrets:
    credentials = st.secrets["credentials"].to_dict()
else:
    st.error("Erro: Credenciais não configuradas nos Secrets.")
    st.stop()

# O Hasher continua a ser necessário para validar as passwords
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
    
    # Função para ler dados da folha
    def carregar_dados():
        try:
            return conn.read(ttl=0)
        except:
            return pd.DataFrame(columns=['Data', 'Turno', 'Enfermeiro'])

    df_base = carregar_dados()

    st.title("Escala de Trabalho - Linha de Saúde Açores")

    # --- 4. ÁREA DE REGISTO (PERMITE MÚLTIPLOS TURNOS POR DIA) ---
    with st.expander("Marcar Disponibilidade"):
        with st.form("registo_disponibilidade"):
            data_sel = st.date_input("Selecione o Dia:", datetime.date.today())
            turno_sel = st.selectbox("Selecione o Turno:", ["Manhã", "Tarde", "Noite"])
            btn_submeter = st.form_submit_button("Confirmar")

        if btn_submeter:
            limite_vagas = 1 if turno_sel == "Noite" else 3
            data_str = data_sel.strftime('%Y-%m-%d')
            
            # Verificar ocupação total do turno naquela data
            ocupacao = len(df_base[
                (df_base['Data'] == data_str) & 
                (df_base['Turno'] == turno_sel)
            ])
            
            # Verifica se o enfermeiro já tem este turno específico neste dia
            ja_tem_este_turno = not df_base[
                (df_base['Data'] == data_str) & 
                (df_base['Turno'] == turno_sel) &
                (df_base['Enfermeiro'] == nome_atual)
            ].empty

            if ja_tem_este_turno:
                st.error(f"Já registou disponibilidade para o turno da {turno_sel} no dia {data_str}.")
            elif ocupacao < limite_vagas:
                novo_registo = pd.DataFrame({
                    'Data': [data_str], 
                    'Turno': [turno_sel], 
                    'Enfermeiro': [nome_atual]
                })
                df_final = pd.concat([df_base, novo_registo], ignore_index=True)
                conn.update(data=df_final)
                st.success("Disponibilidade registada e guardada!")
                st.rerun()
            else:
                st.error(f"O turno da {turno_sel} para o dia {data_str} já está completo.")

    # --- 5. GESTÃO DE TURNOS PRÓPRIOS ---
    st.subheader("As Minhas Marcações")
    meus_turnos = df_base[df_base['Enfermeiro'] == nome_atual]
    
    if not meus_turnos.empty:
        for idx, row in meus_turnos.iterrows():
            col_info, col_btn = st.columns([4, 1])
            col_info.write(f"📅 {row['Data']} | 🕒 {row['Turno']}")
            if col_btn.button("Retirar", key=f"btn_{idx}"):
                df_apos_remocao = df_base.drop(idx).reset_index(drop=True)
                conn.update(data=df_apos_remocao)
                st.rerun()
    else:
        st.write("Sem turnos marcados.")

    # --- 6. VISUALIZAÇÃO EM GRELHA ---
    st.divider()
    st.header("Mapa Mensal de Disponibilidades")

    if not df_base.empty:
        df_visualizacao = df_base.copy()
        # Garantir que a coluna Data é tratada como data para ordenação
        df_visualizacao['Data_DT'] = pd.to_datetime(df_visualizacao['Data'])
        df_visualizacao = df_visualizacao.sort_values(by='Data_DT')
        df_visualizacao['Data_Label'] = df_visualizacao['Data_DT'].dt.strftime('%d/%m')
        
        df_visualizacao['Sigla'] = df_visualizacao['Turno'].map({'Manhã': 'M', 'Tarde': 'T', 'Noite': 'N'})
        
        try:
            grelha = df_visualizacao.pivot_table(
                index='Enfermeiro', 
                columns='Data_Label', 
                values='Sigla', 
                aggfunc=lambda x: ', '.join(sorted(x)),
                sort=False
            ).fillna('')
            st.dataframe(grelha, use_container_width=True)
        except Exception:
            st.warning("Erro ao gerar o mapa visual.")

        # --- 7. EXPORTAÇÃO ---
        st.subheader("Exportar para Excel")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            if is_admin:
                grelha.to_excel(writer, sheet_name='Mapa_Geral')
                df_base.to_excel(writer, index=False, sheet_name='Lista_Completa')
                file_out = "escala_geral.xlsx"
            else:
                meus_turnos.to_excel(writer, index=False, sheet_name='Meus_Turnos')
                file_out = f"escala_{username_atual}.xlsx"

        st.download_button("Descarregar Excel", buffer.getvalue(), file_out)
    else:
        st.info("Aguardando marcações na base de dados.")
