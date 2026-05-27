import os
import hashlib
import streamlit as st
from config import CUSTOM_CSS
from core.database import get_db_connection, init_directories, clear_all_memory
from core.pipeline import run_etl_pipeline
from ui.components import inject_theme_styles, render_header
from ui.filters import render_filters
from ui.dashboard import (
    render_overview_tab,
    render_errors_tab,
    render_entities_tab,
    render_logs_table_tab,
    render_observability_tab
)
from utils.telemetry import Timer

# 1. Configuração de página widescreen premium
st.set_page_config(
    page_title="Inteligência Operacional ANTT/CIOT",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializa diretórios do sistema
init_directories()

# Injeta CSS Global
inject_theme_styles()

# Conecta ao banco de dados DuckDB
conn = get_db_connection()

# Painel de Administração - Limpar Memória
with st.sidebar:
    st.markdown("### ⚙️ Administração")
    if st.button("🧹 Limpar Memória / Resetar", help="Deleta todos os arquivos temporários, logs carregados e limpa o cache da aplicação."):
        clear_all_memory(conn)
        st.success("Memória limpa! Recarregando...")
        st.rerun()

# Cabeçalho da aplicação
render_header(
    "PLATAFORMA DE INTELIGÊNCIA OPERACIONAL ANTT/CIOT",
    "Analytics Corporativo, Insights de Suporte, Causa Raiz e Prevenção de Erros"
)

# 2. Seção de Upload
uploaded_file = st.file_uploader(
    "Carregar arquivo de Log da ANTT (Formatos aceitos: CSV ou XLSX)",
    type=["csv", "xlsx", "xls"],
    help="O arquivo deve conter as colunas de logs da ANTT (cod_mensagem, des_resposta, contratante, protocolo, data, funcionalidade)."
)

if uploaded_file is not None:
    # Calcula hash MD5 direto na memória
    file_bytes = uploaded_file.getvalue()
    file_hash = hashlib.md5(file_bytes).hexdigest()
    
    # Salva o arquivo na pasta uploads/ para a camada RAW se ainda não existir
    file_name_clean = "".join([c if c.isalnum() or c in [".", "_", "-"] else "_" for c in uploaded_file.name])
    temp_file_path = os.path.join("uploads", f"{file_hash}_{file_name_clean}")
    
    if not os.path.exists(temp_file_path):
        with open(temp_file_path, "wb") as f:
            f.write(file_bytes)
            
    # Executa o Pipeline ETL com Medição de Tempo
    with Timer("ETL Pipeline Completo", {"filename": uploaded_file.name, "hash": file_hash}):
        with st.spinner("Processando e Normalizando logs com Polars (Alta Performance)..."):
            try:
                stats = run_etl_pipeline(temp_file_path, file_hash, conn)
                
                # Armazena estado na session_state para sabermos qual hash está carregado
                st.session_state["loaded_file_hash"] = file_hash
                st.session_state["loaded_file_name"] = uploaded_file.name
                st.session_state["total_logs"] = stats["total_logs"]
                st.session_state["unique_protocols"] = stats["unique_protocols"]
                
                # Se mudou o arquivo, reseta as opções de filtro em cache para recalculá-las
                if "last_hash" not in st.session_state or st.session_state["last_hash"] != file_hash:
                    st.session_state["last_hash"] = file_hash
                    if "filter_options" in st.session_state:
                        del st.session_state["filter_options"]
                        
            except Exception as e:
                st.error(f"Erro fatal no processamento do arquivo: {str(e)}")
                st.session_state["loaded_file_hash"] = None

    # Exibe informações do arquivo carregado se o processamento foi bem-sucedido
    if st.session_state.get("loaded_file_hash") == file_hash:
        st.success(
            f"Arquivo **{st.session_state['loaded_file_name']}** processado com sucesso! "
            f"Total de logs normalizados: **{st.session_state['total_logs']:,}**. "
            f"Protocolos únicos: **{st.session_state['unique_protocols']:,}**."
            .replace(",", ".")
        )
        
        # 3. Renderiza filtros na sidebar e recebe a cláusula WHERE do SQL
        where_clause = render_filters(conn)
        
        # 4. Navegação por Abas Principais
        tab_overview, tab_errors, tab_entities, tab_observability, tab_table = st.tabs([
            "📈 Visão Geral", 
            "🏢 Diagnóstico por Contratante", 
            "⚠️ Entidades Críticas",
            "🛠️ Observabilidade & Correlação",
            "📋 Tabela de Logs"
        ])
        
        with tab_overview:
            render_overview_tab(conn, where_clause)
            
        with tab_errors:
            render_errors_tab(conn, where_clause)
            
        with tab_entities:
            render_entities_tab(conn, where_clause)
            
        with tab_observability:
            render_observability_tab(conn, where_clause)
            
        with tab_table:
            render_logs_table_tab(conn, where_clause)
            
else:
    # Estado inicial - Prompt para upload
    st.info("Aguardando upload de logs para iniciar a análise analítica.")
    st.markdown(
        """
        ### Estrutura de Log Esperada:
        A ferramenta processará automaticamente logs estruturados ou semi-estruturados contendo as colunas:
        * **protocolo**: Código identificador único da transação.
        * **data**: Data e hora da ocorrência.
        * **contratante**: Identificação do contratante do serviço (CPF/CNPJ).
        * **funcionalidade**: Operação ANTT sendo realizada (ex: Emitir CIOT, Encerrar CIOT).
        * **cod_mensagem**: Código de resposta do sistema da ANTT. Pode ser um JSON estruturado.
        * **des_resposta**: Descrição detalhada do erro ou retorno do sistema da ANTT. Pode conter JSONs com erros em lote.
        """
    )
