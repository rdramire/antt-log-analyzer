import re

# Regras oficiais de sucesso, confirmações operacionais e retornos válidos
SUCCESS_PATTERNS = [
    r"(?i)opera[cç]ã?o.*efetivada",
    r"(?i)inclus[ão]o?.*realizada.*sucesso",
    r"(?i)encerramento.*realizado",
    r"(?i)consulta.*realizada",
    r"(?i)ciot.*gerado",
    r"(?i)protocolo.*gerado",
    r"(?i)opera[cç]ã?o.*conclu[íi]da",
    r"(?i)sucesso",
    r"(?i)sucesso.*inserido",
    r"(?i)consulta.*sucesso",
    r"(?i)ciot.*gerado.*sucesso",
    r"(?i)viagem.*homologada",
    r"(?i)cadastrado.*sucesso",
    r"(?i)cadastro.*realizado",
    r"(?i)efetivado.*sucesso",
    r"(?i)concluido.*sucesso",
    r"(?i)sucesso.*concluido"
]

def is_success_message(message: str, code_antt: str = None, functionality: str = None) -> bool:
    """
    Determina se a mensagem indica um caso de sucesso com base em padrões de sucesso,
    no código de retorno e opcionalmente na funcionalidade.
    """
    if not message or not isinstance(message, str):
        return False
        
    msg_lower = message.lower().strip()
    
    # Prevenção explícita de negações para evitar falsos positivos
    negations = ["não", "nao", "nõo", "sem", "erro", "rejeitado", "rejeicao", "rejeição", "inválido", "invalido", "inativa", "inativo", "suspensa", "suspenso", "divergente", "falha"]
    if any(neg in msg_lower for neg in negations):
        return False
        
    # 1. Checar códigos de retorno conhecidos de sucesso da ANTT (110, 111, 100, etc.)
    if code_antt:
        code_str = str(code_antt).strip()
        if code_str in ["110", "111", "100", "200"]:
            return True
            
    # 2. Relação contextual: ex. 'Transportador localizado' é sucesso em consultas
    if functionality and any(keyword in functionality.lower() for keyword in ["consultar", "pesquisar", "obter", "query", "get", "retornar"]):
        if "localizado" in msg_lower or "encontrado" in msg_lower or "existente" in msg_lower or "ativo" in msg_lower:
            return True
            
    # 3. Match contra padrões regex de sucesso
    for pattern in SUCCESS_PATTERNS:
        if re.search(pattern, msg_lower):
            return True
            
    return False
