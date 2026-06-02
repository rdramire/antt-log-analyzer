import streamlit as st
from config import CUSTOM_CSS

def check_authentication():
    """
    Verifica se o usuário está autenticado no dashboard.
    Caso não esteja, renderiza uma tela de login centralizada com glassmorphism.
    
    Retorna:
        bool: True se autenticado, False caso contrário.
    """
    # Garante a injeção do CSS customizado para manter a identidade visual dark premium
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # Inicializa a variável de estado de sessão caso não exista
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    # Se o usuário já estiver autenticado, prossegue normalmente
    if st.session_state["authenticated"]:
        return True

    # Renderiza a tela de login estruturada com colunas para centralização responsiva
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col_left, col_mid, col_right = st.columns([1, 2, 1])
    
    with col_mid:
        st.markdown(
            """
            <div class="css-card-premium" style="padding: 35px; border-radius: 16px; margin-bottom: 25px; border: 1px solid rgba(99, 102, 241, 0.2);">
                <div style="text-align: center; margin-bottom: 10px;">
                    <span style="font-size: 3rem;">🔐</span>
                    <h2 style="margin: 15px 0 5px 0; font-size: 1.8rem; font-weight: 700; background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                        Acesso Restrito
                    </h2>
                    <p style="margin: 0; color: #94a3b8; font-size: 0.95rem; font-weight: 300;">
                        Painel de Inteligência Operacional ANTT & CIOT
                    </p>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Utiliza st.form para evitar atualizações de tela a cada tecla digitada
        with st.form("login_form", clear_on_submit=False):
            password = st.text_input(
                "Senha de Homologação:",
                type="password",
                placeholder="Insira a senha de acesso...",
                help="Esta aplicação é protegida por controle de acesso privado."
            )
            submit_button = st.form_submit_button("🔓 Acessar Dashboard", use_container_width=True)
            
            if submit_button:
                try:
                    correct_password = st.secrets["APP_PASSWORD"]
                except KeyError:
                    st.error("⚠️ Erro de Configuração: O segredo 'APP_PASSWORD' não foi localizado nas configurações (secrets) do Streamlit.")
                    return False
                
                if password.strip() == correct_password.strip():
                    st.session_state["authenticated"] = True
                    st.success("✅ Autenticado com sucesso! Carregando painel...")
                    st.rerun()
                else:
                    st.error("❌ Senha incorreta. Verifique suas credenciais (por exemplo, espaços em branco ou maiúsculas/minúsculas) e tente novamente.")
                    
    return False
