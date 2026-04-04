import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
import io

# 1. Configuração de Utilizadores
# Lista simplificada para o exemplo. Pode expandir para os 40 nomes.
nomes = ["Admin", "Enfermeiro 1", "Enfermeiro 2", "Enfermeiro 3", "Enfermeiro 4"]
utilizadores = ["admin", "enf1", "enf2", "enf3", "enf4"]
passwords = ["admin123", "pass1", "pass2", "pass3", "pass4"]

# Gerar hashes das passwords para segurança
hashed_passwords = stauth.Hasher(passwords).generate()

credentials = {"usernames": {}}
for u, n, p in zip(utilizadores, nomes, hashed_passwords):
    credentials["usernames"][u] = {"name": n, "password": p}

# 2. Inicialização do Autenticador
authenticator = stauth.Authenticate(
    credentials,
    "gestao_turnos_enfermeiros",
    "chave_seguranca_123",
    cookie_expiry_days=1
)

# Renderizar formulário de login
nome_utilizador, estado_autenticacao, login_id = authenticator.login("Login do Serviço de Saúde", "main")

if estado_autenticacao == False:
    st.error("Utilizador ou palavra-passe incorretos.")
elif estado_autenticacao == None:
    st.info("Introduza as suas credenciais para aceder ao sistema de turnos.")
else:
    # 3. Interface Principal após Login
    st.sidebar.title(f"Bem-vindo, {nome_utilizador}")
    authenticator.logout("Sair do Sistema", "sidebar")

    # Base de dados em memória (num caso real, deve ser um ficheiro CSV ou SQL)
    if 'base_dados_turnos' not in st.session_state:
        st.session_state.base_dados_turnos = pd.DataFrame(columns=['Data', 'Turno', 'Enfermeiro'])

    st.title("Marcação de Disponibilidade para Turnos")

    # 4. Formulário de Seleção de Turno
    with st.form("formulario_turno"):
        data_escolhida = st.date_input("Selecione a Data:")
        turno_escolhido = st.selectbox("Selecione o Turno:", ["Manhã (08:00-15:59)", "Tarde (16:00-23:59)", "Noite (00:00-07:59)"])
        submeter_btn = st.form_submit_button("Confirmar Disponibilidade")

    if submeter_btn:
        # Extrair o nome do turno para a base de dados
        tipo_turno = turno_escolhido.split(" ")[0]
        
        # Regras de Limite
        limite_vagas = 1 if tipo_turno == "Noite" else 3

        # Contagem de vagas já preenchidas
        registos_atuais = st.session_state.base_dados_turnos[
            (st.session_state.base_dados_turnos['Data'] == data_escolhida) & 
            (st.session_state.base_dados_turnos['Turno'] == tipo_turno)
        ]
        
        # Verificação se o próprio enfermeiro já está registado nesse dia
        ja_no_sistema = not st.session_state.base_dados_turnos[
            (st.session_state.base_dados_turnos['Data'] == data_escolhida) & 
            (st.session_state.base_dados_turnos['Enfermeiro'] == nome_utilizador)
        ].empty

        if ja_no_sistema:
            st.error("Já registou uma disponibilidade para esta data.")
        elif len(registos_atuais) < limite_vagas:
            novo_registo = pd.DataFrame({
                'Data': [data_escolhida], 
                'Turno': [tipo_turno], 
                'Enfermeiro': [nome_utilizador]
            })
            st.session_state.base_dados_turnos = pd.concat([st.session_state.base_dados_turnos, novo_registo], ignore_index=True)
            st.success(f"Disponibilidade para o turno da {tipo_turno} guardada com sucesso.")
        else:
            st.error(f"O turno da {tipo_turno} para o dia {data_escolhida} já atingiu o limite de {limite_vagas} enfermeiros.")

    # 5. Visualização e Exportação (Apenas se houver dados)
    st.divider()
    st.subheader("Mapa de Turnos Consolidado")
    
    if not st.session_state.base_dados_turnos.empty:
        # Ordenar por data e turno para facilitar a leitura
        mapa_ordenado = st.session_state.base_dados_turnos.sort_values(by=['Data', 'Turno'])
        st.dataframe(mapa_ordenado, use_container_width=True)

        # Funcionalidade de exportação para Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            mapa_ordenado.to_excel(writer, index=False, sheet_name='Horário_Enfermeiros')
            
        st.download_button(
            label="Descarregar Escala em Excel",
            data=buffer.getvalue(),
            file_name="escala_enfermeiros_final.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Ainda não existem disponibilidades registadas para este mês.")