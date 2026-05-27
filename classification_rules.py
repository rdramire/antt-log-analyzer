import re

OFFICIAL_CLASSIFICATION_RULES = [
    {
        "codigo": "110",
        "categoria": "SUCESSO",
        "template_oficial": "SUCESSO_INSERCAO",
        "descricao_oficial": "Dados inseridos com sucesso",
        "patterns": [
            r"(?i)dados.*sucesso",
            r"(?i)sucesso.*inserido"
        ]
    },
    {
        "codigo": "111",
        "categoria": "SUCESSO",
        "template_oficial": "SUCESSO_GERACAO",
        "descricao_oficial": "Consulta realizada com sucesso. CIOT gerado com sucesso.",
        "patterns": [
            r"(?i)consulta.*sucesso",
            r"(?i)ciot.*gerado.*sucesso"
        ]
    },
    {
        "codigo": "203",
        "categoria": "TRANSPORTADOR",
        "template_oficial": "TRANSPORTADOR_NAO_ENCONTRADO",
        "descricao_oficial": "Transportador não encontrado ou RNTRC inexistente/inativo",
        "patterns": [
            r"(?i)transportador.*n(?:ao|ã)o.*encontrado",
            r"(?i)rntrc.*inexistente",
            r"(?i)rntrc.*inativo",
            r"(?i)transportador.*n(?:ao|ã)o.*cadastrado",
            r"(?i)cpf.*cnpj.*transportador.*n(?:ao|ã)o.*encontrado",
            r"(?i)transportador.*n(?:ao|ã)o.*localizado",
            r"(?i)transportador.*incompat(?:i|í)vel",
            r"(?i)transportador.*sem.*v(?:i|í)nculo.*antt"
        ]
    },
    {
        "codigo": "204",
        "categoria": "PAGAMENTO",
        "template_oficial": "PAGAMENTO_TAC_NAO_PERMITIDO",
        "descricao_oficial": "Não é permitido o tipo de pagamento informado para transportador TAC ou equiparado",
        "patterns": [
            r"(?i)n(?:ao|ã)o.*permitido.*tipo.*pagamento",
            r"(?i)pagamento.*tac",
            r"(?i)pagamento.*equiparado",
            r"(?i)dados.*pagamento.*inv(?:a|á)lido",
            r"(?i)modalidade.*pagamento",
            r"(?i)pagamento.*incompat(?:i|í)vel"
        ]
    },
    {
        "codigo": "205",
        "categoria": "VALIDAÇÃO",
        "template_oficial": "CAMPO_INVALIDO",
        "descricao_oficial": "O campo <nome do campo> é inválido",
        "patterns": [
            r"(?i)o.*campo.*(e|é).*inv(?:a|á)lido",
            r"(?i)campo.*inv(?:a|á)lido"
        ]
    },
    {
        "codigo": "207",
        "categoria": "TRANSPORTADOR",
        "template_oficial": "TRANSPORTADOR_NAO_ENCONTRADO",
        "descricao_oficial": "Não foi encontrado transportador contratado com CPF/CNPJ {0} e RNTRC {1}",
        "patterns": [
            r"(?i)n(?:ao|ã)o.*encontrado.*transportador.*contratado",
            r"(?i)transportador.*contratado.*cpf.*cnpj.*rntrc"
        ]
    },
    {
        "codigo": "208",
        "categoria": "DATA",
        "template_oficial": "DATA_INFERIOR_ATUAL",
        "descricao_oficial": "A data de início da viagem não pode ser inferior à data atual",
        "patterns": [
            r"(?i)data.*in(?:i|í)cio.*viagem.*inferior.*data.*atual",
            r"(?i)data.*in(?:i|í)cio.*viagem.*inferior.*atual",
            r"(?i)data.*inferior.*data.*atual"
        ]
    },
    {
        "codigo": "209",
        "categoria": "LOCALIZAÇÃO",
        "template_oficial": "LOCALIZACAO_ORIGEM_INVALIDA",
        "descricao_oficial": "Município/CEP origem inválido",
        "patterns": [
            r"(?i)cep.*origem.*inv(?:a|á)lido",
            r"(?i)cep.*origem.*n(?:ao|ã)o.*cadastrado",
            r"(?i)cep.*n(?:ao|ã)o.*cadastrado",
            r"(?i)cep.*inexistente",
            r"(?i)munic(?:i|í)pio.*origem.*inv",
            r"(?i)ibge.*origem",
            r"(?i)c(?:o|ó)digo.*ibge.*munic(?:i|í)pio.*origem"
        ]
    },
    {
        "codigo": "210",
        "categoria": "LOCALIZAÇÃO",
        "template_oficial": "MUNICIPIO_DESTINO_INVALIDO",
        "descricao_oficial": "Município destino inválido",
        "patterns": [
            r"(?i)munic(?:i|í)pio.*destino.*inv",
            r"(?i)ibge.*destino",
            r"(?i)c(?:o|ó)digo.*ibge.*munic(?:i|í)pio.*destino",
            r"(?i)munic(?:i|í)pio.*destino.*n(?:ao|ã)o.*existe",
            r"(?i)cep.*destino.*n(?:ao|ã)o.*cadastrado"
        ]
    },
    {
        "codigo": "210",
        "categoria": "EIXOS",
        "template_oficial": "QUANTIDADE_EIXOS_INVALIDA",
        "descricao_oficial": "Quantidade de eixos inválida para o tipo de veículo informado",
        "patterns": [
            r"(?i)quantidade.*eixos",
            r"(?i)eixo.*inv(?:a|á)lido",
            r"(?i)eixos.*incompat(?:i|í)vel"
        ]
    },
    {
        "codigo": "211",
        "categoria": "CARGA",
        "template_oficial": "NATUREZA_CARGA_INEXISTENTE",
        "descricao_oficial": "O código da natureza da carga informado não existe",
        "patterns": [
            r"(?i)natureza.*carga.*inv(?:a|á)lid",
            r"(?i)natureza.*carga.*n(?:ao|ã)o.*exist",
            r"(?i)c(?:o|ó)digo.*natureza.*carga"
        ]
    },
    {
        "codigo": "217",
        "categoria": "PLACA",
        "template_oficial": "PLACA_SEM_VINCULO_RNTRC",
        "descricao_oficial": "A placa {0} não pertence ao transportador de RNTRC {1}, ou o mesmo não está ativo",
        "patterns": [
            r"(?i)placa.*n(?:ao|ã)o.*pertence.*rntrc",
            r"(?i)placa.*sem.*v(?:i|í)nculo.*rntrc",
            r"(?i)placa.*n(?:ao|ã)o.*associada.*rntrc"
        ]
    },
    {
        "codigo": "219",
        "categoria": "CIOT",
        "template_oficial": "OPERACAO_JA_CADASTRADA",
        "descricao_oficial": "Código de identificação da operação já cadastrado",
        "patterns": [
            r"(?i)ciot.*duplicado",
            r"(?i)ciot.*j(?:a|á).*existente",
            r"(?i)ciot.*j(?:a|á).*cadastrado",
            r"(?i)contrato.*frete.*j(?:a|á).*cadastrado"
        ]
    },
    {
        "codigo": "222",
        "categoria": "CIOT",
        "template_oficial": "OPERACAO_JA_CANCELADA",
        "descricao_oficial": "Operação de Transporte já está cancelada",
        "patterns": [
            r"(?i)operac(?:ao|ão).*cancelada",
            r"(?i)ciot.*cancelado",
            r"(?i)ciot.*encerrado",
            r"(?i)op.*transp.*cancelada"
        ]
    },
    {
        "codigo": "225",
        "categoria": "DATA",
        "template_oficial": "DATA_INFERIOR_DECLARACAO",
        "descricao_oficial": "A data de início da viagem não pode ser inferior à data de declaração",
        "patterns": [
            r"(?i)data.*in(?:i|í)cio.*viagem.*inferior.*data.*declara[cç]ao",
            r"(?i)data.*in(?:i|í)cio.*inferior.*declara[cç]ao",
            r"(?i)iniciomovi.*invalido"
        ]
    },
    {
        "codigo": "234",
        "categoria": "JANELA OPERACIONAL",
        "template_oficial": "INTERVALO_SUPERIOR_90_DIAS",
        "descricao_oficial": "O intervalo entre a data de início e a data de fim da viagem não pode ser superior a 90 dias",
        "patterns": [
            r"(?i)superior.*90.*dias",
            r"(?i)intervalo.*data.*in(?:i|í)cio.*data.*fim.*superior.*90"
        ]
    },
    {
        "codigo": "269",
        "categoria": "TOLERÂNCIA",
        "template_oficial": "FORA_INTERVALO_TOLERANCIA",
        "descricao_oficial": "A data e hora da declaração está fora do intervalo de tolerância permitido para esta operação",
        "patterns": [
            r"(?i)fora.*intervalo.*toler(?:a|â)ncia",
            r"(?i)toler(?:a|â)ncia.*op",
            r"(?i)fora.*toler(?:a|â)ncia"
        ]
    },
    {
        "codigo": "500",
        "categoria": "INTEGRAÇÃO",
        "template_oficial": "ERRO_SISTEMA_RNTRC",
        "descricao_oficial": "Erro ao consultar dados da frota no sistema RNTRC",
        "patterns": [
            r"(?i)erro.*consultar.*dados.*frota",
            r"(?i)erro.*sistema.*rntrc",
            r"(?i)500.*rntrc",
            r"(?i)comunica[cç]ao.*rntrc",
            r"(?i)comunica[cç]ao.*antt",
            r"(?i)comunica[cç]ao.*api",
            r"(?i)erro.*comunica[cç]ao"
        ]
    }
]

# Mapa de orientações e ações corretivas oficiais para cada Categoria
OFFICIAL_GUIDANCE_MAP = {
    "SUCESSO": "Transação realizada com sucesso.",
    "TRANSPORTADOR": "Verificar a situação cadastral do RNTRC e do transportador na ANTT.",
    "PAGAMENTO": "Revisar as regras de pagamento para TAC/TAC-Equiparado (ex: pagamento eletrônico obrigatório).",
    "VALIDAÇÃO": "Revisar a estrutura e validação do campo rejeitado.",
    "DATA": "Corrigir a data/hora de início da viagem.",
    "LOCALIZAÇÃO": "Revisar código IBGE do município e a validade do CEP de origem/destino.",
    "EIXOS": "Verificar a quantidade de eixos informada contra o cadastro físico do veículo.",
    "CARGA": "Validar se o código da natureza da carga informado consta na tabela oficial da ANTT.",
    "PLACA": "Validar dados da placa e o seu vínculo cadastral com o RNTRC informado.",
    "CIOT": "Contrato de frete já possui CIOT ativo ou já foi cancelado na ANTT.",
    "JANELA OPERACIONAL": "Reduzir o intervalo entre a data de início e fim da viagem para menos de 90 dias.",
    "TOLERÂNCIA": "Ajustar a data de declaração dentro do limite de tolerância permitido.",
    "INTEGRAÇÃO": "Falha temporária de comunicação com o sistema RNTRC/ANTT. Reenviar após alguns instantes.",
    "SISTEMA": "Erro de sistema interno. Contatar suporte técnico.",
    "NOVO_CODIGO_NAO_CLASSIFICADO": "Nova rejeição não classificada. Necessita revisão manual.",
    "OUTROS_NAO_CATEGORIZADO": "Nova rejeição não classificada. Necessita revisão manual."
}

# Mapa de severidade estática para cada Categoria Oficial
SEVERIDADE_CATEGORIA_MAP = {
    "SUCESSO": "BAIXA",
    "TRANSPORTADOR": "ALTA",
    "PAGAMENTO": "ALTA",
    "VALIDAÇÃO": "MEDIA",
    "DATA": "MEDIA",
    "LOCALIZAÇÃO": "MEDIA",
    "EIXOS": "ALTA",
    "CARGA": "MEDIA",
    "PLACA": "ALTA",
    "CIOT": "MEDIA",
    "JANELA OPERACIONAL": "MEDIA",
    "TOLERÂNCIA": "MEDIA",
    "INTEGRAÇÃO": "CRITICA",
    "SISTEMA": "CRITICA",
    "NOVO_CODIGO_NAO_CLASSIFICADO": "MEDIA",
    "OUTROS_NAO_CATEGORIZADO": "MEDIA"
}

def get_severity_for_category(category: str) -> str:
    return SEVERIDADE_CATEGORIA_MAP.get(category, "MEDIA")

def get_guidance_for_category(category: str) -> str:
    return OFFICIAL_GUIDANCE_MAP.get(category, "Revisar descrição de resposta e códigos do retorno do log operacional.")

def normalize_message_placeholders(message: str) -> str:
    if not message or not isinstance(message, str):
        return ""
        
    msg = message
    
    # 0. Padroniza o prefixo/rótulo "Rejeição: " (sempre seguido por ":")
    msg = re.sub(r"(?i)^rejei[cç][aã]o\b\s*[-:]?\s*", "Rejeição: ", msg)
    msg = re.sub(r"(?i)\brejei[cç][aã]o\s*[-:]\s*", "Rejeição: ", msg)
    
    # 1. Datas (ex: dd/mm/yyyy hh:mm:ss, yyyy-mm-dd hh:mm:ss, dd/mm/yyyy)
    msg = re.sub(r"\b\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?\b", "{DATA}", msg)
    msg = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:[\sT]\d{2}:\d{2}(?::\d{2})?)?\b", "{DATA}", msg)
    
    # 2. Placas (Mercosul, antigas e customizadas, ex: AAA-1234, AAA1234, ABC1D23, EF08H59, EF-0859)
    # Suporta placas de 3 letras (AAA-1234, AAA1234, AAA1A11) e de 2 letras (EF08H59, EF-0859)
    msg = re.sub(r"\b(?:[A-Za-z]{3}[- ]?[0-9][A-Za-z0-9]{3}|[A-Za-z]{2}[- ]?[0-9][A-Za-z0-9]{3,4})\b", "{PLACA}", msg)
    
    # 3. CNPJ (formatado: XX.XXX.XXX/XXXX-XX)
    msg = re.sub(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", "{DOC}", msg)
    # 4. CPF (formatado: XXX.XXX.XXX-XX)
    msg = re.sub(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", "{DOC}", msg)
    
    # 5. CPFs/CNPJs não formatados (11 ou 14 dígitos)
    # IMPORTANTE: Deve rodar ANTES do RNTRC (8-12 dígitos) para evitar falsos positivos
    msg = re.sub(r"\b\d{14}\b", "{DOC}", msg)
    msg = re.sub(r"\b\d{11}\b", "{DOC}", msg)
    
    # 6. RNTRC (quando explicitado "rntrc" ou "RNTRC" seguido por números)
    msg = re.sub(r"(?i)\brntrc\s*:?\s*\b\d+\b", "RNTRC {RNTRC}", msg)
    # Se sobrar algum número isolado de 8 a 12 dígitos (exceto 11 dígitos, já tratados como DOC)
    msg = re.sub(r"\b\d{8,12}\b", "{RNTRC}", msg)
    
    # 7. CEP (ex: 13010-080 ou 8 dígitos isolados que sobram)
    msg = re.sub(r"\b\d{5}-\d{3}\b", "{CEP}", msg)
    msg = re.sub(r"\b\d{8}\b", "{CEP}", msg)
    
    # 8. Protocolos (ex: PROT001, etc.)
    msg = re.sub(r"(?i)protocolo\s*:?\s*\b[a-zA-Z0-9_-]+\b", "protocolo {PROTOCOLO}", msg)
    
    # 9. Valores e números flutuantes/inteiros gerais (como eixos ou códigos)
    msg = re.sub(r"\b\d+,\d{2}\b", "{VALOR}", msg)
    msg = re.sub(r"\b\d+\.\d{2}\b", "{VALOR}", msg)
    
    # 10. Colapso de múltiplos placeholders consecutivos ou listados (ex: {PLACA}, {PLACA} -> {PLACA})
    msg = re.sub(r"\{PLACA\}(?:\s*(?:,|\be\b|/)\s*\{PLACA\})+", "{PLACA}", msg)
    msg = re.sub(r"\{DOC\}(?:\s*(?:,|\be\b|/)\s*\{DOC\})+", "{DOC}", msg)
    msg = re.sub(r"\{RNTRC\}(?:\s*(?:,|\be\b|/)\s*\{RNTRC\})+", "{RNTRC}", msg)
    msg = re.sub(r"\{CEP\}(?:\s*(?:,|\be\b|/)\s*\{CEP\})+", "{CEP}", msg)
    
    # Ajustes finos de espaços múltiplos
    msg = re.sub(r"\s+", " ", msg).strip()
    
    return msg
