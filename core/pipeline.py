import os
import re
import json
import polars as pl
from datetime import datetime
from core.parser import read_uploaded_file
from core.extractor import extract_entities_from_rejections
from core.database import save_silver_parquet, check_file_already_processed, register_views_in_duckdb
from classification_rules import OFFICIAL_CLASSIFICATION_RULES, get_severity_for_category, get_guidance_for_category, normalize_message_placeholders
def split_message_into_rejections(msg: str) -> list:
    """
    Divide uma mensagem que contém múltiplas rejeições usando estritamente o delimitador '","' ou "','".
    Remove colchetes '[', ']' e aspas '"', '\'' extras do início e fim das mensagens resultantes.
    """
    if not msg or not isinstance(msg, str):
        return []
        
    # Normaliza aspas escapadas
    msg_clean = msg.replace('\\"', '"').replace("\\'", "'").strip()
    
    # Limpa colchetes ou aspas que englobam a mensagem inteira
    changed = True
    while changed:
        changed = False
        if msg_clean.startswith('[') and msg_clean.endswith(']'):
            msg_clean = msg_clean[1:-1].strip()
            changed = True
        elif msg_clean.startswith('"') and msg_clean.endswith('"'):
            msg_clean = msg_clean[1:-1].strip()
            changed = True
        elif msg_clean.startswith("'") and msg_clean.endswith("'"):
            msg_clean = msg_clean[1:-1].strip()
            changed = True
            
    # Divide por "," ou ',' (com possíveis espaços ao redor)
    parts = re.split(r'["\']\s*,\s*["\']', msg_clean)
    
    cleaned_parts = []
    for part in parts:
        part_clean = part.strip()
        # Limpa aspas residuais das partes individuais
        changed_part = True
        while changed_part:
            changed_part = False
            if part_clean.startswith('"') and part_clean.endswith('"'):
                part_clean = part_clean[1:-1].strip()
                changed_part = True
            elif part_clean.startswith("'") and part_clean.endswith("'"):
                part_clean = part_clean[1:-1].strip()
                changed_part = True
        if part_clean:
            cleaned_parts.append(part_clean)
            
    return cleaned_parts

def classify_message_semantically(message: str, code_antt: str) -> dict:
    """
    Classifica uma mensagem de erro em um tipo semântico, causa raiz e 
    orientação operacional usando a taxonomia oficial em classification_rules.py.
    """
    if not message or not isinstance(message, str) or str(message).strip() == "" or str(message) == "None" or str(message) == "nan":
        return {
            "categoria_operacional": "OUTROS_NAO_CATEGORIZADO",
            "tipo_rejeicao_semantica": "OUTROS_NAO_CATEGORIZADO",
            "subtipo_rejeicao": "Erro de sistema ou resposta vazia.",
            "severidade": "CRITICA",
            "orientacao_operacional": get_guidance_for_category("SISTEMA"),
            "causa_raiz": "OUTROS_NAO_CATEGORIZADO",
            "codigo_oficial": "OUTROS",
            "template_oficial": "OUTROS_NAO_CATEGORIZADO",
            "mensagem_normalizada": ""
        }
        
    message_clean = message.strip()
    norm_msg = normalize_message_placeholders(message_clean)
    
    # 1. Match contra as regras de regex oficiais do classification_rules.py
    for rule in OFFICIAL_CLASSIFICATION_RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, message_clean) or re.search(pattern, norm_msg):
                return {
                    "categoria_operacional": rule["categoria"],
                    "tipo_rejeicao_semantica": rule["template_oficial"],
                    "subtipo_rejeicao": rule["descricao_oficial"],
                    "severidade": get_severity_for_category(rule["categoria"]),
                    "orientacao_operacional": get_guidance_for_category(rule["categoria"]),
                    "causa_raiz": rule["categoria"],
                    "codigo_oficial": rule["codigo"],
                    "template_oficial": rule["template_oficial"],
                    "mensagem_normalizada": norm_msg
                }
                
    # 2. Fallbacks baseados nos códigos de retorno da ANTT se não bater nenhuma regex
    if code_antt:
        code_str = str(code_antt).strip()
        matched_rules = [r for r in OFFICIAL_CLASSIFICATION_RULES if r["codigo"] == code_str]
        if matched_rules:
            if len(matched_rules) == 1:
                rule = matched_rules[0]
            else:
                # E.g. código 210 tem LOCALIZAÇÃO e EIXOS
                if any(w in message_clean.lower() for w in ["eixo", "veiculo", "veículo"]):
                    rule = next((r for r in matched_rules if r["categoria"] == "EIXOS"), matched_rules[0])
                else:
                    rule = next((r for r in matched_rules if r["categoria"] == "LOCALIZAÇÃO"), matched_rules[0])
                    
            return {
                "categoria_operacional": rule["categoria"],
                "tipo_rejeicao_semantica": rule["template_oficial"],
                "subtipo_rejeicao": rule["descricao_oficial"],
                "severidade": get_severity_for_category(rule["categoria"]),
                "orientacao_operacional": get_guidance_for_category(rule["categoria"]),
                "causa_raiz": rule["categoria"],
                "codigo_oficial": rule["codigo"],
                "template_oficial": rule["template_oficial"],
                "mensagem_normalizada": norm_msg
            }
            
    # Fallback final para novos códigos não mapeados ou erros desconhecidos
    return {
        "categoria_operacional": "OUTROS_NAO_CATEGORIZADO",
        "tipo_rejeicao_semantica": "OUTROS_NAO_CATEGORIZADO",
        "subtipo_rejeicao": f"Mensagem não classificada: {message_clean}",
        "severidade": "MEDIA",
        "orientacao_operacional": get_guidance_for_category("OUTROS_NAO_CATEGORIZADO"),
        "causa_raiz": "OUTROS_NAO_CATEGORIZADO",
        "codigo_oficial": code_antt if code_antt else "OUTROS",
        "template_oficial": "OUTROS_NAO_CATEGORIZADO",
        "mensagem_normalizada": norm_msg
    }

def extract_row_protocol(row_dict: dict) -> str:
    """
    Implementa a prioridade de captura do protocolo:
    1. json.Protocolo
    2. cod_protocolo
    3. protocolo explícito na mensagem
    4. Coluna original "protocolo"
    5. fallback "SEM_PROTOCOLO"
    """
    # 1. json.Protocolo (des_resposta ou cod_mensagem)
    for field in ["des_resposta", "cod_mensagem"]:
        val = row_dict.get(field)
        if val and isinstance(val, str):
            val_strip = val.strip()
            if val_strip.startswith('{') or val_strip.startswith('['):
                try:
                    data = json.loads(val_strip)
                    if isinstance(data, dict):
                        # case-insensitive key search for "protocolo"
                        for k, v in data.items():
                            if k.lower() == "protocolo" and v:
                                return str(v).strip()
                except Exception:
                    pass

    # 2. cod_protocolo column
    if "cod_protocolo" in row_dict:
        val = row_dict["cod_protocolo"]
        if val is not None and str(val).strip() != "" and str(val) not in ["None", "nan", "SEM_PROTOCOLO"]:
            return str(val).strip()

    # 3. protocolo explícito na mensagem (regex: r"(?i)protocolo\s*:?\s*\b([a-zA-Z0-9_-]+)\b")
    regex_proto = re.compile(r"(?i)protocolo\s*:?\s*\b([a-zA-Z0-9_-]+)\b")
    for field in ["des_resposta", "cod_mensagem"]:
        val = row_dict.get(field)
        if val and isinstance(val, str):
            m = regex_proto.search(val)
            if m:
                extracted = m.group(1)
                if extracted and len(extracted) >= 3:
                    return extracted.strip()

    # 4. Coluna original "protocolo"
    if "protocolo" in row_dict:
        val = row_dict["protocolo"]
        if val is not None and str(val).strip() != "" and str(val) not in ["None", "nan", "SEM_PROTOCOLO"]:
            return str(val).strip()

    # 5. Fallback
    return "SEM_PROTOCOLO"

def parse_payloads(cod_mensagens, des_respostas):
    """
    Realiza o parse estruturado dos campos de retorno tratando os cenários 1, 2 e 3
    e retorna listas limpas de códigos e mensagens correspondentes.
    """
    parsed_codes = []
    parsed_msgs = []
    
    for cod, resp in zip(cod_mensagens, des_respostas):
        codes = []
        msgs = []
        parsed = False
        
        # 1. Tenta fazer o parse de des_resposta como JSON
        if resp and isinstance(resp, str):
            resp_stripped = resp.strip()
            if resp_stripped.startswith('{') or resp_stripped.startswith('['):
                try:
                    data = json.loads(resp_stripped)
                    if isinstance(data, dict):
                        raw_code = data.get('Codigo', data.get('codigo'))
                        raw_msg = data.get('Mensagem', data.get('mensagem'))
                        
                        if isinstance(raw_code, list):
                            codes = [str(c).strip() for c in raw_code if c]
                        elif isinstance(raw_code, str):
                            codes = [c.strip() for c in raw_code.split(',') if c.strip()]
                        elif raw_code is not None:
                            codes = [str(raw_code).strip()]
                            
                        if isinstance(raw_msg, list):
                            msgs = [str(m).strip() for m in raw_msg if m]
                        elif isinstance(raw_msg, str):
                            msgs = [raw_msg.strip()]
                        elif raw_msg is not None:
                            msgs = [str(raw_msg).strip()]
                            
                        parsed = True
                except Exception:
                    pass
                    
        # 2. Tenta fazer o parse de cod_mensagem como JSON
        if not parsed and cod and isinstance(cod, str):
            cod_stripped = cod.strip()
            if cod_stripped.startswith('{') or cod_stripped.startswith('['):
                try:
                    data = json.loads(cod_stripped)
                    if isinstance(data, dict):
                        raw_code = data.get('Codigo', data.get('codigo'))
                        raw_msg = data.get('Mensagem', data.get('mensagem'))
                        
                        if isinstance(raw_code, list):
                            codes = [str(c).strip() for c in raw_code if c]
                        elif isinstance(raw_code, str):
                            codes = [c.strip() for c in raw_code.split(',') if c.strip()]
                        elif raw_code is not None:
                            codes = [str(raw_code).strip()]
                            
                        if isinstance(raw_msg, list):
                            msgs = [str(m).strip() for m in raw_msg if m]
                        elif isinstance(raw_msg, str):
                            msgs = [raw_msg.strip()]
                        elif raw_msg is not None:
                            msgs = [str(raw_msg).strip()]
                            
                        parsed = True
                except Exception:
                    pass
                    
        # 3. Fallback estruturado se não for JSON
        if not parsed:
            if cod is None or str(cod) == "None" or str(cod) == "nan":
                codes = []
            elif isinstance(cod, (int, float)):
                codes = [str(int(cod))]
            else:
                codes = [c.strip() for c in str(cod).split(',') if c.strip()]
                
            if resp is None or str(resp) == "None" or str(resp) == "nan":
                msgs = []
            else:
                msgs = [str(resp).strip()]
                
        if not codes:
            codes = [""]
        if not msgs:
            msgs = [""]
            
        parsed_codes.append(codes)
        parsed_msgs.append(msgs)
        
    return parsed_codes, parsed_msgs

def run_etl_pipeline(file_path: str, file_hash: str, conn) -> dict:
    """
    Executa o Pipeline ETL completo:
    1. Carrega e normaliza logs via Polars.
    2. Roda a classificação semântica das rejeições.
    3. Extrai as entidades operacionais vinculando-as diretamente ao rejeicao_id.
    4. Grava os arquivos Silver Parquet e registra as views no DuckDB.
    """
    if check_file_already_processed(file_hash):
        register_views_in_duckdb(conn, file_hash)
        total_logs = conn.execute("SELECT COUNT(*) FROM dim_log;").fetchone()[0]
        unique_protocols = conn.execute("SELECT COUNT(DISTINCT protocolo) FROM dim_log;").fetchone()[0]
        return {
            "status": "cached",
            "total_logs": total_logs,
            "unique_protocols": unique_protocols
        }
        
    df = read_uploaded_file(file_path)
    cols = df.columns
    
    # Normalização de colunas
    if "contratante" not in cols:
        df = df.with_columns(pl.lit("CONTRATANTE DESCONHECIDO").alias("contratante"))
    else:
        df = df.with_columns(pl.col("contratante").cast(pl.String).fill_null("CONTRATANTE DESCONHECIDO"))
        
    if "funcionalidade" not in cols:
        df = df.with_columns(pl.lit("NÃO ESPECIFICADA").alias("funcionalidade"))
    else:
        df = df.with_columns(pl.col("funcionalidade").cast(pl.String).fill_null("NÃO ESPECIFICADA"))
        
    if "data" not in cols:
        df = df.with_columns(pl.lit(datetime.now().strftime("%Y-%m-%d %H:%M:%S")).alias("data"))
    
    df = df.with_columns(pl.col("data").cast(pl.String))
    parsed_date = None
    for fmt in ["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M"]:
        try:
            test_col = df.select(pl.col("data").str.to_datetime(fmt, strict=False))
            if test_col["data"].null_count() < df.height:
                parsed_date = pl.col("data").str.to_datetime(fmt, strict=False)
                break
        except Exception:
            continue
            
    if parsed_date is not None:
        df = df.with_columns(parsed_date.fill_null(datetime.now()))
    else:
        df = df.with_columns(pl.lit(datetime.now()).alias("data"))
        
    # Campos de erro
    if "cod_mensagem" not in cols:
        df = df.with_columns(pl.lit("").alias("cod_mensagem"))
    else:
        df = df.with_columns(pl.col("cod_mensagem").cast(pl.String).fill_null(""))
        
    if "des_resposta" not in cols:
        df = df.with_columns(pl.lit("").alias("des_resposta"))
    else:
        df = df.with_columns(pl.col("des_resposta").cast(pl.String).fill_null(""))
        
    # Extrai o protocolo com prioridade
    protocols = [extract_row_protocol(row) for row in df.iter_rows(named=True)]
    df = df.with_columns(pl.Series("protocolo", protocols))
        
    # Adiciona ID único de log
    df = df.with_row_index("index_id")
    df = df.with_columns(
        (pl.lit("log_") + pl.col("index_id").cast(pl.String)).alias("log_id")
    )
    
    # Parsing dos payloads
    cod_mensagens = df["cod_mensagem"].to_list()
    des_respostas = df["des_resposta"].to_list()
    log_ids = df["log_id"].to_list()
    
    parsed_codes, parsed_msgs = parse_payloads(cod_mensagens, des_respostas)
    
    # Processa as Rejeições Semânticas e mapeia para causas raiz
    rejections_records = []
    for log_id, codes, msgs in zip(log_ids, parsed_codes, parsed_msgs):
        # Pareia cada mensagem com o seu respectivo código antes da divisão
        paired_msg_code = []
        for idx, msg in enumerate(msgs):
            c = codes[idx] if idx < len(codes) else (codes[0] if codes else "")
            paired_msg_code.append((msg, c))
            
        expanded_pairs = []
        for msg, code in paired_msg_code:
            if msg:
                splits = split_message_into_rejections(msg)
                for split_msg in splits:
                    expanded_pairs.append((split_msg, code))
            else:
                expanded_pairs.append(("", code))
                
        for i, (msg, code) in enumerate(expanded_pairs):
            if not msg or msg.strip() == "" or msg in ["SUCESSO", "Operação realizada com sucesso."]:
                continue
                
            sem = classify_message_semantically(msg, code)
            
            if sem["tipo_rejeicao_semantica"] == "SUCESSO":
                continue
                
            rej_id = f"{log_id}_rej_{i}"
            
            rejections_records.append({
                "rejeicao_id": rej_id,
                "log_id": log_id,
                "codigo_antt": code,
                "categoria_operacional": sem["categoria_operacional"],
                "tipo_rejeicao_semantica": sem["tipo_rejeicao_semantica"],
                "subtipo_rejeicao": sem["subtipo_rejeicao"],
                "categoria": sem["categoria_operacional"],
                "severidade": sem["severidade"],
                "causa_raiz": sem["categoria_operacional"],
                "orientacao_operacional": sem["orientacao_operacional"],
                "mensagem": msg,
                "mensagem_original": msg,
                "mensagem_normalizada": sem["mensagem_normalizada"],
                "template_oficial": sem["template_oficial"]
            })
            
    # Cria DataFrame de Rejeições
    if rejections_records:
        df_rejections = pl.DataFrame(rejections_records)
    else:
        df_rejections = pl.DataFrame(schema={
            "rejeicao_id": pl.String,
            "log_id": pl.String,
            "codigo_antt": pl.String,
            "categoria_operacional": pl.String,
            "tipo_rejeicao_semantica": pl.String,
            "subtipo_rejeicao": pl.String,
            "categoria": pl.String,
            "severidade": pl.String,
            "causa_raiz": pl.String,
            "orientacao_operacional": pl.String,
            "mensagem": pl.String,
            "mensagem_original": pl.String,
            "mensagem_normalizada": pl.String,
            "template_oficial": pl.String
        })
        
    # Extrai Entidades associadas diretamente a cada rejeição
    df_entities = extract_entities_from_rejections(df_rejections)
    
    # Monta dim_log e calcula status_geral final
    # Se o log_id possui qualquer rejeição em df_rejections, o status é ERRO, senão SUCESSO
    error_log_ids = set(df_rejections["log_id"].to_list()) if df_rejections.height > 0 else set()
    
    df_logs = (
        df.select([
            pl.col("log_id"),
            pl.col("protocolo"),
            pl.col("data").alias("data_evento"),
            pl.col("contratante"),
            pl.col("funcionalidade")
        ])
        .with_columns(
            pl.col("log_id")
            .map_elements(lambda lid: "ERRO" if lid in error_log_ids else "SUCESSO", return_dtype=pl.String)
            .alias("status_geral")
        )
    )
    
    # Grava na camada Silver Parquet
    save_silver_parquet(df_logs, df_rejections, df_entities, file_hash)
    
    # Registra as views analíticas no DuckDB
    register_views_in_duckdb(conn, file_hash)
    
    return {
        "status": "processed",
        "total_logs": df_logs.height,
        "unique_protocols": df_logs["protocolo"].n_unique()
    }
