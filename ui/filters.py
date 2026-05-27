import streamlit as st
from datetime import datetime

def init_filter_options(conn):
    """
    Busca as opções de filtro baseadas na nova modelagem semântica e as armazena
    na session_state para evitar consultas repetitivas de DISTINCT.
    """
    if "filter_options" not in st.session_state:
        # Busca datas min e max
        dates = conn.execute("SELECT MIN(data_evento), MAX(data_evento) FROM dim_log;").fetchone()
        min_date = dates[0] if dates[0] else datetime.now()
        max_date = dates[1] if dates[1] else datetime.now()
        
        # Busca outros campos distintos
        contratantes = [row[0] for row in conn.execute("SELECT DISTINCT contratante FROM dim_log WHERE contratante IS NOT NULL ORDER BY contratante;").fetchall()]
        funcionalidades = [row[0] for row in conn.execute("SELECT DISTINCT funcionalidade FROM dim_log WHERE funcionalidade IS NOT NULL ORDER BY funcionalidade;").fetchall()]
        causas = [row[0] for row in conn.execute("SELECT DISTINCT causa_raiz FROM fact_rejeicoes_semanticas WHERE causa_raiz IS NOT NULL ORDER BY causa_raiz;").fetchall()]
        rejeicoes = [row[0] for row in conn.execute("SELECT DISTINCT tipo_rejeicao_semantica FROM fact_rejeicoes_semanticas WHERE tipo_rejeicao_semantica IS NOT NULL ORDER BY tipo_rejeicao_semantica;").fetchall()]
        codigos = [row[0] for row in conn.execute("SELECT DISTINCT codigo_antt FROM fact_rejeicoes_semanticas WHERE codigo_antt IS NOT NULL AND codigo_antt != '' ORDER BY codigo_antt;").fetchall()]
        
        st.session_state["filter_options"] = {
            "min_date": min_date,
            "max_date": max_date,
            "contratantes": contratantes,
            "funcionalidades": funcionalidades,
            "causas": causas,
            "rejeicoes": rejeicoes,
            "codigos": codigos
        }

def render_filters(conn) -> str:
    """
    Renderiza os filtros na barra lateral do Streamlit.
    Retorna uma cláusula SQL WHERE contendo subqueries para filtrar a tabela 'dim_log p'.
    """
    # Inicializa as opções se necessário
    init_filter_options(conn)
    opts = st.session_state["filter_options"]
    
    st.sidebar.markdown("### 🔍 Filtros Operacionais")
    
    # 1. Filtro de Período
    try:
        min_d = opts["min_date"].date() if isinstance(opts["min_date"], datetime) else opts["min_date"]
        max_d = opts["max_date"].date() if isinstance(opts["max_date"], datetime) else opts["max_date"]
        
        if min_d == max_d:
            date_range = st.sidebar.date_input("Período", [min_d])
        else:
            date_range = st.sidebar.date_input("Período", [min_d, max_d])
    except Exception:
        date_range = st.sidebar.date_input("Período", [])
        
    # 2. Pesquisa de Protocolo
    protocol_search = st.sidebar.text_input("Buscar Protocolo (Exato/Parcial)", "")
    
    # 3. Pesquisa de Mensagem de Erro
    message_search = st.sidebar.text_input("Buscar Texto na Mensagem", "")
    
    # 4. Filtro de Status
    status_options = ["TODOS", "SUCESSO", "ERRO"]
    status_sel = st.sidebar.selectbox("Status Geral", status_options)
    
    # 5. Contratantes
    contratante_sel = st.sidebar.multiselect("Contratante (Cliente)", opts["contratantes"])
    
    # 6. Funcionalidades
    funcionalidade_sel = st.sidebar.multiselect("Funcionalidade", opts["funcionalidades"])
    
    # 7. Causas Raiz
    causa_sel = st.sidebar.multiselect("Causa Raiz", opts["causas"])
    
    # 8. Rejeições Semânticas
    rejeicao_sel = st.sidebar.multiselect("Tipo de Rejeição", opts["rejeicoes"])
    
    # 9. Códigos ANTT
    codigo_sel = st.sidebar.multiselect("Código da Mensagem", opts["codigos"])
    
    # Construção da Cláusula SQL WHERE
    where_parts = ["1=1"]
    
    # Filtro de Data
    if len(date_range) == 2:
        start_dt = datetime.combine(date_range[0], datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        end_dt = datetime.combine(date_range[1], datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")
        where_parts.append(f"p.data_evento BETWEEN '{start_dt}' AND '{end_dt}'")
    elif len(date_range) == 1:
        start_dt = datetime.combine(date_range[0], datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        end_dt = datetime.combine(date_range[0], datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")
        where_parts.append(f"p.data_evento BETWEEN '{start_dt}' AND '{end_dt}'")
        
    # Filtro Protocolo
    if protocol_search.strip():
        p_clean = protocol_search.replace("'", "''")
        where_parts.append(f"p.protocolo LIKE '%{p_clean}%'")
        
    # Filtro Status Geral
    if status_sel != "TODOS":
        where_parts.append(f"p.status_geral = '{status_sel}'")
        
    # Filtro Contratantes
    if contratante_sel:
        contratantes_str = ", ".join(["'" + c.replace("'", "''") + "'" for c in contratante_sel])
        where_parts.append(f"p.contratante IN ({contratantes_str})")
        
    # Filtro Funcionalidades
    if funcionalidade_sel:
        func_str = ", ".join(["'" + f.replace("'", "''") + "'" for f in funcionalidade_sel])
        where_parts.append(f"p.funcionalidade IN ({func_str})")
        
    # Filtro de Causas Raiz (subquery para fact_rejeicoes_semanticas)
    if causa_sel:
        causas_str = ", ".join(["'" + c.replace("'", "''") + "'" for c in causa_sel])
        where_parts.append(f"p.log_id IN (SELECT log_id FROM fact_rejeicoes_semanticas WHERE causa_raiz IN ({causas_str}))")
        
    # Filtro de Rejeições Semânticas (subquery para fact_rejeicoes_semanticas)
    if rejeicao_sel:
        rejs_str = ", ".join(["'" + r.replace("'", "''") + "'" for r in rejeicao_sel])
        where_parts.append(f"p.log_id IN (SELECT log_id FROM fact_rejeicoes_semanticas WHERE tipo_rejeicao_semantica IN ({rejs_str}))")
        
    # Filtro de Códigos ANTT (subquery para fact_rejeicoes_semanticas)
    if codigo_sel:
        cods_str = ", ".join(["'" + c.replace("'", "''") + "'" for c in codigo_sel])
        where_parts.append(f"p.log_id IN (SELECT log_id FROM fact_rejeicoes_semanticas WHERE codigo_antt IN ({cods_str}))")
        
    # Filtro de Texto de Mensagem (subquery para fact_rejeicoes_semanticas)
    if message_search.strip():
        m_clean = message_search.replace("'", "''")
        where_parts.append(f"p.log_id IN (SELECT log_id FROM fact_rejeicoes_semanticas WHERE mensagem ILIKE '%{m_clean}%')")
        
    return " AND ".join(where_parts)
