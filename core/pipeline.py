import os
import re
import json
import polars as pl
from datetime import datetime
from core.parser import read_uploaded_file
from core.extractor import extract_entities_from_rejections
from core.database import save_silver_parquet, check_file_already_processed, register_views_in_duckdb
from classification_rules import OFFICIAL_CLASSIFICATION_RULES, get_severity_for_category, get_guidance_for_category, normalize_message_placeholders
from success_rules import is_success_message
from operational_rules import get_contextual_result

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
                    "subtipo_rejeicao": rule.get("descricao_oficial", ""),
                    "severidade": rule.get("severidade") or get_severity_for_category(rule["categoria"]),
                    "orientacao_operacional": rule.get("orientacao_operacional") or get_guidance_for_category(rule["categoria"]),
                    "causa_raiz": rule.get("causa_raiz") or rule["categoria"],
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
                "subtipo_rejeicao": rule.get("descricao_oficial", ""),
                "severidade": rule.get("severidade") or get_severity_for_category(rule["categoria"]),
                "orientacao_operacional": rule.get("orientacao_operacional") or get_guidance_for_category(rule["categoria"]),
                "causa_raiz": rule.get("causa_raiz") or rule["categoria"],
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

def normalize_severity(sev: str) -> str:
    if not sev:
        return "MEDIO"
    sev_upper = str(sev).upper().strip()
    if "CRITIC" in sev_upper:
        return "CRITICO"
    if "ALT" in sev_upper:
        return "ALTO"
    if "MED" in sev_upper:
        return "MEDIO"
    if "BAIX" in sev_upper:
        return "BAIXO"
    if "INFO" in sev_upper:
        return "INFO"
    return "MEDIO"

def classify_log_message(message: str, code: str, functionality: str) -> dict:
    """
    Classifica de forma única e centralizada cada mensagem/código/funcionalidade seguindo a hierarquia:
    1. Erro Técnico ou Erro de Infraestrutura (SSL, TIMEOUT, SOAP_FAULT, etc.)
    2. Sucesso Conhecido (SUCESSO)
    3. Sucesso com Alerta (SUCESSO_COM_ALERTA, e.g. Idempotência)
    4. Alerta Operacional (ALERTA_OPERACIONAL)
    5. Rejeição Negocial (REJEICAO_NEGOCIO, matches OFFICIAL_CLASSIFICATION_RULES)
    6. Fallback (OUTROS_NAO_CATEGORIZADO ou ERRO_TECNICO)
    """
    msg_clean = str(message).strip() if message else ""
    msg_lower = msg_clean.lower()
    code_str = str(code).strip() if code else ""
    func_clean = str(functionality).strip() if functionality else ""
    
    # ----------------------------------------------------
    # 1. ERRO TÉCNICO / ERRO INFRAESTRUTURA
    # ----------------------------------------------------
    
    # A. Check code 500
    if code_str == "500" or "500 internal server error" in msg_lower or "http 500" in msg_lower:
        return {
            "resultado_operacional": "ERRO_TECNICO",
            "tipo_erro_tecnico": "HTTP_500",
            "severidade": "CRITICO"
        }
        
    # B. Match against operational_rules where it's technical or infrastructure error
    ctx = get_contextual_result(message, code, functionality)
    if ctx and ctx["resultado_operacional"] in ["ERRO_TECNICO", "ERRO_INFRAESTRUTURA"]:
        return {
            "resultado_operacional": ctx["resultado_operacional"],
            "tipo_erro_tecnico": ctx["tipo_erro_tecnico"],
            "severidade": normalize_severity(ctx["severidade"])
        }
        
    # C. Inline regex matching fallback for technical / infrastructure errors
    # Timeout
    if any(p in msg_lower for p in ["timeout", "timed out", "timed_out", "tempo limite esgotado", "tempo limite excedido", "requisicao expirada", "requisição expirada"]):
        return {"resultado_operacional": "ERRO_INFRAESTRUTURA", "tipo_erro_tecnico": "TIMEOUT", "severidade": "CRITICO"}
        
    # SSL
    if any(p in msg_lower for p in ["ssl", "certificate", "handshake", "certificado inválido", "certificado invalido", "segurança conexão", "seguranca conexao"]):
        return {"resultado_operacional": "ERRO_INFRAESTRUTURA", "tipo_erro_tecnico": "SSL", "severidade": "CRITICO"}
        
    # Conexão
    if any(p in msg_lower for p in ["connection refused", "conexao", "conexão", "indisponivel", "indisponível", "fora do ar", "fora_ar", "comunicacao", "comunicação", "host unreachable", "socket error", "socket_error"]):
        return {"resultado_operacional": "ERRO_INFRAESTRUTURA", "tipo_erro_tecnico": "CONEXAO", "severidade": "CRITICO"}
        
    # Auth
    if any(p in msg_lower for p in ["auth", "unauthorized", "token", "credencia", "permissao", "permissão", "não autorizado", "nao autorizado", "acesso negado", "senha inválida", "senha invalida"]):
        return {"resultado_operacional": "ERRO_TECNICO", "tipo_erro_tecnico": "AUTH", "severidade": "CRITICO"}
        
    # Parse / Serialização
    if any(p in msg_lower for p in ["json", "xml", "parser", "parsing", "mapeamento", "deserializ", "serializ", "malformado"]) or re.search(r"br\.com\.[\w\.]+\@[a-fA-F0-9]+", msg_clean):
        return {"resultado_operacional": "ERRO_TECNICO", "tipo_erro_tecnico": "PARSE", "severidade": "CRITICO"}
        
    # SOAP Fault
    if any(p in msg_lower for p in ["soap fault", "soapfault", "soap-env:fault", "envelope inválido", "envelope invalido"]):
        return {"resultado_operacional": "ERRO_TECNICO", "tipo_erro_tecnico": "SOAP_FAULT", "severidade": "CRITICO"}
        
    # Rate Limit
    if any(p in msg_lower for p in ["rate limit", "rate_limit", "limite requisiç", "limite requisic", "excedeu requisiç", "excedeu requisic", "too many requests"]):
        return {"resultado_operacional": "ERRO_INFRAESTRUTURA", "tipo_erro_tecnico": "RATE_LIMIT", "severidade": "ALTO"}
        
    # D. Check if semantic category is system/integration
    sem = classify_message_semantically(message, code)
    cat = sem.get("categoria_operacional", "OUTROS_NAO_CATEGORIZADO")
    if cat in ["INTEGRAÇÃO", "INTEGRACAO", "SISTEMA"]:
        return {
            "resultado_operacional": "ERRO_TECNICO" if cat == "SISTEMA" else "ERRO_INFRAESTRUTURA",
            "tipo_erro_tecnico": "HTTP_500" if code_str == "500" else "CONEXAO",
            "severidade": "CRITICO"
        }
        
    # ----------------------------------------------------
    # 2. SUCESSO CONHECIDO
    # ----------------------------------------------------
    
    # A. Check code success bypasses negation checks
    if code_str in ["100", "110", "111", "200"]:
        return {
            "resultado_operacional": "SUCESSO",
            "tipo_erro_tecnico": None,
            "severidade": "INFO"
        }
        
    # B. Match against success messages (but strictly avoid negation keywords)
    negations = ["não", "nao", "nõo", "sem", "erro", "rejeitado", "rejeicao", "rejeição", "inválido", "invalido", "inativa", "inativo", "suspensa", "suspenso", "divergente", "falha"]
    has_negation = any(neg in msg_lower for neg in negations)
    
    if not has_negation:
        if is_success_message(message, None, functionality):
            return {
                "resultado_operacional": "SUCESSO",
                "tipo_erro_tecnico": None,
                "severidade": "INFO"
            }
        if ctx and ctx["resultado_operacional"] == "SUCESSO":
            return {
                "resultado_operacional": "SUCESSO",
                "tipo_erro_tecnico": None,
                "severidade": "INFO"
            }
        if cat == "SUCESSO":
            return {
                "resultado_operacional": "SUCESSO",
                "tipo_erro_tecnico": None,
                "severidade": "INFO"
            }

    # ----------------------------------------------------
    # 3. SUCESSO COM ALERTA
    # ----------------------------------------------------
    if ctx and ctx["resultado_operacional"] == "SUCESSO_COM_ALERTA":
        return {
            "resultado_operacional": "SUCESSO_COM_ALERTA",
            "tipo_erro_tecnico": None,
            "severidade": normalize_severity(ctx["severidade"])
        }
        
    # ----------------------------------------------------
    # 4. ALERTA OPERACIONAL
    # ----------------------------------------------------
    if ctx and ctx["resultado_operacional"] == "ALERTA_OPERACIONAL":
        return {
            "resultado_operacional": "ALERTA_OPERACIONAL",
            "tipo_erro_tecnico": None,
            "severidade": normalize_severity(ctx["severidade"])
        }

    # ----------------------------------------------------
    # 5. REJEIÇÃO NEGOCIAL
    # ----------------------------------------------------
    if sem["tipo_rejeicao_semantica"] != "OUTROS_NAO_CATEGORIZADO" and sem["tipo_rejeicao_semantica"] is not None:
        return {
            "resultado_operacional": "REJEICAO_NEGOCIO",
            "tipo_erro_tecnico": None,
            "severidade": normalize_severity(sem.get("severidade", "MEDIA"))
        }

    # ----------------------------------------------------
    # 6. FALLBACK
    # ----------------------------------------------------
    if code_str and code_str.isdigit() and code_str.startswith("2"):
        return {
            "resultado_operacional": "REJEICAO_NEGOCIO",
            "tipo_erro_tecnico": None,
            "severidade": "MEDIO"
        }
        
    return {
        "resultado_operacional": "REJEICAO_NEGOCIO" if not has_negation else "ERRO_TECNICO",
        "tipo_erro_tecnico": None if not has_negation else "PARSE",
        "severidade": "MEDIO"
    }

def classify_operational_result(message: str, code: str, functionality: str) -> dict:
    """
    Classifica a mensagem de log em um dos resultados operacionais chamando o motor unificado.
    """
    return classify_log_message(message, code, functionality)

def run_etl_pipeline(file_path: str, file_hash: str, conn, progress_callback=None) -> dict:
    """
    Executa o Pipeline ETL otimizado para arquivos grandes com suporte a Inteligência Operacional Contextual.
    """
    import time
    from core.database import SILVER_DIR
    
    file_path_db = file_path.replace("\\", "/")
    
    # 1. Fast-track se o arquivo já foi processado
    if check_file_already_processed(file_hash):
        if progress_callback:
            progress_callback(0.9, "Carregando do cache analítico...", "Restaurando views do cache Parquet")
        register_views_in_duckdb(conn, file_hash)
        total_logs = conn.execute("SELECT COUNT(*) FROM dim_log;").fetchone()[0]
        unique_protocols = conn.execute("SELECT COUNT(DISTINCT protocolo) FROM dim_log;").fetchone()[0]
        if progress_callback:
            progress_callback(1.0, "Carregado com sucesso do cache!", f"Total logs: {total_logs:,}")
        return {
            "status": "cached",
            "total_logs": total_logs,
            "unique_protocols": unique_protocols
        }
        
    start_time = time.time()
    
    # 2. Inicializa as tabelas temporárias estruturadas no DuckDB
    if progress_callback:
        progress_callback(0.02, "Inicializando tabelas temporárias no DuckDB...", "Preparando cache em disco")
        
    conn.execute("""
        CREATE OR REPLACE TABLE temp_dim_log (
            log_id VARCHAR,
            protocolo VARCHAR,
            data_evento TIMESTAMP,
            contratante VARCHAR,
            funcionalidade VARCHAR,
            status_geral VARCHAR,
            resultado_operacional VARCHAR
        );
        CREATE OR REPLACE TABLE temp_fact_rejeicoes (
            rejeicao_id VARCHAR,
            log_id VARCHAR,
            codigo_antt VARCHAR,
            categoria_operacional VARCHAR,
            tipo_rejeicao_semantica VARCHAR,
            subtipo_rejeicao VARCHAR,
            categoria VARCHAR,
            severidade VARCHAR,
            causa_raiz VARCHAR,
            orientacao_operacional VARCHAR,
            mensagem VARCHAR,
            mensagem_original VARCHAR,
            mensagem_normalizada VARCHAR,
            template_oficial VARCHAR,
            resultado_operacional VARCHAR,
            tipo_erro_tecnico VARCHAR
        );
        CREATE OR REPLACE TABLE temp_fact_entidades (
            entidade_id VARCHAR,
            rejeicao_id VARCHAR,
            entidade_tipo VARCHAR,
            entidade_valor VARCHAR
        );
    """)

    # 3. Detecta parâmetros do arquivo
    _, ext = os.path.splitext(file_path.lower())
    
    if progress_callback:
        progress_callback(0.05, "Validando estrutura e detectando formato...", f"Extensão: {ext}")
        
    if ext == ".csv":
        encodings = ["utf-8", "latin-1", "iso-8859-1"]
        delimiters = [";", ","]
        encoding_detected = "latin-1"
        delim_detected = ";"
        
        try:
            with open(file_path, "rb") as f:
                sample_bytes = f.read(50 * 1024)
            for encoding in encodings:
                try:
                    sample_str = sample_bytes.decode(encoding)
                    first_line = sample_str.split("\n")[0]
                    for d in delimiters:
                        if d in first_line:
                            delim_detected = d
                            break
                    encoding_detected = encoding
                    break
                except UnicodeDecodeError:
                    continue
        except Exception:
            pass
            
        duckdb_enc = "latin-1"
        if "utf" in encoding_detected.lower():
            duckdb_enc = "UTF-8"
            
        if progress_callback:
            progress_callback(0.08, "Parâmetros do CSV detectados", f"Encoding: {encoding_detected}, Delimitador: '{delim_detected}'")
            
        try:
            cols_desc = conn.execute(f"DESCRIBE SELECT * FROM read_csv_auto('{file_path_db}', delim='{delim_detected}', encoding='{duckdb_enc}', ignore_errors=True) LIMIT 0;").fetchall()
            raw_cols = [c[0] for c in cols_desc]
        except Exception as e:
            raise ValueError(f"Falha ao ler o arquivo CSV via DuckDB: {str(e)}")
            
        normalized_cols_mapping = {}
        for col in raw_cols:
            clean_col = col.strip().lower()
            normalized_cols_mapping[clean_col] = col
            
        select_exprs = []
        for clean_col, original_col in normalized_cols_mapping.items():
            select_exprs.append(f'"{original_col}" AS {clean_col}')
            
        select_clause = ", ".join(select_exprs)
        
        if progress_callback:
            progress_callback(0.12, "Carregando CSV bruto para o DuckDB...", "Gravando dados temporários brutos em disco")
            
        conn.execute(f"""
            CREATE OR REPLACE TABLE temp_raw_logs AS 
            SELECT {select_clause}
            FROM read_csv_auto('{file_path_db}', delim='{delim_detected}', encoding='{duckdb_enc}', ignore_errors=True);
        """)
        
    elif ext in [".xlsx", ".xls"]:
        if progress_callback:
            progress_callback(0.08, "Carregando planilha Excel...", "Lendo via Polars")
        try:
            df_excel = read_uploaded_file(file_path)
            if progress_callback:
                progress_callback(0.12, "Gravando Excel no DuckDB...", "Transferindo para cache em disco")
            conn.execute("CREATE OR REPLACE TABLE temp_raw_logs AS SELECT * FROM df_excel;")
            del df_excel
        except Exception as e:
            raise ValueError(f"Falha ao processar arquivo Excel: {str(e)}")
    else:
        raise ValueError("Formato de arquivo não suportado.")
        
    # 4. Configura chunks adaptativos baseados no tamanho do arquivo
    file_size_bytes = os.path.getsize(file_path)
    file_size_mb = file_size_bytes / (1024 * 1024)
    
    if file_size_mb > 500:
        chunk_size = 20000
    elif file_size_mb > 200:
        chunk_size = 35000
    else:
        chunk_size = 50000
        
    total_rows = conn.execute("SELECT COUNT(*) FROM temp_raw_logs;").fetchone()[0]
    num_chunks = max(1, (total_rows + chunk_size - 1) // chunk_size)
    
    temp_cols = [c[0] for c in conn.execute("DESCRIBE temp_raw_logs;").fetchall()]
    
    col_exprs = []
    if "contratante" in temp_cols:
        col_exprs.append("CAST(contratante AS VARCHAR) AS contratante")
    else:
        col_exprs.append("'CONTRATANTE DESCONHECIDO' AS contratante")
        
    if "funcionalidade" in temp_cols:
        col_exprs.append("CAST(funcionalidade AS VARCHAR) AS funcionalidade")
    else:
        col_exprs.append("'NÃO ESPECIFICADA' AS funcionalidade")
        
    if "cod_mensagem" in temp_cols:
        col_exprs.append("CAST(cod_mensagem AS VARCHAR) AS cod_mensagem")
    else:
        col_exprs.append("'' AS cod_mensagem")
        
    if "des_resposta" in temp_cols:
        col_exprs.append("CAST(des_resposta AS VARCHAR) AS des_resposta")
    else:
        col_exprs.append("'' AS des_resposta")
        
    if "cod_protocolo" in temp_cols:
        col_exprs.append("CAST(cod_protocolo AS VARCHAR) AS cod_protocolo")
    elif "protocolo" in temp_cols:
        col_exprs.append("CAST(protocolo AS VARCHAR) AS cod_protocolo")
    else:
        col_exprs.append("'SEM_PROTOCOLO' AS cod_protocolo")
        
    if "data" in temp_cols:
        col_exprs.append("CAST(data AS VARCHAR) AS data")
    else:
        col_exprs.append("NULL AS data")
        
    select_fields = ", ".join(col_exprs)
    
    # 5. Processamento dos chunks com segurança de cardinalidade
    total_entities_count = 0
    total_rejections_count = 0
    
    for offset_idx, offset in enumerate(range(0, total_rows, chunk_size)):
        chunk_start = time.time()
        
        chunk_df = conn.execute(f"""
            SELECT {select_fields}
            FROM temp_raw_logs
            WHERE rowid >= {offset} AND rowid < {offset + chunk_size};
        """).pl()
        
        chunk_df = chunk_df.with_columns([
            pl.col("contratante").fill_null("CONTRATANTE DESCONHECIDO"),
            pl.col("funcionalidade").fill_null("NÃO ESPECIFICADA"),
            pl.col("cod_mensagem").fill_null(""),
            pl.col("des_resposta").fill_null(""),
        ])
        
        # Parser da Data
        if "data" in chunk_df.columns and chunk_df["data"].null_count() < chunk_df.height:
            parsed_date = None
            for fmt in ["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M"]:
                try:
                    test_col = chunk_df.select(pl.col("data").str.to_datetime(fmt, strict=False))
                    if test_col["data"].null_count() < chunk_df.height:
                        parsed_date = pl.col("data").str.to_datetime(fmt, strict=False)
                        break
                except Exception:
                    continue
            if parsed_date is not None:
                chunk_df = chunk_df.with_columns(parsed_date.fill_null(datetime.now()))
            else:
                chunk_df = chunk_df.with_columns(pl.lit(datetime.now()).alias("data"))
        else:
            chunk_df = chunk_df.with_columns(pl.lit(datetime.now()).alias("data"))
            
        protocols = [extract_row_protocol(row) for row in chunk_df.iter_rows(named=True)]
        chunk_df = chunk_df.with_columns(pl.Series("protocolo", protocols))
        
        chunk_df = chunk_df.with_row_index("index_id", offset=offset)
        chunk_df = chunk_df.with_columns(
            (pl.lit("log_") + pl.col("index_id").cast(pl.String)).alias("log_id")
        )
        
        cod_mensagens = chunk_df["cod_mensagem"].to_list()
        des_respostas = chunk_df["des_resposta"].to_list()
        log_ids = chunk_df["log_id"].to_list()
        funcionalidades = chunk_df["funcionalidade"].to_list()
        
        parsed_codes, parsed_msgs = parse_payloads(cod_mensagens, des_respostas)
        
        rejections_records = []
        log_operational_results = {}
        
        for log_id, codes, msgs, functionality in zip(log_ids, parsed_codes, parsed_msgs, funcionalidades):
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
                    
            # Classifica cada split de mensagem e código
            row_op_results = []
            for msg, code in expanded_pairs:
                op_res = classify_operational_result(msg, code, functionality)
                row_op_results.append(op_res)
                
            # Determina o resultado operacional geral do log (linha)
            overall_res = "SUCESSO"
            if any(r["resultado_operacional"] == "ERRO_INFRAESTRUTURA" for r in row_op_results):
                overall_res = "ERRO_INFRAESTRUTURA"
            elif any(r["resultado_operacional"] == "ERRO_TECNICO" for r in row_op_results):
                overall_res = "ERRO_TECNICO"
            elif any(r["resultado_operacional"] == "REJEICAO_NEGOCIO" for r in row_op_results):
                overall_res = "REJEICAO_NEGOCIO"
            elif any(r["resultado_operacional"] == "ALERTA_OPERACIONAL" for r in row_op_results):
                overall_res = "ALERTA_OPERACIONAL"
            elif any(r["resultado_operacional"] == "SUCESSO_COM_ALERTA" for r in row_op_results):
                overall_res = "SUCESSO_COM_ALERTA"
                
            log_operational_results[log_id] = overall_res
            
            # Adiciona apenas os erros/alertas a fact_rejeicoes (exclui SUCESSO, SUCESSO_COM_ALERTA, ALERTA_OPERACIONAL)
            # Somente: REJEICAO_NEGOCIO, ERRO_TECNICO, ERRO_INFRAESTRUTURA
            rejections_count_for_row = 0
            for i, (msg, code) in enumerate(expanded_pairs):
                op_res = row_op_results[i]
                
                if op_res["resultado_operacional"] not in ["REJEICAO_NEGOCIO", "ERRO_TECNICO", "ERRO_INFRAESTRUTURA"]:
                    continue
                    
                if rejections_count_for_row >= 10:
                    break
                    
                if len(msg) > 5000:
                    msg = msg[:5000] + "... [TRUNCADO]"
                    
                sem = classify_message_semantically(msg, code)
                
                # Se for erro técnico/infra, tipo_rejeicao_semantica deve ser null,
                # a menos que tenhamos mapeado uma regra semântica de erro técnico específica
                is_custom_tech_error = sem["template_oficial"] != "OUTROS_NAO_CATEGORIZADO"
                
                tipo_rej_sem = sem["tipo_rejeicao_semantica"]
                if op_res["resultado_operacional"] in ["ERRO_TECNICO", "ERRO_INFRAESTRUTURA"] and not is_custom_tech_error:
                    tipo_rej_sem = None
                    
                rej_id = f"{log_id}_rej_{i}"
                
                # Preserva metadados estruturados caso seja um erro técnico customizado
                if op_res["resultado_operacional"] in ["ERRO_TECNICO", "ERRO_INFRAESTRUTURA"] and not is_custom_tech_error:
                    categoria_op = "INTEGRAÇÃO"
                    subtipo_rej = f"Erro técnico: {op_res['tipo_erro_tecnico']}"
                    categoria = "INTEGRAÇÃO"
                    causa_raiz = "INTEGRAÇÃO"
                    orientacao_op = f"Erro técnico detectado ({op_res['tipo_erro_tecnico']}). Contatar suporte."
                    temp_oficial = None
                else:
                    categoria_op = sem["categoria_operacional"]
                    subtipo_rej = sem["subtipo_rejeicao"]
                    categoria = sem["categoria_operacional"]
                    causa_raiz = sem["causa_raiz"]
                    orientacao_op = sem["orientacao_operacional"]
                    temp_oficial = sem["template_oficial"]

                rejections_records.append({
                    "rejeicao_id": rej_id,
                    "log_id": log_id,
                    "codigo_antt": code,
                    "categoria_operacional": categoria_op,
                    "tipo_rejeicao_semantica": tipo_rej_sem,
                    "subtipo_rejeicao": subtipo_rej,
                    "categoria": categoria,
                    "severidade": op_res["severidade"],
                    "causa_raiz": causa_raiz,
                    "orientacao_operacional": orientacao_op,
                    "mensagem": msg,
                    "mensagem_original": msg,
                    "mensagem_normalizada": sem["mensagem_normalizada"],
                    "template_oficial": temp_oficial,
                    "resultado_operacional": op_res["resultado_operacional"],
                    "tipo_erro_tecnico": op_res["tipo_erro_tecnico"]
                })
                rejections_count_for_row += 1
                
        # Constrói DataFrames do chunk
        rejections_schema = {
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
            "template_oficial": pl.String,
            "resultado_operacional": pl.String,
            "tipo_erro_tecnico": pl.String
        }
        if rejections_records:
            df_rejections = pl.DataFrame(rejections_records, schema=rejections_schema)
        else:
            df_rejections = pl.DataFrame(schema=rejections_schema)
            
        df_rejections = df_rejections.select([
            "rejeicao_id",
            "log_id",
            "codigo_antt",
            "categoria_operacional",
            "tipo_rejeicao_semantica",
            "subtipo_rejeicao",
            "categoria",
            "severidade",
            "causa_raiz",
            "orientacao_operacional",
            "mensagem",
            "mensagem_original",
            "mensagem_normalizada",
            "template_oficial",
            "resultado_operacional",
            "tipo_erro_tecnico"
        ])
            
        entity_prefix = f"ent_{offset}_"
        df_entities = extract_entities_from_rejections(df_rejections, prefix=entity_prefix)
        
        total_entities_count += df_entities.height
        total_rejections_count += df_rejections.height
        
        df_logs = (
            chunk_df.select([
                pl.col("log_id"),
                pl.col("protocolo"),
                pl.col("data").alias("data_evento"),
                pl.col("contratante"),
                pl.col("funcionalidade")
            ])
            .with_columns([
                pl.col("log_id")
                .map_elements(lambda lid: log_operational_results.get(lid, "SUCESSO"), return_dtype=pl.String)
                .alias("resultado_operacional"),
                pl.col("log_id")
                .map_elements(lambda lid: "SUCESSO" if log_operational_results.get(lid, "SUCESSO") in ["SUCESSO", "SUCESSO_COM_ALERTA"] else "ERRO", return_dtype=pl.String)
                .alias("status_geral")
            ])
            .select([
                "log_id",
                "protocolo",
                "data_evento",
                "contratante",
                "funcionalidade",
                "status_geral",
                "resultado_operacional"
            ])
        )
        
        conn.execute("INSERT INTO temp_dim_log SELECT * FROM df_logs;")
        conn.execute("INSERT INTO temp_fact_rejeicoes SELECT * FROM df_rejections;")
        conn.execute("INSERT INTO temp_fact_entidades SELECT * FROM df_entities;")
        
        if progress_callback:
            progress_pct = 0.12 + 0.68 * ((offset_idx + 1) / num_chunks)
            chunk_dur = time.time() - chunk_start
            progress_callback(
                progress_pct, 
                f"Processando lote {offset_idx + 1}/{num_chunks}...", 
                f"Processados {offset + chunk_df.height:,} de {total_rows:,} registros ({chunk_dur:.2f}s, extraídas {df_entities.height} entidades)"
            )
            
        del chunk_df
        del df_logs
        del df_rejections
        del df_entities
        
    # 6. Gravação na camada Silver Parquet
    if progress_callback:
        progress_callback(0.82, "Finalizando gravação dos dados analíticos...", "Estruturando views e gerando arquivos Parquet compactados")
        
    os.makedirs(SILVER_DIR, exist_ok=True)
    
    logs_path = os.path.join(SILVER_DIR, f"dim_log_{file_hash}.parquet").replace("\\", "/")
    rejections_path = os.path.join(SILVER_DIR, f"fact_rejeicoes_semanticas_{file_hash}.parquet").replace("\\", "/")
    entities_path = os.path.join(SILVER_DIR, f"fact_entidades_extraidas_{file_hash}.parquet").replace("\\", "/")
    
    conn.execute(f"COPY (SELECT *, '{file_hash}' AS file_hash FROM temp_dim_log) TO '{logs_path}' (FORMAT PARQUET, COMPRESSION ZSTD);")
    conn.execute(f"COPY (SELECT *, '{file_hash}' AS file_hash FROM temp_fact_rejeicoes) TO '{rejections_path}' (FORMAT PARQUET, COMPRESSION ZSTD);")
    conn.execute(f"COPY (SELECT *, '{file_hash}' AS file_hash FROM temp_fact_entidades) TO '{entities_path}' (FORMAT PARQUET, COMPRESSION ZSTD);")
    
    conn.execute("""
        DROP TABLE IF EXISTS temp_raw_logs;
        DROP TABLE IF EXISTS temp_dim_log;
        DROP TABLE IF EXISTS temp_fact_rejeicoes;
        DROP TABLE IF EXISTS temp_fact_entidades;
    """)
    
    # 7. Registra as views finais apontando para os Parquet
    if progress_callback:
        progress_callback(0.95, "Registrando views finais no banco DuckDB...", "Finalizando otimizações")
        
    register_views_in_duckdb(conn, file_hash)
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    print(f"[OP_LOG] ETL Concluído com sucesso:")
    print(f"  - Tempo total de processamento: {elapsed:.2f}s")
    print(f"  - Total de registros: {total_rows:,}")
    print(f"  - Total de chunks processados: {num_chunks}")
    print(f"  - Chunks de tamanho adaptativo: {chunk_size}")
    print(f"  - Total de rejeições criadas: {total_rejections_count:,}")
    print(f"  - Total de entidades extraídas: {total_entities_count:,}")
    print(f"  - Arquivo original: {file_path} ({file_size_mb:.2f} MB)")
    
    if progress_callback:
        progress_callback(1.00, "ETL concluído com sucesso!", f"Total de logs normalizados: {total_rows:,}. Tempo: {elapsed:.2f}s")
        
    return {
        "status": "processed",
        "total_logs": total_rows,
        "unique_protocols": conn.execute("SELECT COUNT(DISTINCT protocolo) FROM dim_log;").fetchone()[0]
    }
