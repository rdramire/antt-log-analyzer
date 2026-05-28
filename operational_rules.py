import re

# Matriz de regras contextuais: mapeia padrões de funcionalidade, código e mensagem 
# para resultados operacionais, tipos de erros técnicos e severidades.
CONTEXTUAL_RULES = [
    # Idempotência (Já cadastrado/processado/existente) -> SUCESSO_COM_ALERTA
    {
        "funcionalidades": [".*"],
        "codigos": [".*"],
        "patterns": [
            r"(?i)j(?:a|á).*cadastrado",
            r"(?i)j(?:a|á).*existente",
            r"(?i)j(?:a|á).*processado",
            r"(?i)j(?:a|á).*encerrado",
            r"(?i)j(?:a|á).*associado",
            r"(?i)j(?:a|á).*concluido",
            r"(?i)j(?:a|á).*efetivado",
            r"(?i)previamente.*concluido",
            r"(?i)previamente.*realizado",
            r"(?i)duplicado"
        ],
        "resultado_operacional": "SUCESSO_COM_ALERTA",
        "tipo_erro_tecnico": None,
        "severidade": "INFO"
    },
    # Sucessos contextuais: "Transportador localizado" -> SUCESSO em Consultas
    {
        "funcionalidades": [".*consultar.*", ".*pesquisar.*", ".*obter.*", ".*query.*", ".*get.*", ".*retornar.*"],
        "codigos": [".*"],
        "patterns": [
            r"(?i)localizado",
            r"(?i)encontrado",
            r"(?i)ativo",
            r"(?i)existente"
        ],
        "resultado_operacional": "SUCESSO",
        "tipo_erro_tecnico": None,
        "severidade": "INFO"
    },
    # Infraestrutura: Timeout
    {
        "funcionalidades": [".*"],
        "codigos": ["503", "502", "504"],
        "patterns": [".*"],
        "resultado_operacional": "ERRO_INFRAESTRUTURA",
        "tipo_erro_tecnico": "TIMEOUT",
        "severidade": "CRITICO"
    },
    {
        "funcionalidades": [".*"],
        "codigos": [".*"],
        "patterns": [
            r"(?i)timeout",
            r"(?i)timed.*out",
            r"(?i)tempo.*limite.*esgotado",
            r"(?i)requisic(?:ao|ão).*expirada"
        ],
        "resultado_operacional": "ERRO_INFRAESTRUTURA",
        "tipo_erro_tecnico": "TIMEOUT",
        "severidade": "CRITICO"
    },
    # Infraestrutura: SSL
    {
        "funcionalidades": [".*"],
        "codigos": [".*"],
        "patterns": [
            r"(?i)ssl",
            r"(?i)certificate",
            r"(?i)handshake",
            r"(?i)certificado.*inv(?:a|á)lido",
            r"(?i)seguran[cç]a.*conex"
        ],
        "resultado_operacional": "ERRO_INFRAESTRUTURA",
        "tipo_erro_tecnico": "SSL",
        "severidade": "CRITICO"
    },
    # Erro Técnico: Autenticação/Permissão
    {
        "funcionalidades": [".*"],
        "codigos": [".*"],
        "patterns": [
            r"(?i)auth",
            r"(?i)unauthorized",
            r"(?i)token",
            r"(?i)credencia",
            r"(?i)permissao",
            r"(?i)n(?:ao|ã)o.*autorizado",
            r"(?i)acesso.*negado",
            r"(?i)senha.*inv(?:a|á)lida"
        ],
        "resultado_operacional": "ERRO_TECNICO",
        "tipo_erro_tecnico": "AUTH",
        "severidade": "CRITICO"
    },
    # Infraestrutura: Conexão Geral
    {
        "funcionalidades": [".*"],
        "codigos": [".*"],
        "patterns": [
            r"(?i)connection",
            r"(?i)conexao",
            r"(?i)indisponivel",
            r"(?i)fora.*ar",
            r"(?i)comunicacao",
            r"(?i)host.*unreachable",
            r"(?i)socket.*error"
        ],
        "resultado_operacional": "ERRO_INFRAESTRUTURA",
        "tipo_erro_tecnico": "CONEXAO",
        "severidade": "CRITICO"
    },
    # Erro Técnico: Rate Limit
    {
        "funcionalidades": [".*"],
        "codigos": [".*"],
        "patterns": [
            r"(?i)rate.*limit",
            r"(?i)limite.*requisic",
            r"(?i)excedeu.*requisic",
            r"(?i)too.*many.*requests"
        ],
        "resultado_operacional": "ERRO_INFRAESTRUTURA",
        "tipo_erro_tecnico": "RATE_LIMIT",
        "severidade": "ALTO"
    },
    # Erro Técnico: Parse / Serialização
    {
        "funcionalidades": [".*"],
        "codigos": [".*"],
        "patterns": [
            r"(?i)json",
            r"(?i)xml",
            r"(?i)parser",
            r"(?i)parsing",
            r"(?i)mapeamento",
            r"(?i)deserializ",
            r"(?i)serializ",
            r"(?i)malformado"
        ],
        "resultado_operacional": "ERRO_TECNICO",
        "tipo_erro_tecnico": "PARSE",
        "severidade": "CRITICO"
    },
    # Erro Técnico: SOAP Fault
    {
        "funcionalidades": [".*"],
        "codigos": [".*"],
        "patterns": [
            r"(?i)soap",
            r"(?i)fault",
            r"(?i)envelope.*inv(?:a|á)lido"
        ],
        "resultado_operacional": "ERRO_TECNICO",
        "tipo_erro_tecnico": "SOAP_FAULT",
        "severidade": "CRITICO"
    }
]

def get_contextual_result(message: str, code_antt: str, functionality: str) -> dict:
    """
    Avalia a mensagem, código e funcionalidade contra a matriz de regras contextuais.
    Retorna um dicionário com as chaves:
    - resultado_operacional
    - tipo_erro_tecnico
    - severidade
    Retorna None se não bater em nenhuma regra contextual específica.
    """
    msg_clean = str(message).strip() if message else ""
    code_clean = str(code_antt).strip() if code_antt else ""
    func_clean = str(functionality).strip() if functionality else ""
    
    for rule in CONTEXTUAL_RULES:
        # 1. Verifica se a funcionalidade bate
        func_match = False
        for f_pat in rule["funcionalidades"]:
            if re.match(f_pat, func_clean, re.IGNORECASE):
                func_match = True
                break
        if not func_match:
            continue
            
        # 2. Verifica se o código bate
        code_match = False
        for c_pat in rule["codigos"]:
            if re.match(c_pat, code_clean, re.IGNORECASE):
                code_match = True
                break
        if not code_match:
            continue
            
        # 3. Verifica se a mensagem bate
        msg_match = False
        for m_pat in rule["patterns"]:
            if re.search(m_pat, msg_clean, re.IGNORECASE):
                msg_match = True
                break
        if not msg_match:
            continue
            
        # Encontrou match completo
        if rule["resultado_operacional"] == "SUCESSO":
            negations = ["não", "nao", "nõo", "sem", "erro", "rejeitado", "rejeicao", "rejeição", "inválido", "invalido", "inativa", "inativo", "suspensa", "suspenso", "divergente", "falha"]
            if any(neg in msg_clean.lower() for neg in negations):
                continue
                
        return {
            "resultado_operacional": rule["resultado_operacional"],
            "tipo_erro_tecnico": rule["tipo_erro_tecnico"],
            "severidade": rule["severidade"]
        }
        
    return None
