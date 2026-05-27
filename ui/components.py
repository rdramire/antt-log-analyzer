import streamlit as st
from config import CUSTOM_CSS

def inject_theme_styles():
    """Injeta os estilos CSS personalizados da aplicação."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

def render_metric_card(title: str, value: str, delta: str = None, trend: str = None):
    """
    Renderiza um card analítico premium com glassmorphism,
    sombreamento e micro-animações de hover.
    """
    delta_html = ""
    if delta:
        color = "#10b981" if trend == "up" else "#ef4444" if trend == "down" else "#94a3b8"
        icon = "▲" if trend == "up" else "▼" if trend == "down" else ""
        delta_html = f'<p style="margin: 0; font-size: 0.85rem; color: {color}; font-weight: 500;">{icon} {delta}</p>'
        
    card_html = f"""
    <div class="css-card-premium">
        <p style="margin: 0 0 8px 0; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; font-weight: 500;">
            {title}
        </p>
        <p style="margin: 0 0 4px 0; font-size: 1.8rem; font-weight: 700; color: #ffffff; line-height: 1.2;">
            {value}
        </p>
        {delta_html}
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

def render_header(title: str, subtitle: str):
    """Renderiza um cabeçalho premium com gradiente e descrição estilizada."""
    st.markdown(
        f"""
        <div style="margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.05);">
            <h1 style="margin: 0; background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.2rem; font-weight: 700;">
                {title}
            </h1>
            <p style="margin: 5px 0 0 0; color: #94a3b8; font-size: 1rem; font-weight: 300;">
                {subtitle}
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
