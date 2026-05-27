import os
import hashlib
import polars as pl
import streamlit as st

def calculate_md5(file_path: str) -> str:
    """Calcula o hash MD5 de um arquivo no disco de forma incremental para economizar memória."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def normalize_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Normaliza o nome das colunas para letras minúsculas e sem espaços extras."""
    rename_dict = {}
    for col in df.columns:
        clean_col = col.strip().lower()
        if clean_col != col:
            rename_dict[col] = clean_col
    if rename_dict:
        df = df.rename(rename_dict)
    return df

def read_uploaded_file(file_path: str) -> pl.DataFrame:
    """Lê o arquivo CSV ou XLSX salvo no disco usando Polars de forma eficiente."""
    _, ext = os.path.splitext(file_path.lower())
    
    if ext == ".csv":
        # Tenta ler com delimitador ; ou , e encodings comuns
        for delimiter in [";", ","]:
            for encoding in ["utf-8", "latin-1", "iso-8859-1"]:
                try:
                    df = pl.read_csv(
                        file_path, 
                        separator=delimiter, 
                        encoding=encoding,
                        infer_schema_length=10000,
                        ignore_errors=True
                    )
                    df = normalize_columns(df)
                    
                    # Verifica se temos pelo menos as colunas básicas
                    required_cols = ["protocolo", "contratante"]
                    if any(col in df.columns for col in required_cols):
                        return df
                except Exception:
                    continue
        
        # Fallback padrão
        raise ValueError("Não foi possível ler o arquivo CSV. Verifique se o delimitador e o encoding são compatíveis (UTF-8 ou Latin-1).")
    
    elif ext in [".xlsx", ".xls"]:
        try:
            # pl.read_excel requer fsspec e openpyxl ou calamine. Usamos o calamine se disponível por velocidade
            try:
                df = pl.read_excel(file_path, engine="calamine")
            except Exception:
                df = pl.read_excel(file_path, engine="openpyxl")
            
            df = normalize_columns(df)
            return df
        except Exception as e:
            raise ValueError(f"Erro ao ler arquivo Excel: {str(e)}")
            
    else:
        raise ValueError("Formato de arquivo não suportado. Envie apenas arquivos CSV, XLSX ou XLS.")
