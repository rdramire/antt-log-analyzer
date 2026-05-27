import os
import io
import duckdb
import polars as pl
import streamlit as st

def export_filtered_data_csv(conn, query_sql: str) -> bytes:
    """
    Exporta o resultado de uma consulta do DuckDB para CSV de forma ultra rápida
    utilizando a gravação direta em disco do DuckDB e lendo os bytes resultantes.
    """
    temp_path = os.path.join("exports", "temp_export.csv").replace("\\", "/")
    
    # Limpa ponto e vírgula final se houver
    query_sql_clean = query_sql.strip().rstrip(';')
    
    # Executa a cópia direta no DuckDB
    copy_query = f"COPY ({query_sql_clean}) TO '{temp_path}' (HEADER, DELIMITER ';', FORCE_QUOTE *);"
    conn.execute(copy_query)
    
    # Lê os bytes e remove o arquivo temporário
    with open(temp_path, "rb") as f:
        data = f.read()
        
    try:
        os.remove(temp_path)
    except Exception:
        pass
        
    return data

def export_filtered_data_xlsx(conn, query_sql: str) -> bytes:
    """
    Exporta o resultado de uma consulta do DuckDB para Excel (XLSX).
    Limita o tamanho para evitar estourar o limite de linhas do Excel (1.048.576).
    """
    # Limpa ponto e vírgula final se houver
    query_sql_clean = query_sql.strip().rstrip(';')
    
    # Executa a query no DuckDB e converte direto para Polars DataFrame
    df = conn.execute(query_sql_clean).pl()
    
    # Proteção de limite de linhas do Excel
    if df.height > 1000000:
        df = df.head(1000000)
        st.warning("O arquivo gerado foi limitado a 1.000.000 de linhas (limite do Excel).")
        
    # Escreve em buffer de memória
    output = io.BytesIO()
    df.write_excel(output, table_name="ANTT_Logs", table_style="Table Style Medium 9")
    return output.getvalue()
