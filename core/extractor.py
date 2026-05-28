import polars as pl
from config import (
    REGEX_CEP, REGEX_PLACA, REGEX_CPF, REGEX_CNPJ,
    REGEX_RNTRC, REGEX_CIOT, REGEX_EIXO, REGEX_MUNICIPIO
)

def extract_entities_from_rejections(df_rejections: pl.DataFrame, prefix: str = "ent_") -> pl.DataFrame:
    """
    Extrai entidades operacionais das mensagens de rejeição utilizando Polars de forma vetorizada.
    
    Recebe um DataFrame contendo as colunas: rejeicao_id, mensagem
    Retorna um DataFrame normalizado com: entidade_id, rejeicao_id, entidade_tipo, entidade_valor
    """
    if df_rejections.height == 0:
        return pl.DataFrame(schema={
            "entidade_id": pl.String,
            "rejeicao_id": pl.String,
            "entidade_tipo": pl.String,
            "entidade_valor": pl.String
        })
        
    df = df_rejections.select([
        pl.col("rejeicao_id"),
        pl.col("mensagem").fill_null("").cast(pl.String).alias("msg")
    ])
    
    entities_dfs = []
    
    # 1. CEP
    df_cep = (
        df.select([
            pl.col("rejeicao_id"),
            pl.col("msg").str.extract_all(REGEX_CEP).alias("valores")
        ])
        .filter(pl.col("valores").list.len() > 0)
        .explode("valores")
        .select([
            pl.col("rejeicao_id"),
            pl.lit("CEP").alias("entidade_tipo"),
            pl.col("valores").alias("entidade_valor")
        ])
    )
    entities_dfs.append(df_cep)
    
    # 2. PLACA
    df_placa = (
        df.select([
            pl.col("rejeicao_id"),
            pl.col("msg").str.extract_all(REGEX_PLACA).alias("valores")
        ])
        .filter(pl.col("valores").list.len() > 0)
        .explode("valores")
        .select([
            pl.col("rejeicao_id"),
            pl.lit("PLACA").alias("entidade_tipo"),
            pl.col("valores").str.to_uppercase().str.replace_all(r"[- ]", "").alias("entidade_valor")
        ])
    )
    entities_dfs.append(df_placa)
    
    # 3. RNTRC
    df_rntrc = (
        df.select([
            pl.col("rejeicao_id"),
            pl.col("msg").str.extract_all(REGEX_RNTRC).alias("valores")
        ])
        .filter(pl.col("valores").list.len() > 0)
        .explode("valores")
        .select([
            pl.col("rejeicao_id"),
            pl.lit("RNTRC").alias("entidade_tipo"),
            pl.col("valores").str.replace_all(r"(?i)rntrc\s*:?\s*", "").alias("entidade_valor")
        ])
    )
    entities_dfs.append(df_rntrc)
    
    # 4. CPF
    df_cpf = (
        df.select([
            pl.col("rejeicao_id"),
            pl.col("msg").str.extract_all(REGEX_CPF).alias("valores")
        ])
        .filter(pl.col("valores").list.len() > 0)
        .explode("valores")
        .select([
            pl.col("rejeicao_id"),
            pl.lit("CPF").alias("entidade_tipo"),
            pl.col("valores").alias("entidade_valor")
        ])
    )
    entities_dfs.append(df_cpf)
    
    # 5. CNPJ
    df_cnpj = (
        df.select([
            pl.col("rejeicao_id"),
            pl.col("msg").str.extract_all(REGEX_CNPJ).alias("valores")
        ])
        .filter(pl.col("valores").list.len() > 0)
        .explode("valores")
        .select([
            pl.col("rejeicao_id"),
            pl.lit("CNPJ").alias("entidade_tipo"),
            pl.col("valores").alias("entidade_valor")
        ])
    )
    entities_dfs.append(df_cnpj)
    
    # 6. CIOT
    df_ciot = (
        df.select([
            pl.col("rejeicao_id"),
            pl.col("msg").str.extract_all(REGEX_CIOT).alias("valores")
        ])
        .filter(pl.col("valores").list.len() > 0)
        .explode("valores")
        .select([
            pl.col("rejeicao_id"),
            pl.lit("CIOT").alias("entidade_tipo"),
            pl.col("valores").str.replace_all(r"(?i)ciot\s*:?\s*", "").alias("entidade_valor")
        ])
    )
    entities_dfs.append(df_ciot)
    
    # 7. EIXOS
    df_eixos = (
        df.select([
            pl.col("rejeicao_id"),
            pl.col("msg").str.extract_all(REGEX_EIXO).alias("valores")
        ])
        .filter(pl.col("valores").list.len() > 0)
        .explode("valores")
        .select([
            pl.col("rejeicao_id"),
            pl.lit("EIXOS").alias("entidade_tipo"),
            pl.col("valores").str.replace_all(r"(?i)\s*eixos?", "").alias("entidade_valor")
        ])
    )
    entities_dfs.append(df_eixos)
    
    # 8. MUNICIPIO (IBGE Código)
    df_mun = (
        df.select([
            pl.col("rejeicao_id"),
            pl.col("msg").str.extract_all(REGEX_MUNICIPIO).alias("valores")
        ])
        .filter(pl.col("valores").list.len() > 0)
        .explode("valores")
        .select([
            pl.col("rejeicao_id"),
            pl.lit("MUNICIPIO").alias("entidade_tipo"),
            pl.col("valores").str.replace_all(r"(?i)munic(?:i|í)pio\s*:?\s*", "").alias("entidade_valor")
        ])
    )
    entities_dfs.append(df_mun)

    # Une todas as entidades
    valid_dfs = [d for d in entities_dfs if d.height > 0]
    if valid_dfs:
        df_final = pl.concat(valid_dfs)
        df_final = df_final.unique(subset=["rejeicao_id", "entidade_tipo", "entidade_valor"])
        
        # Limita para evitar explosão de cardinalidade (máximo de 10 entidades do mesmo tipo por rejeição)
        df_final = df_final.with_columns(
            pl.col("entidade_valor").cum_count().over(["rejeicao_id", "entidade_tipo"]).alias("entity_rank")
        )
        excess_count = df_final.filter(pl.col("entity_rank") > 10).height
        if excess_count > 0:
            print(f"WARNING: Truncated {excess_count} excess entities to prevent cardinality explosion (max 10 of same type per rejection).")
            
        df_final = df_final.filter(pl.col("entity_rank") <= 10).drop("entity_rank")
        
        # Gera ID de Entidade único
        df_final = df_final.with_row_index("index_ent")
        df_final = df_final.with_columns(
            (pl.lit(prefix) + pl.col("index_ent").cast(pl.String)).alias("entidade_id")
        )
        return df_final.select(["entidade_id", "rejeicao_id", "entidade_tipo", "entidade_valor"])
        
    return pl.DataFrame(schema={
        "entidade_id": pl.String,
        "rejeicao_id": pl.String,
        "entidade_tipo": pl.String,
        "entidade_valor": pl.String
    })
