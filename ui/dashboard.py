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
    
    kpis = conn.execute(f"""
        SELECT 
            COUNT(p.log_id) as total_requests,
            COUNT(DISTINCT p.protocolo) as unique_protocols,
            COUNT(DISTINCT p.contratante) as total_contratantes,
            COUNT(CASE WHEN p.status_geral = 'SUCESSO' THEN 1 END) as count_sucesso,
            COUNT(CASE WHEN p.status_geral = 'ERRO' THEN 1 END) as count_erro,
            (
                SELECT COUNT(*) FROM (
                    SELECT p2.contratante 
                    FROM dim_log p2 
                    WHERE p2.status_geral = 'ERRO' AND {where_clause.replace("p.", "p2.")} 
                    GROUP BY p2.contratante 
                    HAVING COUNT(p2.log_id) >= 3
                )
            ) as clientes_afetados,
            COUNT(CASE WHEN r.severidade = 'CRITICO' AND p.status_geral = 'ERRO' THEN 1 END) as count_critico,
            COUNT(CASE WHEN r.severidade = 'ALTO' AND p.status_geral = 'ERRO' THEN 1 END) as count_alto,
            COUNT(CASE WHEN r.severidade = 'MEDIO' AND p.status_geral = 'ERRO' THEN 1 END) as count_medio,
            COUNT(CASE WHEN r.severidade = 'BAIXO' AND p.status_geral = 'ERRO' THEN 1 END) as count_baixo,
            COUNT(CASE WHEN p.status_geral = 'ERRO' AND r.categoria_operacional IN ('PLACA', 'LOCALIZAÇÃO', 'CARGA', 'VALIDAÇÃO', 'DATA', 'JANELA OPERACIONAL', 'TOLERÂNCIA') THEN 1 END) as count_evitavel,
            COUNT(CASE WHEN p.status_geral = 'ERRO' AND r.rejeicao_id IS NOT NULL THEN 1 END) as total_rejeicoes_fatos
        FROM dim_log p
        LEFT JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
        WHERE {where_clause};
    """).fetchone()
    
    total_logs, unique_protocols, total_contratantes, count_sucesso, count_erro, clientes_afetados, count_critico, count_alto, count_medio, count_baixo, count_evitavel, total_rejeicoes_fatos = kpis
    
    if total_logs == 0:
        st.info("Nenhum log encontrado para os filtros selecionados.")
        return
        
    # Calcular Score Operacional Geral
    penalties = (count_critico * 1.0) + (count_alto * 0.5) + (count_medio * 0.2) + (count_baixo * 0.1)
    score_operacional = max(0.0, 100.0 - (penalties / total_logs) * 100.0) if total_logs > 0 else 100.0
    
    # Taxas Executivas
    rate_sucesso = (count_sucesso * 100.0 / total_logs) if total_logs > 0 else 100.0
    rate_evitabilidade = (count_evitavel * 100.0 / count_erro) if count_erro > 0 else 0.0
    
    # Renderizar Grade de KPIs (5x1)
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        render_metric_card("Taxa Sucesso Operacional", f"{rate_sucesso:.1f}%", f"{count_sucesso} chamadas concluídas", "up" if rate_sucesso > 90 else "down")
    with col2:
        render_metric_card("Total de Rejeições", f"{count_erro}", f"{unique_protocols} protocolos únicos", "down" if count_erro > 0 else "info")
    with col3:
        render_metric_card("Clientes Afetados", f"{clientes_afetados}", f"De {total_contratantes} ativos", "down" if clientes_afetados > 2 else "info")
    with col4:
        render_metric_card("Score Operacional", f"{score_operacional:.2f}%", f"Penalidades: {penalties:.1f}", "up" if score_operacional > 90 else "down")
    with col5:
        render_metric_card("Taxa de Evitabilidade", f"{rate_evitabilidade:.1f}%", f"{count_evitavel} erros evitáveis", "info")
        
    # Painel de Auditoria
    with st.expander("🔍 Auditoria da Fórmula do Score Operacional"):
        st.markdown(
            f"""
            O **Score Operacional** mede a estabilidade da integração de logs reduzindo pontos com base na severidade das falhas:
            
            $$\\text{{Score}} = \\max\\left(0,\\, 100 - \\left( \\frac{{\\sum \\text{{Penalidades}}}}{{\\text{{Total de Requisições}}}} \\times 100 \\right)\\right)$$
            
            **Detalhamento Geral da Operação:**
            * **Total de Requisições:** `{total_logs}`
            * **Rejeições por Severidade:**
              * 🛑 **CRÍTICO (-1.0):** `{count_critico}` ocorrências
              * ⚠️ **ALTO (-0.5):** `{count_alto}` ocorrências
              * 🟡 **MÉDIO (-0.2):** `{count_medio}` ocorrências
              * 🟢 **BAIXO (-0.1):** `{count_baixo}` ocorrências
            * **Soma Total de Penalidades:** `{penalties:.1f}` pontos
            * **Cálculo Aplicado:**
              $$Score = \\max\\left(0,\\, 100 - \\left( \\frac{{{penalties:.1f}}}{{{total_logs}}} \\times 100 \\right)\\right) = {score_operacional:.2f}\\%$$
            """
        )
        
    st.markdown("---")
    
    # Seção: Insights Executivos Inteligentes e Diagnósticos Automáticos
    st.markdown("##### 💡 Insights Executivos e Diagnósticos Automáticos")
    top_causa_name = "N/A"
    top_causa_pct = 0.0
    top_causa_query = conn.execute(f"""
        SELECT r.categoria_operacional, COUNT(*) as errors
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause} AND p.status_geral = 'ERRO'
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 1;
    """).fetchone()
    if total_rejeicoes_fatos > 0 and top_causa_query:
        top_causa_name = top_causa_query[0]
        top_causa_pct = (top_causa_query[1] * 100.0 / total_rejeicoes_fatos)
        
    top_func_name = "N/A"
    top_func_pct = 0.0
    top_func_query = conn.execute(f"""
        SELECT p.funcionalidade, COUNT(p.log_id) as errors
        FROM dim_log p
        WHERE {where_clause} AND p.status_geral = 'ERRO'
        GROUP BY p.funcionalidade
        ORDER BY errors DESC
        LIMIT 1;
    """).fetchone()
    if count_erro > 0 and top_func_query:
        top_func_name = top_func_query[0]
        top_func_pct = (top_func_query[1] * 100.0 / count_erro)
        
    top2_share = 0.0
    num_top_clients = 0
    top_contratantes_share_query = conn.execute(f"""
        SELECT p.contratante, COUNT(DISTINCT p.protocolo) as errors
        FROM dim_log p
        WHERE {where_clause} AND p.status_geral = 'ERRO'
        GROUP BY p.contratante
        ORDER BY errors DESC
        LIMIT 2;
    """).fetchall()
    if count_erro > 0 and top_contratantes_share_query:
        top2_errors = sum(row[1] for row in top_contratantes_share_query)
        top2_share = (top2_errors * 100.0 / count_erro)
        num_top_clients = len(top_contratantes_share_query)

    insights_text = ""
    if count_erro > 0:
        insights_text += f"- 🎯 **{top_causa_pct:.1f}% das falhas** de negócio estão relacionadas a inconsistências de **{top_causa_name}**.\n"
        insights_text += f"- ⚡ A funcionalidade **{top_func_name}** é a mais problemática, concentrando **{top_func_pct:.1f}% dos erros** operacionais.\n"
        insights_text += f"- 🛡️ **{rate_evitabilidade:.1f}% das falhas** são classificadas como **evitáveis** por meio de saneamento cadastral na origem.\n"
        if num_top_clients > 0:
            insights_text += f"- 👥 Os **{num_top_clients} contratante(s) principal(is)** com pendências representa(m) **{top2_share:.1f}% de todas as rejeições** operacionais reais."
    else:
        insights_text = "✨ **Operação 100% Estável:** Nenhum erro registrado para o período ou filtros selecionados."
        
    st.info(insights_text)
    
    st.markdown("---")
    
    # Seção 2: Top 10 Contratantes e Top 10 Rejeições
    gcol1, gcol2 = st.columns([1.2, 1])
    
    with gcol1:
        st.markdown("##### 🏆 Top 10 Contratantes com Mais Rejeições")
        st.caption("Clientes que apresentam maior volume de falhas operacionais baseado em protocolos únicos.")
        df_top_clients = conn.execute(f"""
            WITH client_rejections AS (
                SELECT 
                    p.contratante,
                    COUNT(DISTINCT p.protocolo) as total_rejeicoes,
                    COUNT(DISTINCT p.protocolo) * 100.0 / SUM(COUNT(DISTINCT p.protocolo)) OVER () as percentual
                FROM dim_log p
                WHERE {where_clause} AND p.status_geral = 'ERRO'
                GROUP BY p.contratante
            ),
            client_score AS (
                SELECT 
                    p.contratante,
                    COUNT(p.log_id) as total_logs,
                    COUNT(CASE WHEN r.severidade = 'CRITICO' AND p.status_geral = 'ERRO' THEN 1 END) as count_critico,
                    COUNT(CASE WHEN r.severidade = 'ALTO' AND p.status_geral = 'ERRO' THEN 1 END) as count_alto,
                    COUNT(CASE WHEN r.severidade = 'MEDIO' AND p.status_geral = 'ERRO' THEN 1 END) as count_medio,
                    COUNT(CASE WHEN r.severidade = 'BAIXO' AND p.status_geral = 'ERRO' THEN 1 END) as count_baixo
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
                WHERE {where_clause} AND p.status_geral = 'ERRO'
                GROUP BY contratante, tipo_rejeicao_semantica
            ),
            client_top_func AS (
                SELECT 
                    contratante,
                    funcionalidade as principal_funcionalidade,
                    ROW_NUMBER() OVER (PARTITION BY contratante ORDER BY COUNT(*) DESC) as rn
                FROM dim_log p
                JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
                WHERE {where_clause} AND p.status_geral = 'ERRO'
                GROUP BY contratante, funcionalidade
            )
            SELECT 
                cr.contratante as "Contratante",
                cr.total_rejeicoes as "Total Rejeições",
                cr.percentual as "Percentual do Total",
                MAX(GREATEST(0.0, 100.0 - ((cs.count_critico * 1.0 + cs.count_alto * 0.5 + cs.count_medio * 0.2 + cs.count_baixo * 0.1) / NULLIF(cs.total_logs, 0)) * 100.0)) as "Score Operacional",
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
        st.caption("Rejeições semânticas da ANTT com maior volume de ocorrências.")
        df_top_rejs = conn.execute(f"""
            SELECT 
                r.tipo_rejeicao_semantica, 
                COUNT(*) as volume,
                COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentual
            FROM fact_rejeicoes_semanticas r
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause} AND p.status_geral = 'ERRO'
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
                color_continuous_scale="Reds",
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
    
    # Seção 3: Top Funcionalidades Problemáticas & Heatmap de Severidade
    gcol_f1, gcol_f2 = st.columns([1.2, 1])
    
    with gcol_f1:
        st.markdown("##### ⚡ Top Funcionalidades Problemáticas")
        st.caption("Endpoints operacionais ordenados pela quantidade absoluta de erros.")
        df_top_funcs = conn.execute(f"""
            WITH func_err_metrics AS (
                SELECT 
                    p.funcionalidade,
                    COUNT(p.log_id) as total_chamadas,
                    COUNT(CASE WHEN p.status_geral = 'ERRO' THEN 1 END) as total_erros
                FROM dim_log p
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
                WHERE {where_clause} AND p.status_geral = 'ERRO'
                GROUP BY p.funcionalidade, r.tipo_rejeicao_semantica
            ),
            func_top_severity AS (
                SELECT 
                    p.funcionalidade,
                    r.severidade as severidade_predominante,
                    ROW_NUMBER() OVER (PARTITION BY p.funcionalidade ORDER BY COUNT(*) DESC) as rn
                FROM dim_log p
                JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
                WHERE {where_clause} AND p.status_geral = 'ERRO'
                GROUP BY p.funcionalidade, r.severidade
            )
            SELECT 
                fm.funcionalidade as "Funcionalidade",
                fm.total_erros as "Total Erros",
                (fm.total_erros * 100.0 / NULLIF(fm.total_chamadas, 0)) as "Taxa Erro (%)",
                COALESCE(tr.principal_rejeicao, 'Nenhuma') as "Principal Rejeição",
                COALESCE(ts.severidade_predominante, 'INFO') as "Severidade Predominante"
            FROM func_err_metrics fm
            LEFT JOIN func_top_rejection tr ON fm.funcionalidade = tr.funcionalidade AND tr.rn = 1
            LEFT JOIN func_top_severity ts ON fm.funcionalidade = ts.funcionalidade AND ts.rn = 1
            WHERE fm.total_erros > 0
            ORDER BY fm.total_erros DESC;
        """).df()
        
        if not df_top_funcs.empty:
            st.dataframe(
                df_top_funcs,
                column_config={
                    "Total Erros": st.column_config.NumberColumn("Erros", format="%d"),
                    "Taxa Erro (%)": st.column_config.NumberColumn("Taxa Erro", format="%.1f%%")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("Operação normalizada: Zero erros por funcionalidade.")
            
    with gcol_f2:
        st.markdown("##### 🎯 Heatmap de Severidade e Concentração de Erros")
        st.caption("Concentração de falhas severas mapeadas pelas principais funcionalidades (Top 10).")
        
        df_heatmap_raw = conn.execute(f"""
            SELECT 
                p.funcionalidade,
                r.severidade,
                COUNT(r.rejeicao_id) as volume
            FROM dim_log p
            JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
            WHERE {where_clause} AND p.status_geral = 'ERRO'
            GROUP BY 1, 2
            ORDER BY volume DESC;
        """).df()
        
        if not df_heatmap_raw.empty:
            # Seleciona as top 10 funcionalidades com mais erros
            top_funcs_heatmap = df_heatmap_raw.groupby("funcionalidade")["volume"].sum().nlargest(10).index
            df_heatmap_filtered = df_heatmap_raw[df_heatmap_raw["funcionalidade"].isin(top_funcs_heatmap)]
            
            df_pivot = df_heatmap_filtered.pivot(index="funcionalidade", columns="severidade", values="volume").fillna(0).astype(int)
            
            # Garante e ordena colunas
            for c in ["BAIXO", "MEDIO", "ALTO", "CRITICO"]:
                if c not in df_pivot.columns:
                    df_pivot[c] = 0
            df_pivot = df_pivot[["BAIXO", "MEDIO", "ALTO", "CRITICO"]]
            
            fig_heatmap = px.imshow(
                df_pivot,
                labels=dict(x="Severidade", y="Funcionalidade", color="Volume Erros"),
                x=df_pivot.columns,
                y=df_pivot.index,
                color_continuous_scale="Reds",
                aspect="auto",
                text_auto=True
            )
            fig_heatmap.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#ffffff',
                margin=dict(t=10, b=10, l=10, r=10),
                coloraxis_showscale=False
            )
            st.plotly_chart(fig_heatmap, use_container_width=True)
        else:
            st.info("Heatmap indisponível sem dados de falhas.")
            
    st.markdown("---")
    
    # Seção 4: Evitabilidade e Qualidade Cadastral
    gcol3, gcol4 = st.columns([1, 1])
    
    with gcol3:
        st.markdown("##### 📊 Evitabilidade das Rejeições")
        st.caption("Classificação operacional recomendada para ações corretivas de suporte.")
        df_evit = conn.execute(f"""
            SELECT 
                CASE 
                    WHEN r.categoria_operacional IN ('PLACA', 'LOCALIZAÇÃO', 'CARGA', 'VALIDAÇÃO', 'DATA', 'JANELA OPERACIONAL', 'TOLERÂNCIA') THEN 'Evitável (Dados/Cadastro)'
                    WHEN r.categoria_operacional IN ('TRANSPORTADOR', 'PAGAMENTO', 'CIOT') THEN 'Parcialmente Evitável (Processo)'
                    WHEN r.categoria_operacional IN ('INTEGRAÇÃO', 'INTEGRACAO', 'SISTEMA') THEN 'Não Evitável (Integração/Sistema)'
                    ELSE 'Não Classificado'
                END as classe_evitabilidade,
                COUNT(*) as total
            FROM fact_rejeicoes_semanticas r
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE {where_clause} AND p.status_geral = 'ERRO'
            GROUP BY 1;
        """).df()
        
        if not df_evit.empty:
            total_evit = df_evit["total"].sum()
            df_evit["percentual"] = df_evit["total"].apply(lambda x: (x * 100.0 / total_evit) if total_evit > 0 else 0.0)
            
            desc_map = {
                'Evitável (Dados/Cadastro)': 'Evitável: Erros causados por dados incorretos ou inconsistências cadastrais.',
                'Parcialmente Evitável (Processo)': 'Parcialmente Evitável: Rejeições cadastrais do transportador ou do RNTRC.',
                'Não Evitável (Integração/Sistema)': 'Não Evitável: Instabilidade, timeouts ou falhas de rede da ANTT.',
                'Não Classificado': 'Não Classificado: Outras mensagens sem categorização de evitabilidade definida.'
            }
            df_evit["descricao"] = df_evit["classe_evitabilidade"].map(desc_map)
            
            fig_evit_bars = px.bar(
                df_evit,
                x="total",
                y="classe_evitabilidade",
                orientation="h",
                text=df_evit.apply(lambda r: f"{r['total']} ({r['percentual']:.1f}%)", axis=1),
                color="classe_evitabilidade",
                color_discrete_map={
                    "Evitável (Dados/Cadastro)": "#10b981", 
                    "Parcialmente Evitável (Processo)": "#f59e0b", 
                    "Não Evitável (Integração/Sistema)": "#ef4444",
                    "Não Classificado": "#6b7280"
                },
                hover_data=["descricao"],
                labels={"total": "Volume de Erros", "classe_evitabilidade": "Evitabilidade"}
            )
            fig_evit_bars.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#ffffff',
                showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
                xaxis_title="Volume de Ocorrências",
                yaxis_title=None
            )
            st.plotly_chart(fig_evit_bars, use_container_width=True)
        else:
            st.success("Zero erros registrados no período.")
            
    with gcol4:
        st.markdown("##### 📈 Maturidade Cadastral Global")
        st.caption("Conformidade cadastral real calculada por domínio operacional de erros cadastrados.")
        
        df_quality = conn.execute(f"""
            SELECT
                -- Placa Quality
                COUNT(CASE WHEN r.categoria_operacional = 'PLACA' AND p.status_geral = 'ERRO' THEN 1 END) as placa_sem_vinculo,
                COUNT(CASE WHEN p.funcionalidade IN ('Emitir CIOT', 'Retificar CIOT') THEN 1 END) as total_operacoes_placa,
                
                -- RNTRC Quality
                COUNT(CASE WHEN (r.categoria_operacional = 'TRANSPORTADOR' OR r.tipo_rejeicao_semantica IN ('TRANSPORTADOR_NAO_ENCONTRADO', 'RNTRC_INATIVO')) AND p.status_geral = 'ERRO' AND EXISTS (SELECT 1 FROM fact_entidades_extraidas e WHERE e.rejeicao_id = r.rejeicao_id AND e.entidade_tipo = 'RNTRC') THEN 1 END) as rntrc_sem_cadastro,
                COUNT(CASE WHEN p.funcionalidade IN ('Emitir CIOT', 'Retificar CIOT', 'Consultar CIOT') THEN 1 END) as total_operacoes_rntrc,
                
                -- CEP Quality
                COUNT(CASE WHEN (r.categoria_operacional IN ('GEOLOCALIZACAO', 'LOCALIZAÇÃO') OR r.tipo_rejeicao_semantica IN ('LOCALIZACAO_ORIGEM_INVALIDA', 'CEP_NAO_CADASTRADO')) AND p.status_geral = 'ERRO' AND EXISTS (SELECT 1 FROM fact_entidades_extraidas e WHERE e.rejeicao_id = r.rejeicao_id AND e.entidade_tipo = 'CEP') THEN 1 END) as cep_invalido,
                COUNT(CASE WHEN p.funcionalidade IN ('Emitir CIOT', 'Retificar CIOT') THEN 1 END) as total_operacoes_cep,
                
                -- Município Quality
                COUNT(CASE WHEN (r.categoria_operacional IN ('GEOLOCALIZACAO', 'LOCALIZAÇÃO') OR r.tipo_rejeicao_semantica IN ('MUNICIPIO_DESTINO_INVALIDO', 'MUNICIPIO_INVALIDO')) AND p.status_geral = 'ERRO' AND EXISTS (SELECT 1 FROM fact_entidades_extraidas e WHERE e.rejeicao_id = r.rejeicao_id AND e.entidade_tipo = 'MUNICIPIO') THEN 1 END) as municipio_invalido,
                COUNT(CASE WHEN p.funcionalidade IN ('Emitir CIOT', 'Retificar CIOT') THEN 1 END) as total_operacoes_municipio,
                
                -- CPF/CNPJ Quality
                COUNT(CASE WHEN (r.categoria_operacional = 'TRANSPORTADOR' OR r.tipo_rejeicao_semantica = 'TRANSPORTADOR_NAO_ENCONTRADO') AND p.status_geral = 'ERRO' AND EXISTS (SELECT 1 FROM fact_entidades_extraidas e WHERE e.rejeicao_id = r.rejeicao_id AND e.entidade_tipo IN ('CPF', 'CNPJ', 'DOC')) THEN 1 END) as cpf_cnpj_invalido,
                COUNT(CASE WHEN p.funcionalidade IN ('Emitir CIOT', 'Retificar CIOT', 'Consultar CIOT') THEN 1 END) as total_operacoes_cpf_cnpj
            FROM dim_log p
            LEFT JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
            WHERE {where_clause}
        """).df()
        
        if not df_quality.empty:
            row = df_quality.iloc[0]
            
            # Placa
            if row["total_operacoes_placa"] > 0:
                placa_q = max(0.0, 100.0 * (1.0 - (row["placa_sem_vinculo"] / row["total_operacoes_placa"])))
                st.write(f"**Qualidade de Placas (Vínculo ANTT):** {placa_q:.1f}%")
                st.progress(placa_q / 100.0)
            else:
                st.write("**Qualidade de Placas (Vínculo ANTT):** Sem operações registradas")
                st.progress(0.0)
                
            # RNTRC
            if row["total_operacoes_rntrc"] > 0:
                rntrc_q = max(0.0, 100.0 * (1.0 - (row["rntrc_sem_cadastro"] / row["total_operacoes_rntrc"])))
                st.write(f"**Qualidade de RNTRCs (Transportador Ativo):** {rntrc_q:.1f}%")
                st.progress(rntrc_q / 100.0)
            else:
                st.write("**Qualidade de RNTRCs (Transportador Ativo):** Sem operações registradas")
                st.progress(0.0)
                
            # CEP
            if row["total_operacoes_cep"] > 0:
                cep_q = max(0.0, 100.0 * (1.0 - (row["cep_invalido"] / row["total_operacoes_cep"])))
                st.write(f"**Qualidade de CEPs (Geolocalização):** {cep_q:.1f}%")
                st.progress(cep_q / 100.0)
            else:
                st.write("**Qualidade de CEPs (Geolocalização):** Sem operações registradas")
                st.progress(0.0)
                
            # Município
            if row["total_operacoes_municipio"] > 0:
                mun_q = max(0.0, 100.0 * (1.0 - (row["municipio_invalido"] / row["total_operacoes_municipio"])))
                st.write(f"**Qualidade de Municípios (Cód IBGE):** {mun_q:.1f}%")
                st.progress(mun_q / 100.0)
            else:
                st.write("**Qualidade de Municípios (Cód IBGE):** Sem operações registradas")
                st.progress(0.0)
                
            # CPF/CNPJ
            if row["total_operacoes_cpf_cnpj"] > 0:
                doc_q = max(0.0, 100.0 * (1.0 - (row["cpf_cnpj_invalido"] / row["total_operacoes_cpf_cnpj"])))
                st.write(f"**Qualidade de CPF/CNPJ (Contratado):** {doc_q:.1f}%")
                st.progress(doc_q / 100.0)
            else:
                st.write("**Qualidade de CPF/CNPJ (Contratado):** Sem operações registradas")
                st.progress(0.0)
        else:
            st.info("Métricas cadastrais indisponíveis.")
            
    st.markdown("---")
    
    # Seção 5: Sankey Diagram de Fluxo Operacional
    st.markdown("##### 🔀 Sankey Operacional: Rastreabilidade e Fluxo de Rejeições")
    st.caption("Fluxo analítico simplificado: Funcionalidade ➔ Tipo Rejeição ➔ Causa Raiz.")
    
    df_sankey = conn.execute(f"""
        SELECT 
            p.funcionalidade,
            COALESCE(r.tipo_rejeicao_semantica, r.tipo_erro_tecnico, 'OUTROS_NAO_CATEGORIZADO') as tipo_rejeicao,
            r.causa_raiz,
            COUNT(*) as volume
        FROM dim_log p
        JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
        WHERE {where_clause} AND p.status_geral = 'ERRO' 
          AND COALESCE(r.tipo_rejeicao_semantica, '') NOT IN ('SUCESSO_GERACAO', 'SUCESSO_INSERCAO', 'SUCESSO')
        GROUP BY 1, 2, 3
        ORDER BY volume DESC;
    """).df()
    
    if not df_sankey.empty:
        # Top 5 funcionalidades
        top_funcs = df_sankey.groupby("funcionalidade")["volume"].sum().nlargest(5).index
        # Top 7 rejections
        top_rejs = df_sankey.groupby("tipo_rejeicao")["volume"].sum().nlargest(7).index
        # Top 5 causes
        top_causas = df_sankey.groupby("causa_raiz")["volume"].sum().nlargest(5).index
        
        df_sankey["func_grouped"] = df_sankey["funcionalidade"].apply(lambda x: x if x in top_funcs else "OUTROS")
        df_sankey["rej_grouped"] = df_sankey["tipo_rejeicao"].apply(lambda x: x if x in top_rejs else "OUTROS")
        df_sankey["causa_grouped"] = df_sankey["causa_raiz"].apply(lambda x: x if x in top_causas else "OUTROS")
        
        df_sankey_clean = df_sankey.groupby(
            ["func_grouped", "rej_grouped", "causa_grouped"]
        )["volume"].sum().reset_index()
        
        # Limita para visualização limpa
        df_sankey_clean = df_sankey_clean.nlargest(20, "volume")
        
        if not df_sankey_clean.empty:
            nodes_func = [f"F: {x}" for x in df_sankey_clean["func_grouped"].unique()]
            nodes_rej = [f"R: {x}" for x in df_sankey_clean["rej_grouped"].unique()]
            nodes_causa = [f"C: {x}" for x in df_sankey_clean["causa_grouped"].unique()]
            
            all_nodes = nodes_func + nodes_rej + nodes_causa
            node_idx = {name: i for i, name in enumerate(all_nodes)}
            
            sources = []
            targets = []
            values = []
            
            # Link 1: Funcionalidade -> Tipo Rejeicao
            df_link1 = df_sankey_clean.groupby(["func_grouped", "rej_grouped"])["volume"].sum().reset_index()
            for _, row in df_link1.iterrows():
                sources.append(node_idx[f"F: {row['func_grouped']}"])
                targets.append(node_idx[f"R: {row['rej_grouped']}"])
                values.append(row["volume"])
                
            # Link 2: Tipo Rejeicao -> Causa Raiz
            df_link2 = df_sankey_clean.groupby(["rej_grouped", "causa_grouped"])["volume"].sum().reset_index()
            for _, row in df_link2.iterrows():
                sources.append(node_idx[f"R: {row['rej_grouped']}"])
                targets.append(node_idx[f"C: {row['causa_grouped']}"])
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
        
    # Seção 6: Observabilidade Temporal
    st.markdown("---")
    
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
            WHERE {where_clause} AND p.status_geral = 'ERRO'
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
            COUNT(CASE WHEN r.severidade = 'CRITICO' THEN 1 END) as count_critica,
            COUNT(CASE WHEN r.severidade = 'ALTO' THEN 1 END) as count_alta,
            COUNT(CASE WHEN r.severidade = 'MEDIO' THEN 1 END) as count_media,
            COUNT(CASE WHEN r.severidade = 'BAIXO' THEN 1 END) as count_baixa
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}';
    """).fetchone()
    
    c_critica, c_alta, c_media, c_baixa = sev_client
    penalties_client = (c_critica * 1.0) + (c_alta * 0.5) + (c_media * 0.2) + (c_baixa * 0.1)
    score_client = max(0.0, 100.0 - (penalties_client / total_client) * 100.0) if total_client > 0 else 100.0
    
    rejeicoes_client = conn.execute(f"""
        SELECT COUNT(*)
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}'
          AND r.resultado_operacional = 'REJEICAO_NEGOCIO';
    """).fetchone()[0]
    
    erros_tecnicos_client = conn.execute(f"""
        SELECT COUNT(*)
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}'
          AND r.resultado_operacional IN ('ERRO_TECNICO', 'ERRO_INFRAESTRUTURA');
    """).fetchone()[0]
    
    # Qualidade Cadastral do Cliente (rejeições de dados reais)
    cadastro_errors = conn.execute(f"""
        SELECT COUNT(*)
        FROM fact_rejeicoes_semanticas r
        JOIN dim_log p ON p.log_id = r.log_id
        WHERE {where_clause} AND p.contratante = '{selected_client.replace("'", "''")}'
          AND r.categoria_operacional IN ('TRANSPORTADOR', 'GEOLOCALIZACAO', 'PLACA')
          AND r.resultado_operacional = 'REJEICAO_NEGOCIO';
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
            render_metric_card("Rejeições (Negócio)", f"{rejeicoes_client:,}".replace(",", "."), None, "down" if rejeicoes_client > 0 else "info")
        with kcol2:
            render_metric_card("Erros Técnicos/Infra", f"{erros_tecnicos_client:,}".replace(",", "."), None, "down" if erros_tecnicos_client > 0 else "info")
            render_metric_card("Qualidade Cadastral", f"{perc_controlavel:.1f}%", "Evitabilidade de erros", "up" if perc_controlavel > 80 else "down")
            
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
              AND r.resultado_operacional = 'REJEICAO_NEGOCIO'
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
              AND r.resultado_operacional = 'REJEICAO_NEGOCIO'
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
          AND r.resultado_operacional = 'REJEICAO_NEGOCIO'
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
            WHERE {where_clause} AND {cond} AND r.resultado_operacional = 'REJEICAO_NEGOCIO'
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
            WHERE {where_clause} AND {cond} AND r.resultado_operacional = 'REJEICAO_NEGOCIO'
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
            WHERE {where_clause} AND {cond} AND r.resultado_operacional = 'REJEICAO_NEGOCIO'
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
            WHERE {where_clause} AND r.resultado_operacional = 'REJEICAO_NEGOCIO'
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
                WHERE {where_clause} AND e.entidade_valor IN ({list_str}) AND r.resultado_operacional = 'REJEICAO_NEGOCIO'
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
        WHERE {where_clause} AND r.resultado_operacional = 'REJEICAO_NEGOCIO'
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
        local_conds.append(f"(p.protocolo LIKE '%{s_clean}%' OR r.mensagem_original ILIKE '%{s_clean}%' OR EXISTS (SELECT 1 FROM fact_entidades_extraidas e WHERE e.rejeicao_id = r.rejeicao_id AND e.entidade_valor LIKE '%{s_clean}%'))")
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
            p.resultado_operacional as "resultado_operacional",
            r.codigo_antt as "codigo_antt",
            r.tipo_rejeicao_semantica as "tipo_rejeicao_semantica",
            r.tipo_erro_tecnico as "tipo_erro_tecnico",
            r.causa_raiz as "causa_raiz",
            r.orientacao_operacional as "orientacao_operacional",
            (
                SELECT COALESCE(string_agg(e.entidade_tipo || ':' || e.entidade_valor, ' | '), '')
                FROM fact_entidades_extraidas e
                WHERE e.rejeicao_id = r.rejeicao_id
            ) as "entidades_extraidas",
            COALESCE(r.mensagem_original, 'Operação concluída com sucesso') as "mensagem_original",
            r.severidade as "severidade",
            r.categoria_operacional as "categoria",
            CASE 
                WHEN r.severidade = 'CRITICO' THEN -1.0
                WHEN r.severidade = 'ALTO' THEN -0.5
                WHEN r.severidade = 'MEDIO' THEN -0.2
                WHEN r.severidade = 'BAIXO' THEN -0.1
                ELSE 0.0
            END as "score",
            r.subtipo_rejeicao as "rejeicao_oficial",
            r.mensagem_normalizada as "template_normalizado",
            p.log_id as "hash_evento"
        FROM dim_log p
        LEFT JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
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
    st.caption("A exportação analítica consolida os logs e erros associados em um arquivo denormalizado contendo todo o contexto operacional.")
    
    export_sql = f"""
        SELECT 
            p.protocolo,
            p.data_evento as data,
            p.contratante,
            p.funcionalidade,
            p.status_geral,
            p.resultado_operacional,
            r.tipo_rejeicao_semantica,
            r.tipo_erro_tecnico,
            COALESCE(r.mensagem_original, 'Operação concluída com sucesso') as mensagem_original,
            COALESCE(r.mensagem_normalizada, 'Operação concluída com sucesso') as mensagem_normalizada,
            CASE WHEN p.status_geral = 'SUCESSO' THEN 'SIM' ELSE 'NÃO' END as indicador_sucesso,
            COALESCE(r.severidade, 'INFO') as severidade_operacional,
            COALESCE(r.codigo_antt, '') as codigo_antt,
            CASE WHEN p.resultado_operacional IN ('SUCESSO', 'SUCESSO_COM_ALERTA') THEN 'Sucesso Operacional' ELSE 'Erro/Falha' END as contexto_operacional,
            r.rejeicao_id,
            r.log_id,
            r.template_oficial,
            r.subtipo_rejeicao as mensagem_padrao,
            r.categoria_operacional as categoria_oficial,
            r.causa_raiz,
            r.orientacao_operacional,
            (
                SELECT COALESCE(string_agg(e.entidade_tipo || ':' || e.entidade_valor, ' | '), '')
                FROM fact_entidades_extraidas e
                WHERE e.rejeicao_id = r.rejeicao_id
            ) as entidades_extraidas
        FROM dim_log p
        LEFT JOIN fact_rejeicoes_semanticas r ON p.log_id = r.log_id
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

def render_normalized_rejections_tab(conn, where_clause: str):
    """Renderiza a aba 'Rejeições Normalizadas Consolidadas' com busca, paginação e exportação."""
    import io
    st.markdown("### 🔍 Rejeições Normalizadas Consolidadas")
    st.caption("Consolidação operacional de todas as ocorrências de rejeições ANTT utilizando exclusivamente a mensagem normalizada.")
    
    # 1. Filtro de Busca Textual Local
    search_text = st.text_input("🔍 Buscar na Funcionalidade / Mensagem Normalizada:", "", key="consolidated_search_text")
    
    # Construção da query SQL baseada em CTE
    search_cond = ""
    if search_text.strip():
        s_clean = search_text.replace("'", "''")
        search_cond = f"WHERE mensagem_normalizada ILIKE '%{s_clean}%' OR funcionalidade ILIKE '%{s_clean}%'"
        
    query = f"""
        WITH cohort_errors AS (
            SELECT
                CAST(p.data_evento AS DATE) AS data,
                p.funcionalidade,
                COALESCE(NULLIF(r.mensagem_normalizada, ''), 'Erro de sistema ou resposta vazia') AS mensagem_normalizada,
                COUNT(*) AS quantidade,
                ROUND(
                    COUNT(*) * 100.0 /
                    SUM(COUNT(*)) OVER (),
                    3
                ) AS percentual_representatividade
            FROM fact_rejeicoes_semanticas r
            JOIN dim_log p ON p.log_id = r.log_id
            WHERE p.status_geral = 'ERRO' AND {where_clause}
            GROUP BY 1, 2, 3
        )
        SELECT 
            data,
            funcionalidade,
            mensagem_normalizada,
            quantidade,
            percentual_representatividade AS "% representatividade"
        FROM cohort_errors
        {search_cond}
        ORDER BY data DESC, quantidade DESC;
    """
    
    df = conn.execute(query).df()
    
    if df.empty:
        st.info("Nenhuma rejeição consolidada encontrada para os filtros selecionados.")
        return
        
    total_rows = len(df)
    total_quantidade = df["quantidade"].sum()
    
    # KPIs rápidos
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric("Total de Ocorrências (ERRO)", f"{total_quantidade:,}".replace(",", "."), help="Soma total das ocorrências nesta visão.")
    with col_m2:
        st.metric("Tipos Únicos de Rejeição por Dia", f"{total_rows}", help="Quantidade de mensagens normalizadas distintas por funcionalidade e por dia.")
        
    st.markdown("---")
    
    # 2. Controles de Paginação
    limit = 15
    total_pages = max(1, (total_rows + limit - 1) // limit)
    
    col_pag1, col_pag2, col_pag3 = st.columns([2, 1, 2])
    with col_pag2:
        if total_pages > 1:
            page = st.number_input("Página", min_value=1, max_value=total_pages, value=1, step=1, key="consolidated_rejections_page")
        else:
            page = 1
        offset = (page - 1) * limit
        
    # Fatiamento dos dados da página atual
    df_page = df.iloc[offset : offset + limit]
    
    # Exibe a tabela formatada com colunas customizadas
    st.dataframe(
        df_page,
        column_config={
            "data": st.column_config.DateColumn(
                "data",
                format="DD/MM/YYYY",
                help="Data em que ocorreu a rejeição"
            ),
            "funcionalidade": st.column_config.TextColumn(
                "funcionalidade",
                width="medium",
                help="Funcionalidade/endpoint operacional ANTT"
            ),
            "mensagem_normalizada": st.column_config.TextColumn(
                "mensagem_normalizada",
                width="large",
                help="Mensagem de erro normalizada com placeholders preservados"
            ),
            "quantidade": st.column_config.NumberColumn(
                "quantidade",
                format="%d",
                help="Quantidade absoluta de ocorrências"
            ),
            "% representatividade": st.column_config.NumberColumn(
                "% representatividade",
                format="%.3f%%",
                help="Percentual de representação sobre o total de erros"
            )
        },
        use_container_width=True,
        hide_index=True
    )
    
    # 3. Rodapé com totalizador similar ao da planilha do usuário
    st.markdown(
        f"""
        <div style="background-color: rgba(255, 255, 255, 0.05); padding: 12px; border-radius: 5px; margin-top: -10px; display: flex; justify-content: space-between; font-weight: bold; border: 1px solid rgba(255, 255, 255, 0.1);">
            <div style="flex: 3; padding-left: 10px;">Total</div>
            <div style="flex: 4; text-align: left;"></div>
            <div style="flex: 1; text-align: left; padding-left: 10px;">{total_quantidade:,}</div>
            <div style="flex: 1; text-align: left; padding-left: 10px;">100,000%</div>
        </div>
        """.replace(",", "."),
        unsafe_allow_html=True
    )
    
    st.markdown("---")
    
    # 4. Ações de Exportação
    st.markdown("##### 📥 Exportar Rejeições Consoladas")
    st.caption("Faça o download do relatório consolidado com os filtros e busca aplicados.")
    
    col_exp1, col_exp2 = st.columns(2)
    filter_key_suffix = str(hash(where_clause) ^ hash(search_text))
    
    # Exportação em CSV
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, sep=";", index=False, encoding="utf-8")
    csv_data = csv_buffer.getvalue()
    
    # Exportação em Excel usando Polars para formatação rápida
    xlsx_buffer = io.BytesIO()
    pl.from_pandas(df).write_excel(xlsx_buffer, table_name="Rejeicoes_Normalizadas", table_style="Table Style Medium 9")
    xlsx_data = xlsx_buffer.getvalue()
    
    with col_exp1:
        st.download_button(
            label="📥 Exportar para CSV",
            data=csv_data,
            file_name=f"rejeicoes_normalizadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key="dl_csv_norm_" + filter_key_suffix
        )
    with col_exp2:
        st.download_button(
            label="📥 Exportar para Excel (XLSX)",
            data=xlsx_data,
            file_name=f"rejeicoes_normalizadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_xlsx_norm_" + filter_key_suffix
        )

