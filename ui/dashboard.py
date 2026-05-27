import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import pandas as pd
from datetime import datetime
from ui.components import render_metric_card
from utils.exports import export_filtered_data_csv, export_filtered_data_xlsx

def render_overview_tab(conn, where_clause: str):
    """Renderiza o Painel Executivo de Inteligência Operacional ANTT/CIOT."""
    st.markdown("### 📊 Painel Executivo de Inteligência Operacional")
    
    # 1. Obter KPIs do DuckDB com uma única consulta agregada de alto desempenho
    kpis = conn.execute(f"""
        SELECT 
            COUNT(p.log_id) as total_requests,
            COUNT(DISTINCT p.protocolo) as unique_protocols,
            COUNT(DISTINCT p.contratante) as total_contratantes,
            COUNT(r.rejeicao_id) as total_rejections,
            COUNT(DISTINCT CASE WHEN r.rejeicao_id IS NOT NULL THEN p.contratante END) as clientes_afetados,
            COUNT(CASE WHEN r.categoria_operacional IN ('PLACA', 'LOCALIZAÇÃO', 'CARGA', 'VALIDAÇÃO', 'DATA', 'JANELA OPERACIONAL', 'TOLERÂNCIA') THEN 1 END) as count_evitavel,
            COUNT(CASE WHEN r.categoria_operacional IN ('TRANSPORTADOR', 'PAGAMENTO', 'CIOT') THEN 1 END) as count_parcial,
            COUNT(CASE WHEN r.categoria_operacional IN ('INTEGRAÇÃO', 'SISTEMA', 'OUTROS_NAO_CATEGORIZADO') THEN 1 END) as count_nao_evitavel,
            COUNT(CASE WHEN r.severidade = 'CRITICA' THEN 1 END) as count_critica,
            COUNT(CASE WHEN r.severidade = 'ALTA' THEN 1 END) as count_alta,
            COUNT(CASE WHEN r.severidade = 'MEDIA' THEN 1 END) as count_media,
            COUNT(CASE WHEN r.severidade = 'BAIXA' THEN 1 END) as count_baixa
        FROM dim_log p
        LEFT JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
        WHERE {where_clause};
    """).fetchone()
    
    total_logs, unique_protocols, total_contratantes, total_rejections, clientes_afetados, count_evitavel, count_parcial, count_nao_evitavel, count_critica, count_alta, count_media, count_baixa = kpis
    
    if total_logs == 0:
        st.info("Nenhum log encontrado para os filtros selecionados.")
        return
        
    # Calcular Score Operacional Geral
    penalties = (count_critica * 1.0) + (count_alta * 0.5) + (count_media * 0.2) + (count_baixa * 0.1)
    score_operacional = max(0.0, 100.0 - (penalties / total_logs) * 100.0) if total_logs > 0 else 100.0
    
    # Calcular taxa de reincidência de entidades
    reinc_query = conn.execute(f"""
        WITH entity_counts AS (
            SELECT e.entidade_valor, COUNT(*) as cnt
            FROM fact_entidades_extraidas e
            JOIN fact_rejeicoes_semanticas r ON r.rejeicao_id = e.rejeicao_id
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause}
            GROUP BY e.entidade_valor
        )
        SELECT 
            COALESCE(SUM(CASE WHEN cnt > 1 THEN cnt ELSE 0 END) * 100.0 / NULLIF(SUM(cnt), 0), 0.0) as reinc_rate
        FROM entity_counts;
    """).fetchone()
    reinc_rate = reinc_query[0] if reinc_query else 0.0
    
    # Top Causa Raiz
    top_causa_query = conn.execute(f"""
        SELECT r.categoria_operacional, COUNT(*) as volume
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause}
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 1;
    """).fetchone()
    top_causa = top_causa_query[0] if top_causa_query else "N/A"
    
    # Top Rejeição Semântica
    top_rejeicao_query = conn.execute(f"""
        SELECT r.tipo_rejeicao_semantica, COUNT(*) as volume
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause}
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 1;
    """).fetchone()
    top_rejeicao = top_rejeicao_query[0] if top_rejeicao_query else "N/A"
    
    # Porcentagem Evitável
    perc_evitavel = (count_evitavel * 100.0 / total_rejections) if total_rejections > 0 else 0.0
    
    # Renderizar Grade de KPIs (4x2)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric_card("Total de Rejeições", f"{total_rejections:,}".replace(",", "."), f"Em {total_logs:,} requisições", "down" if total_rejections > 0 else "info")
    with col2:
        render_metric_card("Erros Evitáveis", f"{perc_evitavel:.1f}%", f"{count_evitavel} falhas de cadastro/dados", "up" if perc_evitavel > 70 else "info")
    with col3:
        render_metric_card("Clientes Afetados", f"{clientes_afetados}", f"De {total_contratantes} ativos", "down" if clientes_afetados > 2 else "info")
    with col4:
        render_metric_card("Score Médio Geral", f"{score_operacional:.2f}%", f"Penalidades: {penalties:.1f}", "up" if score_operacional > 90 else "down")
        
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        render_metric_card("Taxa de Reincidência", f"{reinc_rate:.1f}%", "Falhas repetidas de entidades", "down" if reinc_rate > 30 else "up")
    with col6:
        render_metric_card("Top Causa Raiz", f"{top_causa}", "Categoria de erro principal", "info")
    with col7:
        render_metric_card("Top Rejeição", f"{top_rejeicao.replace('_', ' ')[:25]}", "Template semântico mais comum", "info")
    with col8:
        render_metric_card("Volume Total Logs", f"{total_logs:,}".replace(",", "."), f"{unique_protocols:,} protocolos", "info")
        
    # Painel de Auditoria
    with st.expander("🔍 Auditoria da Fórmula do Score Operacional"):
        st.markdown(
            f"""
            O **Score Operacional** mede a estabilidade da integração de logs reduzindo pontos com base na severidade das falhas:
            
            $$\\text{{Score}} = \\max\\left(0,\\, 100 - \\left( \\frac{{\\sum \\text{{Penalidades}}}}{{\\text{{Total de Requisições}}}} \\times 100 \\right)\\right)$$
            
            **Detalhamento Geral da Operação:**
            * **Total de Requisições:** `{total_logs}`
            * **Rejeições por Severidade:**
              * 🛑 **CRÍTICA (-1.0):** `{count_critica}` ocorrências
              * ⚠️ **ALTA (-0.5):** `{count_alta}` ocorrências
              * 🟡 **MÉDIA (-0.2):** `{count_media}` ocorrências
              * 🟢 **BAIXA (-0.1):** `{count_baixa}` ocorrências
            * **Soma Total de Penalidades:** `{penalties:.1f}` pontos
            * **Cálculo Aplicado:**
              $$Score = \\max\\left(0,\\, 100 - \\left( \\frac{{{penalties:.1f}}}{{{total_logs}}} \\times 100 \\right)\\right) = {score_operacional:.2f}\\%$$
            """
        )
        
    st.markdown("---")
    # Seção 2: Top 10 Contratantes e Top 10 Rejeições
    gcol1, gcol2 = st.columns([1.2, 1])
    
    with gcol1:
        st.markdown("##### 🏆 Top 10 Contratantes com Mais Rejeições")
        st.caption("Ranking de clientes ordenado por volume de rejeições baseado em protocolos únicos.")
        df_top_clients = conn.execute(f"""
            WITH client_rejections AS (
                SELECT 
                    p.contratante,
                    COUNT(DISTINCT p.protocolo) as total_rejeicoes,
                    COUNT(DISTINCT p.protocolo) * 100.0 / SUM(COUNT(DISTINCT p.protocolo)) OVER () as percentual
                FROM dim_log p
                JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
                WHERE {where_clause}
                GROUP BY p.contratante
            ),
            client_score AS (
                SELECT 
                    p.contratante,
                    COUNT(p.log_id) as total_logs,
                    COUNT(CASE WHEN r.severidade = 'CRITICA' THEN 1 END) as count_critica,
                    COUNT(CASE WHEN r.severidade = 'ALTA' THEN 1 END) as count_alta,
                    COUNT(CASE WHEN r.severidade = 'MEDIA' THEN 1 END) as count_media,
                    COUNT(CASE WHEN r.severidade = 'BAIXA' THEN 1 END) as count_baixa
                FROM dim_log p
                LEFT JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
                WHERE {where_clause}
                GROUP BY p.contratante
            ),
            client_top_rejection AS (
                SELECT 
                    contratante,
                    tipo_rejeicao_semantica as principal_rejeicao,
                    ROW_NUMBER() OVER (PARTITION BY contratante ORDER BY COUNT(*) DESC) as rn
                FROM dim_log p
                JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
                WHERE {where_clause}
                GROUP BY contratante, tipo_rejeicao_semantica
            ),
            client_top_func AS (
                SELECT 
                    contratante,
                    funcionalidade as principal_funcionalidade,
                    ROW_NUMBER() OVER (PARTITION BY contratante ORDER BY COUNT(*) DESC) as rn
                FROM dim_log p
                JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
                WHERE {where_clause}
                GROUP BY contratante, funcionalidade
            )
            SELECT 
                cr.contratante as "Contratante",
                cr.total_rejeicoes as "Total Rejeições",
                cr.percentual as "Percentual do Total",
                MAX(GREATEST(0.0, 100.0 - ((cs.count_critica * 1.0 + cs.count_alta * 0.5 + cs.count_media * 0.2 + cs.count_baixa * 0.1) / NULLIF(cs.total_logs, 0)) * 100.0)) as "Score Operacional",
                tr.principal_rejeicao as "Principal Rejeição",
                tf.principal_funcionalidade as "Principal Funcionalidade"
            FROM client_rejections cr
            JOIN client_score cs ON cr.contratante = cs.contratante
            LEFT JOIN client_top_rejection tr ON cr.contratante = tr.contratante AND tr.rn = 1
            LEFT JOIN client_top_func tf ON cr.contratante = tf.contratante AND tf.rn = 1
            GROUP BY cr.contratante, cr.total_rejeicoes, cr.percentual, tr.principal_rejeicao, tf.principal_funcionalidade
            ORDER BY cr.total_rejeicoes DESC
            LIMIT 10;
        """).df()
        
        if not df_top_clients.empty:
            st.dataframe(
                df_top_clients,
                column_config={
                    "Total Rejeições": st.column_config.ProgressColumn(
                        "Total Rejeições",
                        format="%d",
                        min_value=0,
                        max_value=int(df_top_clients["Total Rejeições"].max())
                    ),
                    "Percentual do Total": st.column_config.NumberColumn(
                        "Percentual",
                        format="%.1f%%"
                    ),
                    "Score Operacional": st.column_config.NumberColumn(
                        "Score",
                        format="%.1f%%"
                    )
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Nenhum dado de cliente disponível.")

    with gcol2:
        st.markdown("##### 🏆 Top 10 Rejeições Semânticas")
        st.caption("Rejeições semânticas oficiais mais ocorrentes ordenadas por volume.")
        df_top_rejs = conn.execute(f"""
            SELECT 
                r.tipo_rejeicao_semantica, 
                COUNT(*) as volume,
                COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentual
            FROM fact_rejeicoes_semanticas r
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause}
            GROUP BY 1
            ORDER BY 2 DESC
            LIMIT 10;
        """).df()
        
        if not df_top_rejs.empty:
            fig_top_rejs = px.bar(
                df_top_rejs,
                x="volume",
                y="tipo_rejeicao_semantica",
                orientation="h",
                text=df_top_rejs.apply(lambda r: f"{r['volume']} ({r['percentual']:.1f}%)", axis=1),
                color="volume",
                color_continuous_scale="Viridis",
                labels={"volume": "Volume de Ocorrências", "tipo_rejeicao_semantica": "Rejeição Semântica"}
            )
            fig_top_rejs.update_layout(
                yaxis=dict(autorange="reversed"),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#ffffff',
                showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
                coloraxis_showscale=False
            )
            st.plotly_chart(fig_top_rejs, use_container_width=True)
        else:
            st.success("Nenhuma rejeição encontrada no filtro atual.")
            
    st.markdown("---")
    
    # Seção 3: Top Funcionalidades e Matriz de Impacto
    gcol_f1, gcol_f2 = st.columns([1.2, 1])
    
    with gcol_f1:
        st.markdown("##### ⚡ Top Funcionalidades com Mais Rejeições")
        st.caption("Volumetria de erros cadastrais e de sistema agrupados por endpoint operacional.")
        df_top_funcs = conn.execute(f"""
            WITH func_base AS (
                SELECT 
                    p.funcionalidade,
                    COUNT(DISTINCT p.protocolo) as quantidade_erros,
                    COUNT(DISTINCT p.protocolo) * 100.0 / SUM(COUNT(DISTINCT p.protocolo)) OVER () as percentual
                FROM dim_log p
                JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
                WHERE {where_clause}
                GROUP BY p.funcionalidade
            ),
            func_top_rejection AS (
                SELECT 
                    p.funcionalidade,
                    r.tipo_rejeicao_semantica as principal_rejeicao,
                    ROW_NUMBER() OVER (PARTITION BY p.funcionalidade ORDER BY COUNT(*) DESC) as rn
                FROM dim_log p
                JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
                WHERE {where_clause}
                GROUP BY p.funcionalidade, r.tipo_rejeicao_semantica
            ),
            func_top_sev AS (
                SELECT 
                    p.funcionalidade,
                    r.severidade,
                    ROW_NUMBER() OVER (PARTITION BY p.funcionalidade ORDER BY COUNT(*) DESC) as rn
                FROM dim_log p
                JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
                WHERE {where_clause}
                GROUP BY p.funcionalidade, r.severidade
            )
            SELECT 
                fb.funcionalidade as "Funcionalidade",
                fb.quantidade_erros as "Quantidade Erros",
                fb.percentual as "Percentual",
                tr.principal_rejeicao as "Principal Rejeição",
                ts.severidade as "Severidade Predominante"
            FROM func_base fb
            LEFT JOIN func_top_rejection tr ON fb.funcionalidade = tr.funcionalidade AND tr.rn = 1
            LEFT JOIN func_top_sev ts ON fb.funcionalidade = ts.funcionalidade AND ts.rn = 1
            ORDER BY fb.quantidade_erros DESC;
        """).df()
        
        if not df_top_funcs.empty:
            fig_top_funcs = px.bar(
                df_top_funcs,
                x="Quantidade Erros",
                y="Funcionalidade",
                orientation="h",
                text=df_top_funcs.apply(lambda r: f"{r['Quantidade Erros']} ({r['Percentual']:.1f}%)", axis=1),
                color="Quantidade Erros",
                color_continuous_scale="Reds",
                hover_data=["Principal Rejeição", "Severidade Predominante"],
                labels={"Quantidade Erros": "Quantidade de Erros", "Funcionalidade": "Funcionalidade"}
            )
            fig_top_funcs.update_layout(
                yaxis=dict(autorange="reversed"),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#ffffff',
                showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
                coloraxis_showscale=False
            )
            st.plotly_chart(fig_top_funcs, use_container_width=True)
        else:
            st.info("Nenhum dado de funcionalidade disponível.")
            
    with gcol_f2:
        st.markdown("##### 🎯 Matriz de Impacto e Severidade")
        st.caption("Cruzamento de volume (X) vs severidade (Y) para identificar falhas críticas silenciosas ou massivas.")
        df_bubble = conn.execute(f"""
            SELECT 
                r.tipo_rejeicao_semantica,
                COUNT(r.rejeicao_id) as volume,
                r.severidade,
                COUNT(DISTINCT p.contratante) as clientes_impactados
            FROM fact_rejeicoes_semanticas r
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause}
            GROUP BY 1, 3
            ORDER BY volume DESC;
        """).df()
        
        if not df_bubble.empty:
            fig_bubble = px.scatter(
                df_bubble,
                x="volume",
                y="severidade",
                size="clientes_impactados",
                color="severidade",
                hover_name="tipo_rejeicao_semantica",
                size_max=35,
                color_discrete_map={"CRITICA": "#ef4444", "ALTA": "#f97316", "MEDIA": "#eab308", "BAIXA": "#3b82f6"},
                labels={"volume": "Volume de Ocorrências", "severidade": "Severidade (Impacto)", "clientes_impactados": "Clientes Impactados"},
                category_orders={"severidade": ["BAIXA", "MEDIA", "ALTA", "CRITICA"]}
            )
            fig_bubble.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#ffffff',
                margin=dict(t=10, b=10, l=10, r=10),
                xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
                yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)')
            )
            st.plotly_chart(fig_bubble, use_container_width=True)
        else:
            st.info("Matriz indisponível sem dados de falhas.")
            
    st.markdown("---")
    
    # Seção 4: Evitabilidade e Qualidade Cadastral
    gcol3, gcol4 = st.columns([1, 1])
    
    with gcol3:
        st.markdown("##### 🍩 Evitabilidade das Rejeições")
        st.caption("Classificação operacional para guiar estratégias de redução de chamados e suporte.")
        df_evit = conn.execute(f"""
            SELECT 
                CASE 
                    WHEN r.categoria_operacional IN ('PLACA', 'LOCALIZAÇÃO', 'CARGA', 'VALIDAÇÃO', 'DATA', 'JANELA OPERACIONAL', 'TOLERÂNCIA') THEN 'Evitável (Dados/Cadastro)'
                    WHEN r.categoria_operacional IN ('TRANSPORTADOR', 'PAGAMENTO', 'CIOT') THEN 'Parcialmente Evitável (Processo)'
                    ELSE 'Não Evitável (Integração/Sistema)'
                END as classe_evitabilidade,
                COUNT(*) as total
            FROM fact_rejeicoes_semanticas r
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause}
            GROUP BY 1;
        """).df()
        
        if not df_evit.empty:
            fig_donut = px.pie(
                df_evit,
                values="total",
                names="classe_evitabilidade",
                hole=0.5,
                color="classe_evitabilidade",
                color_discrete_map={
                    "Evitável (Dados/Cadastro)": "#10b981", 
                    "Parcialmente Evitável (Processo)": "#f59e0b", 
                    "Não Evitável (Integração/Sistema)": "#ef4444"
                }
            )
            fig_donut.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#ffffff',
                margin=dict(t=10, b=10, l=10, r=10),
                legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_donut, use_container_width=True)
        else:
            st.success("Zero erros cadastrais/processuais.")
            
    with gcol4:
        st.markdown("##### 📈 Maturidade Cadastral Global")
        st.caption("Índice de conformidade do cadastro por tipo de dado (taxa de sucesso cadastral).")
        
        df_quality = conn.execute(f"""
            SELECT
                100.0 - (COUNT(CASE WHEN r.tipo_rejeicao_semantica = 'PLACA_SEM_VINCULO_RNTRC' THEN 1 END) * 100.0 / NULLIF(COUNT(p.log_id), 0)) as placa_qualidade,
                100.0 - (COUNT(CASE WHEN r.tipo_rejeicao_semantica = 'TRANSPORTADOR_NAO_ENCONTRADO' THEN 1 END) * 100.0 / NULLIF(COUNT(p.log_id), 0)) as rntrc_qualidade,
                100.0 - (COUNT(CASE WHEN r.tipo_rejeicao_semantica = 'LOCALIZACAO_ORIGEM_INVALIDA' THEN 1 END) * 100.0 / NULLIF(COUNT(p.log_id), 0)) as cep_qualidade,
                100.0 - (COUNT(CASE WHEN r.tipo_rejeicao_semantica = 'MUNICIPIO_DESTINO_INVALIDO' THEN 1 END) * 100.0 / NULLIF(COUNT(p.log_id), 0)) as municipio_qualidade
            FROM dim_log p
            LEFT JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
            WHERE {where_clause}
        """).df()
        
        if not df_quality.empty:
            placa_q = max(0.0, min(100.0, df_quality.iloc[0]["placa_qualidade"]))
            rntrc_q = max(0.0, min(100.0, df_quality.iloc[0]["rntrc_qualidade"]))
            cep_q = max(0.0, min(100.0, df_quality.iloc[0]["cep_qualidade"]))
            mun_q = max(0.0, min(100.0, df_quality.iloc[0]["municipio_qualidade"]))
            
            st.write(f"**Qualidade de Placas (Vínculo ANTT):** {placa_q:.1f}%")
            st.progress(placa_q / 100.0)
            
            st.write(f"**Qualidade de RNTRCs (Transportador Ativo):** {rntrc_q:.1f}%")
            st.progress(rntrc_q / 100.0)
            
            st.write(f"**Qualidade de CEPs (Geolocalização):** {cep_q:.1f}%")
            st.progress(cep_q / 100.0)
            
            st.write(f"**Qualidade de Municípios (Cód IBGE):** {mun_q:.1f}%")
            st.progress(mun_q / 100.0)
        else:
            st.info("Métricas cadastrais indisponíveis.")
            
    st.markdown("---")
    
    # Seção 5: Sankey Diagram de Fluxo Operacional
    st.markdown("##### 🔀 Sankey Operacional: Rastreabilidade e Fluxo de Rejeições")
    st.caption("Fluxo analítico: Funcionalidade ➔ Tipo Rejeição ➔ Causa Raiz ➔ Entidade Afetada (Top 5 + OUTROS).")
    
    df_sankey = conn.execute(f"""
        SELECT 
            p.funcionalidade,
            r.tipo_rejeicao_semantica,
            r.causa_raiz,
            COALESCE(e.entidade_valor, 'SEM ENTIDADE') as entidade_valor,
            COUNT(*) as volume
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        LEFT JOIN fact_entidades_extraidas e ON r.rejeicao_id = e.rejeicao_id
        WHERE {where_clause}
        GROUP BY 1, 2, 3, 4
        ORDER BY volume DESC
        LIMIT 100;
    """).df()
    
    if not df_sankey.empty:
        # Agrupar entidades menores em "OUTROS"
        entity_counts = df_sankey[df_sankey["entidade_valor"] != 'SEM ENTIDADE'].groupby("entidade_valor")["volume"].sum()
        if not entity_counts.empty:
            top_5_entities = entity_counts.nlargest(5).index
            df_sankey["entidade_valor_grouped"] = df_sankey["entidade_valor"].apply(
                lambda x: x if x in top_5_entities or x == 'SEM ENTIDADE' else 'OUTROS ENTIDADES'
            )
        else:
            df_sankey["entidade_valor_grouped"] = 'SEM ENTIDADE'
            
        df_sankey_clean = df_sankey.groupby(
            ["funcionalidade", "tipo_rejeicao_semantica", "causa_raiz", "entidade_valor_grouped"]
        )["volume"].sum().reset_index()
        
        # Limita para visualização limpa
        df_sankey_clean = df_sankey_clean.nlargest(20, "volume")
        
        if not df_sankey_clean.empty:
            nodes_func = [f"F: {x}" for x in df_sankey_clean["funcionalidade"].unique()]
            nodes_rej = [f"R: {x}" for x in df_sankey_clean["tipo_rejeicao_semantica"].unique()]
            nodes_causa = [f"C: {x}" for x in df_sankey_clean["causa_raiz"].unique()]
            nodes_ent = [f"E: {x}" for x in df_sankey_clean["entidade_valor_grouped"].unique()]
            
            all_nodes = nodes_func + nodes_rej + nodes_causa + nodes_ent
            node_idx = {name: i for i, name in enumerate(all_nodes)}
            
            sources = []
            targets = []
            values = []
            
            # Link 1: Funcionalidade -> Tipo Rejeicao
            df_link1 = df_sankey_clean.groupby(["funcionalidade", "tipo_rejeicao_semantica"])["volume"].sum().reset_index()
            for _, row in df_link1.iterrows():
                sources.append(node_idx[f"F: {row['funcionalidade']}"])
                targets.append(node_idx[f"R: {row['tipo_rejeicao_semantica']}"])
                values.append(row["volume"])
                
            # Link 2: Tipo Rejeicao -> Causa Raiz
            df_link2 = df_sankey_clean.groupby(["tipo_rejeicao_semantica", "causa_raiz"])["volume"].sum().reset_index()
            for _, row in df_link2.iterrows():
                sources.append(node_idx[f"R: {row['tipo_rejeicao_semantica']}"])
                targets.append(node_idx[f"C: {row['causa_raiz']}"])
                values.append(row["volume"])
                
            # Link 3: Causa Raiz -> Entidade
            df_link3 = df_sankey_clean.groupby(["causa_raiz", "entidade_valor_grouped"])["volume"].sum().reset_index()
            for _, row in df_link3.iterrows():
                sources.append(node_idx[f"C: {row['causa_raiz']}"])
                targets.append(node_idx[f"E: {row['entidade_valor_grouped']}"])
                values.append(row["volume"])
                
            fig_sankey = go.Figure(data=[go.Sankey(
                node = dict(
                    pad = 15,
                    thickness = 15,
                    line = dict(color = "black", width = 0.5),
                    label = [x.split(": ", 1)[-1].replace("_", " ") for x in all_nodes],
                    color = "#6366f1"
                ),
                link = dict(
                    source = sources,
                    target = targets,
                    value = values,
                    color = "rgba(99, 102, 241, 0.15)"
                )
            )])
            fig_sankey.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#ffffff',
                height=350,
                margin=dict(t=20, b=20, l=10, r=10)
            )
            st.plotly_chart(fig_sankey, use_container_width=True)
        else:
            st.info("Fluxo Sankey indisponível.")
    else:
        st.info("Fluxo Sankey indisponível.")
        
    # Seção 5: Observabilidade Temporal (Apenas se houver variabilidade real)
    st.markdown("---")
    
    # Verificar variabilidade temporal real
    distinct_days = conn.execute(f"""
        SELECT COUNT(DISTINCT date_trunc('day', p.data_evento))
        FROM dim_log p
        WHERE {where_clause};
    """).fetchone()[0]
    
    distinct_hours = conn.execute(f"""
        SELECT COUNT(DISTINCT date_trunc('hour', p.data_evento))
        FROM dim_log p
        WHERE {where_clause};
    """).fetchone()[0]
    
    if distinct_days is not None and (distinct_days > 1 or (distinct_hours is not None and distinct_hours >= 4)):
        st.markdown("##### 📈 Evolução Temporal de Rejeições por Causa Raiz")
        date_diff = conn.execute(f"""
            SELECT date_diff('day', MIN(p.data_evento), MAX(p.data_evento))
            FROM dim_log p
            WHERE {where_clause};
        """).fetchone()[0]
        
        trunc_unit = "day"
        date_format = "%Y-%m-%d"
        if date_diff is not None and date_diff <= 3:
            trunc_unit = "hour"
            date_format = "%Y-%m-%d %H:00"
            
        df_temporal = conn.execute(f"""
            SELECT 
                strftime(date_trunc('{trunc_unit}', p.data_evento), '{date_format}') as periodo,
                r.categoria_operacional as causa_raiz,
                COUNT(*) as total
            FROM fact_rejeicoes_semanticas r
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause}
            GROUP BY 1, 2
            ORDER BY 1;
        """).df()
        
        if not df_temporal.empty:
            fig_line = px.area(
                df_temporal,
                x="periodo",
                y="total",
                color="causa_raiz",
                color_discrete_sequence=px.colors.qualitative.Safe,
                labels={"periodo": "Período", "total": "Ocorrências"}
            )
            fig_line.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#ffffff',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
                margin=dict(t=10, b=10, l=10, r=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("ℹ️ Baixa variabilidade temporal detectada nos logs selecionados. Evolução temporal oculta para evitar gráficos de linha achatados.")

def render_errors_tab(conn, where_clause: str):
    """Renderiza o Diagnóstico por Contratante com Score em Gauge e rankings."""
    st.markdown("### 🏢 Diagnóstico Analítico por Contratante")
    
    # 1. Busca lista de contratantes disponíveis
    contratantes = [row[0] for row in conn.execute(f"SELECT DISTINCT contratante FROM dim_log p WHERE {where_clause} ORDER BY 1;").fetchall()]
    
    if not contratantes:
        st.info("Nenhum contratante mapeado nos filtros atuais.")
        return
        
    selected_client = st.selectbox("Selecione o Contratante (Cliente)", contratantes)
    
    st.markdown(f"#### Diagnóstico Operacional: `{selected_client}`")
    
    # 2. Obter estatísticas do cliente selecionado
    total_client = conn.execute(f"""
        SELECT COUNT(*) FROM dim_log p 
        WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}';
    """).fetchone()[0]
    
    if total_client == 0:
        st.info("Nenhum log encontrado para este contratante nos filtros atuais.")
        return
        
    # Severidades do cliente para o Score
    sev_client = conn.execute(f"""
        SELECT 
            COUNT(CASE WHEN r.severidade = 'CRITICA' THEN 1 END) as count_critica,
            COUNT(CASE WHEN r.severidade = 'ALTA' THEN 1 END) as count_alta,
            COUNT(CASE WHEN r.severidade = 'MEDIA' THEN 1 END) as count_media,
            COUNT(CASE WHEN r.severidade = 'BAIXA' THEN 1 END) as count_baixa
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}';
    """).fetchone()
    
    c_critica, c_alta, c_media, c_baixa = sev_client
    penalties_client = (c_critica * 1.0) + (c_alta * 0.5) + (c_media * 0.2) + (c_baixa * 0.1)
    score_client = max(0.0, 100.0 - (penalties_client / total_client) * 100.0)
    
    rejeicoes_client = conn.execute(f"""
        SELECT COUNT(*)
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}';
    """).fetchone()[0]
    
    # Qualidade Cadastral do Cliente
    cadastro_errors = conn.execute(f"""
        SELECT COUNT(*)
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}'
          AND r.categoria_operacional IN ('TRANSPORTADOR', 'GEOLOCALIZACAO', 'PLACA');
    """).fetchone()[0]
    perc_controlavel = (1.0 - (cadastro_errors / total_client)) * 100.0 if total_client > 0 else 100.0
    
    # Layout de KPIs de Nível Executivo e Gauge Chart
    gcol1, gcol2 = st.columns([1, 1.2])
    
    with gcol1:
        # Gauge chart de Plotly para visualização de score executivo
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = score_client,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Score de Saúde Operacional", 'font': {'size': 18, 'color': '#ffffff'}},
            gauge = {
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#ffffff"},
                'bar': {'color': "#6366f1"},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 2,
                'bordercolor': "rgba(255,255,255,0.05)",
                'steps': [
                    {'range': [0, 50], 'color': 'rgba(239, 68, 68, 0.2)'},
                    {'range': [50, 80], 'color': 'rgba(234, 179, 8, 0.2)'},
                    {'range': [80, 100], 'color': 'rgba(16, 185, 129, 0.2)'}
                ]
            }
        ))
        fig_gauge.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#ffffff',
            height=200,
            margin=dict(t=30, b=10, l=30, r=30)
        )
        st.plotly_chart(fig_gauge, use_container_width=True)
        
    with gcol2:
        kcol1, kcol2 = st.columns(2)
        with kcol1:
            render_metric_card("Requisições do Cliente", f"{total_client:,}".replace(",", "."), None, "info")
            render_metric_card("Total de Rejeições", f"{rejeicoes_client:,}".replace(",", "."), None, "down" if rejeicoes_client > 0 else "info")
        with kcol2:
            render_metric_card("Qualidade Cadastral", f"{perc_controlavel:.1f}%", "Evitabilidade de erros", "up" if perc_controlavel > 80 else "down")
            render_metric_card("Soma Penalidades", f"{penalties_client:.1f}", "Baseado em criticidade", "info")
            
    st.markdown("---")
    
    col_d1, col_d2 = st.columns(2)
    
    with col_d1:
        st.markdown("##### ⚠️ Reincidência de Entidades do Cliente")
        st.caption("Ranking das entidades do contratante com maior reincidência de erros operacionais no suporte.")
        df_reinc_client = conn.execute(f"""
            SELECT 
                e.entidade_tipo as "Tipo",
                e.entidade_valor as "Valor",
                COUNT(*) as "Total Falhas",
                MAX(r.tipo_rejeicao_semantica) as "Rejeição Predominante"
            FROM fact_entidades_extraidas e
            JOIN fact_rejeicoes_semanticas r ON r.rejeicao_id = e.rejeicao_id
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}'
            GROUP BY 1, 2
            ORDER BY 3 DESC
            LIMIT 8;
        """).df()
        
        if not df_reinc_client.empty:
            st.dataframe(
                df_reinc_client,
                column_config={
                    "Total Falhas": st.column_config.ProgressColumn(
                        "Total Falhas",
                        format="%d",
                        min_value=0,
                        max_value=int(df_reinc_client["Total Falhas"].max())
                    )
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("Nenhuma entidade reincidente detectada para este cliente!")
            
    with col_d2:
        st.markdown("##### 📊 Principais Categorias Operacionais de Erro")
        st.caption("Frequência de erros do cliente agrupada por Categoria de Causa Raiz.")
        df_rejs_client = conn.execute(f"""
            SELECT r.categoria_operacional as Categoria, COUNT(*) as volume
            FROM fact_rejeicoes_semanticas r
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}'
            GROUP BY 1
            ORDER BY 2 DESC;
        """).df()
        
        if not df_rejs_client.empty:
            fig_pareto = px.bar(
                df_rejs_client,
                x="volume",
                y="Categoria",
                orientation="h",
                color="volume",
                color_continuous_scale="Reds"
            )
            fig_pareto.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#ffffff',
                showlegend=False,
                xaxis_title="Ocorrências",
                yaxis_title=None,
                margin=dict(t=10, b=10, l=10, r=10),
                coloraxis_showscale=False
            )
            st.plotly_chart(fig_pareto, use_container_width=True)
        else:
            st.success("Cliente sem rejeições registradas no período!")
            
    st.markdown("---")
    
    # Painel de Ações Corretivas
    st.markdown("##### 🧭 Painel de Ações Corretivas de Suporte")
    st.caption("Ações proativas sugeridas para regularizar a operação do contratante.")
    
    df_actions = conn.execute(f"""
        SELECT 
            r.categoria_operacional as "Categoria",
            r.tipo_rejeicao_semantica as "Tipo Semântico",
            r.subtipo_rejeicao as "Subtipo",
            COUNT(*) as "Ocorrências",
            r.orientacao_operacional as "Ação Corretiva de Suporte",
            MAX(r.mensagem) as "Exemplo do Erro"
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}'
        GROUP BY 1, 2, 3, 5
        ORDER BY 4 DESC;
    """).df()
    
    if not df_actions.empty:
        st.dataframe(df_actions, use_container_width=True, hide_index=True)
    else:
        st.success("Nenhuma ação corretiva pendente!")

def render_entity_table(conn, title, entity_type, where_clause, key_prefix):
    st.markdown(f"##### {title}")
    
    # 1. Filtro local de pesquisa
    search_val = st.text_input(f"🔍 Filtrar por valor ({title.split()[-1]})", "", key=f"{key_prefix}_search")
    
    # Condições de filtro para o SQL
    if entity_type == 'DOC':
        cond = "e.entidade_tipo IN ('CPF', 'CNPJ', 'DOC')"
    elif entity_type == 'CEP_MUN':
        cond = "e.entidade_tipo IN ('CEP', 'MUNICIPIO')"
    else:
        cond = f"e.entidade_tipo = '{entity_type}'"
        
    if search_val.strip():
        search_escaped = search_val.replace("'", "''")
        cond += f" AND e.entidade_valor LIKE '%{search_escaped}%'"
        
    # Query de base
    sql_base = f"""
        WITH entity_base AS (
            SELECT 
                e.entidade_valor as entidade,
                COUNT(DISTINCT p.protocolo) as quantidade_rejeicoes,
                COUNT(DISTINCT p.contratante) as quantidade_clientes
            FROM fact_entidades_extraidas e
            JOIN fact_rejeicoes_semanticas r ON r.rejeicao_id = e.rejeicao_id
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause} AND {cond}
            GROUP BY 1
        ),
        entity_top_rejection AS (
            SELECT 
                e.entidade_valor as entidade,
                r.tipo_rejeicao_semantica as principal_rejeicao,
                ROW_NUMBER() OVER (PARTITION BY e.entidade_valor ORDER BY COUNT(*) DESC) as rn
            FROM fact_entidades_extraidas e
            JOIN fact_rejeicoes_semanticas r ON r.rejeicao_id = e.rejeicao_id
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause} AND {cond}
            GROUP BY e.entidade_valor, r.tipo_rejeicao_semantica
        ),
        entity_top_func AS (
            SELECT 
                e.entidade_valor as entidade,
                p.funcionalidade as principal_funcionalidade,
                ROW_NUMBER() OVER (PARTITION BY e.entidade_valor ORDER BY COUNT(*) DESC) as rn
            FROM fact_entidades_extraidas e
            JOIN fact_rejeicoes_semanticas r ON r.rejeicao_id = e.rejeicao_id
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause} AND {cond}
            GROUP BY e.entidade_valor, p.funcionalidade
        )
        SELECT 
            eb.entidade as "{title.split()[-1]}",
            eb.quantidade_rejeicoes as "Quantidade Rejeições",
            eb.quantidade_clientes as "Clientes Impactados",
            tr.principal_rejeicao as "Principal Rejeição",
            tf.principal_funcionalidade as "Principal Funcionalidade"
        FROM entity_base eb
        LEFT JOIN entity_top_rejection tr ON eb.entidade = tr.entidade AND tr.rn = 1
        LEFT JOIN entity_top_func tf ON eb.entidade = tf.entidade AND tf.rn = 1
        ORDER BY eb.quantidade_rejeicoes DESC;
    """
    
    df_entity = conn.execute(sql_base).df()
    
    if df_entity.empty:
        st.info("Nenhuma entidade encontrada para os critérios informados.")
        return
        
    # 2. Paginação
    limit = 10
    total_rows = df_entity.shape[0]
    total_pages = max(1, (total_rows + limit - 1) // limit)
    
    col_p1, col_p2 = st.columns([1, 1])
    with col_p1:
        page = st.number_input("Página", min_value=1, max_value=total_pages, value=1, step=1, key=f"{key_prefix}_page")
    with col_p2:
        st.write(f"Total: {total_rows} registros | Exibindo página {page} de {total_pages}")
        
    offset = (page - 1) * limit
    df_paged = df_entity.iloc[offset:offset+limit]
    
    st.dataframe(
        df_paged,
        column_config={
            "Quantidade Rejeições": st.column_config.ProgressColumn(
                "Quantidade Rejeições",
                format="%d",
                min_value=0,
                max_value=int(df_entity["Quantidade Rejeições"].max())
            )
        },
        use_container_width=True,
        hide_index=True
    )
    
    # 3. Exportação
    csv_data = df_entity.to_csv(sep=";", index=False, encoding="utf-8").encode("utf-8")
    st.download_button(
        label=f"📥 Exportar Todos ({total_rows}) para CSV",
        data=csv_data,
        file_name=f"export_{key_prefix}.csv",
        mime="text/csv",
        key=f"{key_prefix}_download"
    )

def render_entities_tab(conn, where_clause: str):
    """Renderiza a aba 'Entidades Críticas' como rankings visuais com tabelas agregadas e paginação."""
    st.markdown("### ⚠️ Entidades Críticas da Operação")
    st.caption("Visão analítica de dados em conflito cadastral na ANTT com paginação, filtros e exportação individual.")
    
    t_rntrc, t_placa, t_doc, t_cep = st.tabs([
        "🪪 Top RNTRCs Problemáticos",
        "🚚 Top Placas com Rejeição",
        "👥 Top CPF/CNPJ com Pendências",
        "📍 Top CEP/Município Inválido"
    ])
    
    with t_rntrc:
        render_entity_table(conn, "Top RNTRC", "RNTRC", where_clause, "rntrc")
        
    with t_placa:
        render_entity_table(conn, "Top Placa", "PLACA", where_clause, "placa")
        
    with t_doc:
        render_entity_table(conn, "Top Documento", "DOC", where_clause, "doc")
        
    with t_cep:
        render_entity_table(conn, "Top CEP/Município", "CEP_MUN", where_clause, "cep")

    # Série Temporal das Top 5 Entidades Críticas (Apenas se houver variabilidade)
    distinct_days = conn.execute(f"""
        SELECT COUNT(DISTINCT date_trunc('day', p.data_evento))
        FROM dim_log p
        WHERE {where_clause};
    """).fetchone()[0]
    
    distinct_hours = conn.execute(f"""
        SELECT COUNT(DISTINCT date_trunc('hour', p.data_evento))
        FROM dim_log p
        WHERE {where_clause};
    """).fetchone()[0]
    
    if distinct_days is not None and (distinct_days > 1 or (distinct_hours is not None and distinct_hours >= 4)):
        st.markdown("---")
        st.markdown("##### 📈 Tendência Temporal das Top 5 Entidades Críticas")
        df_top_ent = conn.execute(f"""
            SELECT e.entidade_valor, COUNT(*) as cnt
            FROM fact_entidades_extraidas e
            JOIN fact_rejeicoes_semanticas r ON r.rejeicao_id = e.rejeicao_id
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 5;
        """).df()
        
        if not df_top_ent.empty:
            top_list = df_top_ent["entidade_valor"].tolist()
            list_str = ", ".join([f"'{v.replace("'", "''")}'" for v in top_list])
            
            df_trend = conn.execute(f"""
                SELECT 
                    strftime(date_trunc('day', p.data_evento), '%Y-%m-%d') as "Dia",
                    e.entidade_valor as "Entidade",
                    COUNT(*) as "Total Falhas"
                FROM fact_entidades_extraidas e
                JOIN fact_rejeicoes_semanticas r ON r.rejeicao_id = e.rejeicao_id
                JOIN dim_log p ON p.log_id = r.log_id
                WHERE {where_clause} AND e.entidade_valor IN ({list_str})
                GROUP BY 1, 2 ORDER BY 1;
            """).df()
            
            if not df_trend.empty:
                fig_trend = px.line(
                    df_trend, x="Dia", y="Total Falhas", color="Entidade", markers=True,
                    color_discrete_sequence=px.colors.qualitative.Bold,
                    labels={"Dia": "Data", "Total Falhas": "Frequência de Falhas"}
                )
                fig_trend.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#ffffff',
                    xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
                    margin=dict(t=10, b=10, l=10, r=10)
                )
                st.plotly_chart(fig_trend, use_container_width=True)

def render_observability_tab(conn, where_clause: str):
    """Renderiza a Matriz Operacional Analítica (crosstab) e diagnósticos de observabilidade avançada."""
    st.markdown("### 🛠️ Observabilidade e Matriz Operacional Analítica")
    
    # Matriz Operacional Analítica (Tabela cruzada)
    st.markdown("##### 🗺️ Matriz Operacional Analítica: Cruzamento Clientes vs Rejeições")
    st.caption("Filtre e identifique rapidamente padrões de erro, clusters e clientes críticos.")
    
    # Controles de parametrização Top N configurável
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        top_n_clients = st.slider("Top N Contratantes (Linhas)", 5, 50, 20, step=5)
    with col_c2:
        top_n_rejections = st.slider("Top N Rejeições Semânticas (Colunas)", 5, 30, 15, step=5)
        
    df_matrix_raw = conn.execute(f"""
        SELECT p.contratante, r.tipo_rejeicao_semantica, COUNT(*) as total
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause}
        GROUP BY 1, 2;
    """).df()
    
    if not df_matrix_raw.empty:
        # Encontra os top N contratantes e top N rejeições por total de erros
        top_clients_list = df_matrix_raw.groupby("contratante")["total"].sum().nlargest(top_n_clients).index
        top_rejs_list = df_matrix_raw.groupby("tipo_rejeicao_semantica")["total"].sum().nlargest(top_n_rejections).index
        
        df_filtered = df_matrix_raw[df_matrix_raw["contratante"].isin(top_clients_list) & df_matrix_raw["tipo_rejeicao_semantica"].isin(top_rejs_list)]
        
        if not df_filtered.empty:
            df_pivot = df_filtered.pivot(index="contratante", columns="tipo_rejeicao_semantica", values="total").fillna(0)
            df_pivot = df_pivot.astype(int)
            
            # Estilização com gradiente de cor (heat coloring) usando pandas styling
            styled_matrix = df_pivot.style.background_gradient(cmap="PuBu", axis=None)
            st.dataframe(styled_matrix, use_container_width=True)
        else:
            st.info("Ocorrências insuficientes para gerar a matriz.")
    else:
        st.info("Matriz operacional indisponível.")
        
    st.markdown("---")
    
    col_a1, col_a2 = st.columns(2)
    
    with col_a1:
        st.markdown("##### 🚨 Alerta de Novos Códigos Não Categorizados")
        st.caption("Novas rejeições identificadas no log da ANTT sem mapeamento semântico.")
        df_new_codes = conn.execute(f"""
            SELECT 
                r.codigo_antt as "Código ANTT",
                MAX(r.mensagem_original) as "Descrição Original (Exemplo)",
                p.funcionalidade as "Funcionalidade",
                COUNT(*) as "Quantidade",
                MIN(p.data_evento) as "Primeira Ocorrência",
                MAX(p.data_evento) as "Última Ocorrência"
            FROM fact_rejeicoes_semanticas r
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause} AND r.tipo_rejeicao_semantica = 'OUTROS_NAO_CATEGORIZADO' AND r.codigo_antt != ''
            GROUP BY 1, 3
            ORDER BY 4 DESC;
        """).df()
        
        if not df_new_codes.empty:
            st.warning(f"Atenção: Foram detectados {df_new_codes.shape[0]} novos códigos não catalogados!")
            st.dataframe(df_new_codes, use_container_width=True, hide_index=True)
        else:
            st.success("Mapeamento semântico completo. Zero códigos desconhecidos nos logs!")
            
    with col_a2:
        # Verificar variabilidade temporal real
        distinct_days = conn.execute(f"""
            SELECT COUNT(DISTINCT date_trunc('day', p.data_evento))
            FROM dim_log p
            WHERE {where_clause};
        """).fetchone()[0]
        
        distinct_hours = conn.execute(f"""
            SELECT COUNT(DISTINCT date_trunc('hour', p.data_evento))
            FROM dim_log p
            WHERE {where_clause};
        """).fetchone()[0]
        
        if distinct_days is not None and (distinct_days > 1 or (distinct_hours is not None and distinct_hours >= 4)):
            st.markdown("##### 📉 Detecção de Anomalias de Tráfego")
            st.caption("Picos de erros operacionais anômalos por hora (Desvio Padrão > 2).")
            
            df_hourly_errors = conn.execute(f"""
                SELECT 
                    date_trunc('hour', p.data_evento) as hora,
                    COUNT(*) as total_erros
                FROM fact_rejeicoes_semanticas r
                JOIN dim_log p ON p.log_id = r.log_id
                WHERE {where_clause}
                GROUP BY 1 ORDER BY 1;
            """).df()
            
            if not df_hourly_errors.empty and df_hourly_errors.shape[0] > 2:
                pl_df = pl.from_pandas(df_hourly_errors)
                mean_errors = pl_df["total_erros"].mean()
                std_errors = pl_df["total_erros"].std()
                threshold = mean_errors + 2 * std_errors
                
                pl_anomalies = pl_df.filter(pl.col("total_erros") > threshold)
                
                if pl_anomalies.height > 0:
                    st.error(f"Picos críticos detectados: {pl_anomalies.height} picos anômalos de erro!")
                    st.dataframe(pl_anomalies.to_pandas(), use_container_width=True, hide_index=True)
                else:
                    st.success("Comportamento estável. Nenhuma anomalia de tráfego detectada.")
        else:
            st.info("Comportamento estável. Dados insuficientes para cálculo de desvio padrão.")

def render_logs_table_tab(conn, where_clause: str):
    """Renderiza a aba 'Tabela de Logs' para consulta detalhada com 18 colunas e filtros locais."""
    st.markdown("### 📋 Consulta de Requisições & Logs")
    
    # 1. Filtros Rápidos Locais
    st.markdown("##### 🔍 Filtros Rápidos Locais")
    col_lf1, col_lf2, col_lf3, col_lf4 = st.columns(4)
    
    with col_lf1:
        search_text = st.text_input("Pesquisa Textual (Protocolo/Mensagem/Valor)", "", key="local_search_text")
    with col_lf2:
        list_funcs = ["TODAS"] + [row[0] for row in conn.execute("SELECT DISTINCT funcionalidade FROM dim_log WHERE funcionalidade IS NOT NULL ORDER BY 1;").fetchall()]
        sel_func = st.selectbox("Funcionalidade", list_funcs, key="local_sel_func")
    with col_lf3:
        list_rejs = ["TODAS"] + [row[0] for row in conn.execute("SELECT DISTINCT tipo_rejeicao_semantica FROM fact_rejeicoes_semanticas WHERE tipo_rejeicao_semantica IS NOT NULL ORDER BY 1;").fetchall()]
        sel_rej = st.selectbox("Tipo de Rejeição", list_rejs, key="local_sel_rej")
    with col_lf4:
        list_clients = ["TODOS"] + [row[0] for row in conn.execute("SELECT DISTINCT contratante FROM dim_log WHERE contratante IS NOT NULL ORDER BY 1;").fetchall()]
        sel_client = st.selectbox("Contratante", list_clients, key="local_sel_client")
        
    # Construção da cláusula SQL com filtros locais combinados
    local_conds = [where_clause]
    if search_text.strip():
        s_clean = search_text.replace("'", "''")
        local_conds.append(f"(p.protocolo LIKE '%{s_clean}%' OR r.mensagem_original ILIKE '%{s_clean}%' OR e.entidade_valor LIKE '%{s_clean}%')")
    if sel_func != "TODAS":
        sel_func_escaped = sel_func.replace("'", "''")
        local_conds.append(f"p.funcionalidade = '{sel_func_escaped}'")
    if sel_rej != "TODAS":
        sel_rej_escaped = sel_rej.replace("'", "''")
        local_conds.append(f"r.tipo_rejeicao_semantica = '{sel_rej_escaped}'")
    if sel_client != "TODOS":
        sel_client_escaped = sel_client.replace("'", "''")
        local_conds.append(f"p.contratante = '{sel_client_escaped}'")
        
    combined_where = " AND ".join(local_conds)
    
    total_filtrados = conn.execute(f"""
        SELECT COUNT(*)
        FROM dim_log p
        LEFT JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
        LEFT JOIN fact_entidades_extraidas e ON r.rejeicao_id = e.rejeicao_id
        WHERE {combined_where};
    """).fetchone()[0]
    
    st.write(f"Encontrados {total_filtrados:,} registros.".replace(",", "."))
    
    limit = 50
    total_pages = max(1, (total_filtrados + limit - 1) // limit)
    
    col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])
    with col_pag2:
        page = st.number_input("Página", min_value=1, max_value=total_pages, value=1, step=1, key="logs_table_page")
        offset = (page - 1) * limit
        
    query_paginada = f"""
        SELECT 
            p.protocolo as "protocolo",
            p.data_evento as "data",
            p.contratante as "contratante",
            p.funcionalidade as "funcionalidade",
            p.status_geral as "status_geral",
            r.codigo_antt as "codigo_antt",
            r.tipo_rejeicao_semantica as "tipo_rejeicao_semantica",
            r.causa_raiz as "causa_raiz",
            r.orientacao_operacional as "orientacao_operacional",
            e.entidade_tipo as "entidade_tipo",
            e.entidade_valor as "entidade_valor",
            r.mensagem_original as "mensagem_original",
            r.severidade as "severidade",
            r.categoria_operacional as "categoria",
            CASE 
                WHEN r.severidade = 'CRITICA' THEN -1.0
                WHEN r.severidade = 'ALTA' THEN -0.5
                WHEN r.severidade = 'MEDIA' THEN -0.2
                WHEN r.severidade = 'BAIXA' THEN -0.1
                ELSE 0.0
            END as "score",
            r.subtipo_rejeicao as "rejeicao_oficial",
            r.mensagem_normalizada as "template_normalizado",
            p.log_id as "hash_evento"
        FROM dim_log p
        LEFT JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
        LEFT JOIN fact_entidades_extraidas e ON r.rejeicao_id = e.rejeicao_id
        WHERE {combined_where}
        ORDER BY p.data_evento DESC
        LIMIT {limit} OFFSET {offset};
    """
    
    df_logs = conn.execute(query_paginada).df()
    
    if not df_logs.empty:
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum log encontrado nesta página.")
        
    st.markdown("---")
    st.markdown("##### 📥 Exportar Dados Operacionais")
    st.caption("A exportação analítica consolida os logs e erros associados em um arquivo denormalizado de 18 colunas.")
    
    export_sql = f"""
        SELECT 
            p.protocolo,
            p.data_evento as data,
            p.contratante,
            p.funcionalidade,
            p.status_geral,
            r.rejeicao_id,
            r.log_id,
            r.codigo_antt,
            r.mensagem_original,
            r.mensagem_normalizada,
            r.template_oficial,
            r.tipo_rejeicao_semantica,
            r.subtipo_rejeicao as mensagem_padrao,
            r.categoria_operacional as categoria_oficial,
            r.causa_raiz,
            r.orientacao_operacional,
            r.severidade,
            (
                SELECT COALESCE(string_agg(e.entidade_tipo || ':' || e.entidade_valor, ' | '), '')
                FROM fact_entidades_extraidas e
                WHERE e.rejeicao_id = r.rejeicao_id
            ) as entidades_extraidas
        FROM dim_log p
        JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
        WHERE {where_clause}
        ORDER BY p.data_evento DESC
    """
    col_exp1, col_exp2 = st.columns(2)
    filter_key_suffix = str(hash(where_clause))
    
    with col_exp1:
        if st.button("Preparar CSV (Rápido - Alta Volumetria)", key="btn_csv_" + filter_key_suffix):
            with st.spinner("Gerando CSV..."):
                st.session_state["csv_ready_" + filter_key_suffix] = export_filtered_data_csv(conn, export_sql)
                
        if "csv_ready_" + filter_key_suffix in st.session_state:
            st.download_button(
                label="📥 Baixar Relatório CSV",
                data=st.session_state["csv_ready_" + filter_key_suffix],
                file_name=f"antt_semantic_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key="dl_csv_" + filter_key_suffix
            )
            
    with col_exp2:
        if st.button("Preparar Excel (XLSX)", key="btn_xlsx_" + filter_key_suffix):
            with st.spinner("Gerando Excel..."):
                st.session_state["xlsx_ready_" + filter_key_suffix] = export_filtered_data_xlsx(conn, export_sql)
                
        if "xlsx_ready_" + filter_key_suffix in st.session_state:
            st.download_button(
                label="📥 Baixar Relatório Excel (XLSX)",
                data=st.session_state["xlsx_ready_" + filter_key_suffix],
                file_name=f"antt_semantic_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_xlsx_" + filter_key_suffix
            )
