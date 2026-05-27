import os
import duckdb
import polars as pl
import streamlit as st

DB_DIR = os.path.join("data")
RAW_DIR = os.path.join(DB_DIR, "raw")
SILVER_DIR = os.path.join(DB_DIR, "silver")
UPLOADS_DIR = "uploads"
EXPORTS_DIR = "exports"

def init_directories():
    """Inicializa os diretórios necessários para a aplicação funcionar."""
    for path in [DB_DIR, RAW_DIR, SILVER_DIR, UPLOADS_DIR, EXPORTS_DIR]:
        os.makedirs(path, exist_ok=True)

@st.cache_resource
def get_db_connection():
    """Retorna uma conexão DuckDB thread-safe e persistente em arquivo local."""
    init_directories()
    db_path = os.path.join(DB_DIR, "antt_analytics.db")
    conn = duckdb.connect(db_path, read_only=False)
    conn.execute("SET threads TO 4;")
    return conn

def save_silver_parquet(
    df_logs: pl.DataFrame,
    df_rejections: pl.DataFrame,
    df_entities: pl.DataFrame,
    file_hash: str
):
    """Grava as tabelas da camada Silver (dim_log, fact_rejeicoes, fact_entidades) em Parquet."""
    init_directories()
    
    # Adicionamos o hash do arquivo em cada tabela para rastreabilidade/versionamento
    df_logs = df_logs.with_columns(pl.lit(file_hash).alias("file_hash"))
    df_rejections = df_rejections.with_columns(pl.lit(file_hash).alias("file_hash"))
    df_entities = df_entities.with_columns(pl.lit(file_hash).alias("file_hash"))
    
    # Salva arquivos parquet com compressão Zstd
    df_logs.write_parquet(os.path.join(SILVER_DIR, f"dim_log_{file_hash}.parquet"), compression="zstd")
    df_rejections.write_parquet(os.path.join(SILVER_DIR, f"fact_rejeicoes_semanticas_{file_hash}.parquet"), compression="zstd")
    df_entities.write_parquet(os.path.join(SILVER_DIR, f"fact_entidades_extraidas_{file_hash}.parquet"), compression="zstd")

def register_views_in_duckdb(conn, file_hash: str):
    """Cria views temporárias no DuckDB apontando diretamente para os arquivos Parquet da camada Silver."""
    logs_path = os.path.join(SILVER_DIR, f"dim_log_{file_hash}.parquet").replace("\\", "/")
    rejections_path = os.path.join(SILVER_DIR, f"fact_rejeicoes_semanticas_{file_hash}.parquet").replace("\\", "/")
    entities_path = os.path.join(SILVER_DIR, f"fact_entidades_extraidas_{file_hash}.parquet").replace("\\", "/")
    
    conn.execute(f"CREATE OR REPLACE VIEW dim_log AS SELECT * FROM read_parquet('{logs_path}');")
    conn.execute(f"CREATE OR REPLACE VIEW fact_rejeicoes_semanticas AS SELECT * FROM read_parquet('{rejections_path}');")
    conn.execute(f"CREATE OR REPLACE VIEW fact_entidades_extraidas AS SELECT * FROM read_parquet('{entities_path}');")

def check_file_already_processed(file_hash: str) -> bool:
    """Verifica se os arquivos Silver Parquet para o hash fornecido já existem."""
    logs_path = os.path.join(SILVER_DIR, f"dim_log_{file_hash}.parquet")
    rejections_path = os.path.join(SILVER_DIR, f"fact_rejeicoes_semanticas_{file_hash}.parquet")
    entities_path = os.path.join(SILVER_DIR, f"fact_entidades_extraidas_{file_hash}.parquet")
    
    return (
        os.path.exists(logs_path) and
        os.path.exists(rejections_path) and
        os.path.exists(entities_path)
    )

def clear_all_memory(conn):
    """Limpa toda a memória da aplicação: deleta arquivos Parquet, uploads, exportações e dropa views."""
    # 1. Dropa views no DuckDB
    try:
        conn.execute("DROP VIEW IF EXISTS dim_log;")
        conn.execute("DROP VIEW IF EXISTS fact_rejeicoes_semanticas;")
        conn.execute("DROP VIEW IF EXISTS fact_entidades_extraidas;")
    except Exception:
        pass
        
    # 2. Deleta arquivos de dados
    for folder in [SILVER_DIR, UPLOADS_DIR, EXPORTS_DIR, RAW_DIR]:
        if os.path.exists(folder):
            for file in os.listdir(folder):
                file_path = os.path.join(folder, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception:
                    pass
                    
    # 3. Limpa cache do Streamlit
    st.cache_data.clear()
    st.cache_resource.clear()
