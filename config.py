import re

# Definição das Regras do Motor Semântico de Rejeições
# Mapeia expressões regulares nas mensagens para tipos semânticos, causas raiz e orientações operacionais.
SEMANTIC_RULES = [
    {
        "categoria_operacional": "GEOLOCALIZACAO",
        "tipo_rejeicao_semantica": "CEP_NAO_CADASTRADO",
        "subtipo_rejeicao": "CEP_ORIGEM_INVALIDO",
        "severidade": "MEDIA",
        "orientacao": "Validar e corrigir o CEP de origem da viagem.",
        "patterns": [
            r"(?i)cep.*origem.*n(?:ao|ã)o.*cadastrado"
        ]
    },
    {
        "categoria_operacional": "GEOLOCALIZACAO",
        "tipo_rejeicao_semantica": "CEP_NAO_CADASTRADO",
        "subtipo_rejeicao": "CEP_DESTINO_INVALIDO",
        "severidade": "MEDIA",
        "orientacao": "Validar e corrigir o CEP de destino da viagem.",
        "patterns": [
            r"(?i)cep.*destino.*n(?:ao|ã)o.*cadastrado"
        ]
    },
    {
        "categoria_operacional": "GEOLOCALIZACAO",
        "tipo_rejeicao_semantica": "CEP_NAO_CADASTRADO",
        "subtipo_rejeicao": "CEP_GERAL_INVALIDO",
        "severidade": "MEDIA",
        "orientacao": "Informar coordenadas geográficas exatas (latitude/longitude) do local ou solicitar homologação de CEP.",
        "patterns": [
            r"(?i)cep.*n(?:ao|ã)o.*cadastrado",
            r"(?i)cep.*inexistente",
            r"(?i)cep.*n(?:ao|ã)o.*encontrado"
        ]
    },
    {
        "categoria_operacional": "GEOLOCALIZACAO",
        "tipo_rejeicao_semantica": "MUNICIPIO_INVALIDO",
        "subtipo_rejeicao": "MUNICIPIO_ORIGEM",
        "severidade": "MEDIA",
        "orientacao": "Revisar o código IBGE informado para o município de origem e validar se pertence à UF correspondente.",
        "patterns": [
            r"(?i)munic(?:i|í)pio.*origem.*inv",
            r"(?i)munic(?:i|í)pio.*origem.*n(?:ao|ã)o.*existe"
        ]
    },
    {
        "categoria_operacional": "GEOLOCALIZACAO",
        "tipo_rejeicao_semantica": "MUNICIPIO_INVALIDO",
        "subtipo_rejeicao": "MUNICIPIO_DESTINO",
        "severidade": "MEDIA",
        "orientacao": "Revisar o código IBGE informado para o município de destino e validar se pertence à UF correspondente.",
        "patterns": [
            r"(?i)munic(?:i|í)pio.*destino.*inv",
            r"(?i)munic(?:i|í)pio.*destino.*n(?:ao|ã)o.*existe"
        ]
    },
    {
        "categoria_operacional": "GEOLOCALIZACAO",
        "tipo_rejeicao_semantica": "MUNICIPIO_INVALIDO",
        "subtipo_rejeicao": "MUNICIPIO_GERAL",
        "severidade": "MEDIA",
        "orientacao": "Revisar o código IBGE informado para o município de origem ou destino.",
        "patterns": [
            r"(?i)munic(?:i|í)pio.*invalido",
            r"(?i)munic(?:i|í)pio.*n(?:ao|ã)o.*existe",
            r"(?i)ibge.*invalido",
            r"(?i)ibge.*munic(?:i|í)pio.*inv(?:a|á)lido"
        ]
    },
    {
        "categoria_operacional": "PLACA",
        "tipo_rejeicao_semantica": "PLACA_SEM_VINCULO",
        "subtipo_rejeicao": "VEICULO_OUTRO_PROP",
        "severidade": "ALTA",
        "orientacao": "Revisar o vínculo entre a placa do veículo e o RNTRC informado na ANTT. O veículo pode estar associado a outro transportador.",
        "patterns": [
            r"(?i)placa.*n(?:ao|ã)o.*pertence.*rntrc"
        ]
    },
    {
        "categoria_operacional": "PLACA",
        "tipo_rejeicao_semantica": "PLACA_SEM_VINCULO",
        "subtipo_rejeicao": "PLACA_SEM_VINCULO_RNTRC",
        "severidade": "ALTA",
        "orientacao": "Validar se o veículo possui vínculo ativo com o RNTRC informado no cadastro da ANTT.",
        "patterns": [
            r"(?i)placa.*sem.*v(?:i|í)nculo.*rntrc",
            r"(?i)placa.*n(?:ao|ã)o.*associada.*rntrc"
        ]
    },
    {
        "categoria_operacional": "TRANSPORTADOR",
        "tipo_rejeicao_semantica": "RNTRC_INATIVO",
        "subtipo_rejeicao": "RNTRC_BAIXADO",
        "severidade": "ALTA",
        "orientacao": "O RNTRC do transportador consta como baixado na ANTT. É necessário regularizar a situação cadastral do transportador.",
        "patterns": [
            r"(?i)rntrc.*baixado"
        ]
    },
    {
        "categoria_operacional": "TRANSPORTADOR",
        "tipo_rejeicao_semantica": "RNTRC_INATIVO",
        "subtipo_rejeicao": "RNTRC_SUSPENSO",
        "severidade": "ALTA",
        "orientacao": "O RNTRC do transportador está suspenso ou cancelado na ANTT. Verificar pendências financeiras ou cadastrais.",
        "patterns": [
            r"(?i)rntrc.*suspenso",
            r"(?i)rntrc.*cancelado"
        ]
    },
    {
        "categoria_operacional": "TRANSPORTADOR",
        "tipo_rejeicao_semantica": "RNTRC_INATIVO",
        "subtipo_rejeicao": "RNTRC_INATIVO_GERAL",
        "severidade": "ALTA",
        "orientacao": "Consultar a situação cadastral do RNTRC na ANTT. O cadastro precisa estar ATIVO e sem pendências para emissão.",
        "patterns": [
            r"(?i)rntrc.*inativo",
            r"(?i)rntrc.*inv(?:a|á)lido"
        ]
    },
    {
        "categoria_operacional": "TRANSPORTADOR",
        "tipo_rejeicao_semantica": "TRANSPORTADOR_NAO_ENCONTRADO",
        "subtipo_rejeicao": "TRANSPORTADOR_NAO_ENCONTRADO",
        "severidade": "ALTA",
        "orientacao": "Verificar se o CPF/CNPJ do transportador/TAC está correto no banco de dados e cadastrado ativo na ANTT.",
        "patterns": [
            r"(?i)transportador.*n(?:ao|ã)o.*encontrado",
            r"(?i)transportador.*n(?:ao|ã)o.*cadastrado",
            r"(?i)cpf.*cnpj.*transportador.*n(?:ao|ã)o.*encontrado"
        ]
    },
    {
        "categoria_operacional": "CIOT",
        "tipo_rejeicao_semantica": "CIOT_DUPLICADO",
        "subtipo_rejeicao": "CIOT_JA_EXISTENTE",
        "severidade": "MEDIA",
        "orientacao": "O contrato de frete já possui um CIOT ativo na ANTT. Verifique a numeração ou consulte o status antes de reenviar.",
        "patterns": [
            r"(?i)ciot.*duplicado",
            r"(?i)ciot.*j(?:a|á).*existente",
            r"(?i)ciot.*j(?:a|á).*cadastrado",
            r"(?i)contrato.*frete.*j(?:a|á).*cadastrado"
        ]
    },
    {
        "categoria_operacional": "CIOT",
        "tipo_rejeicao_semantica": "OPERACAO_CANCELADA",
        "subtipo_rejeicao": "OPERACAO_CANCELADA",
        "severidade": "BAIXA",
        "orientacao": "A operação não pode ser processada porque o CIOT correspondente já foi cancelado ou encerrado.",
        "patterns": [
            r"(?i)operac(?:ao|ão).*cancelada",
            r"(?i)ciot.*cancelado",
            r"(?i)ciot.*encerrado"
        ]
    },
    {
        "categoria_operacional": "DATA",
        "tipo_rejeicao_semantica": "DATA_FORA_TOLERANCIA",
        "subtipo_rejeicao": "DATA_INICIO_ANTERIOR",
        "severidade": "MEDIA",
        "orientacao": "A data de início da viagem não pode ser anterior ao limite permitido pelo sistema da ANTT.",
        "patterns": [
            r"(?i)data.*anterior"
        ]
    },
    {
        "categoria_operacional": "DATA",
        "tipo_rejeicao_semantica": "DATA_FORA_TOLERANCIA",
        "subtipo_rejeicao": "JANELA_TOLERANCIA",
        "severidade": "MEDIA",
        "orientacao": "Corrigir a data e hora de início de viagem. Validar tolerância retroativa ou futura.",
        "patterns": [
            r"(?i)data.*toler(?:a|â)ncia",
            r"(?i)data.*fora.*limite",
            r"(?i)iniciomovi.*invalido",
            r"(?i)data.*in(?:i|í)cio.*viagem"
        ]
    },
    {
        "categoria_operacional": "VEICULO",
        "tipo_rejeicao_semantica": "EIXO_INVALIDO",
        "subtipo_rejeicao": "EIXO_INCOMPATIVEL",
        "severidade": "ALTA",
        "orientacao": "Verificar se a quantidade de eixos informada bate com a configuração física do veículo cadastrado na ANTT.",
        "patterns": [
            r"(?i)eixos.*inv(?:a|á)lid",
            r"(?i)eixos.*incompat(?:i|í)vel",
            r"(?i)quantidade.*eixos"
        ]
    },
    {
        "categoria_operacional": "CARGA",
        "tipo_rejeicao_semantica": "NATUREZA_CARGA_INVALIDA",
        "subtipo_rejeicao": "NATUREZA_INVALIDA",
        "severidade": "MEDIA",
        "orientacao": "Revisar o código da natureza da carga em relação à tabela homologada da ANTT.",
        "patterns": [
            r"(?i)natureza.*carga.*inv(?:a|á)lid",
            r"(?i)natureza.*carga.*n(?:ao|ã)o.*exist"
        ]
    },
    {
        "categoria_operacional": "PAGAMENTO",
        "tipo_rejeicao_semantica": "PAGAMENTO_INCOMPATIVEL",
        "subtipo_rejeicao": "PAGAMENTO_INCOMPATIVEL_TAC",
        "severidade": "ALTA",
        "orientacao": "Revisar regras de pagamento para TAC/TAC-Equiparado (ex: pagamento eletrônico obrigatório, CPF do banco correspondente).",
        "patterns": [
            r"(?i)pagamento.*incompat(?:i|í)vel",
            r"(?i)pagamento.*inv(?:a|á)lido",
            r"(?i)dados.*pagamento.*inv(?:a|á)lidos",
            r"(?i)modalidade.*pagamento"
        ]
    },
    {
        "categoria_operacional": "INTEGRACAO",
        "tipo_rejeicao_semantica": "ERRO_INTEGRACAO",
        "subtipo_rejeicao": "API_ANTT_FORA",
        "severidade": "CRITICA",
        "orientacao": "Falha temporária de comunicação com a API da ANTT. Reenviar transação após alguns instantes.",
        "patterns": [
            r"(?i)erro.*integra[cç]ao.*antt",
            r"(?i)500.*antt",
            r"(?i)comunica[cç]ao.*antt"
        ]
    },
    {
        "categoria_operacional": "SISTEMA",
        "tipo_rejeicao_semantica": "EXCEPTION_SISTEMA",
        "subtipo_rejeicao": "EXCEPTION_INTERNA",
        "severidade": "CRITICA",
        "orientacao": "Erro de sistema interno. Contatar suporte técnico para avaliar logs de exceção.",
        "patterns": [
            r"(?i)exception",
            r"(?i)nullreference",
            r"(?i)erro.*interno.*sistema"
        ]
    }
]

# Estáticos de Severidade para Fallbacks de códigos gerais da ANTT
CODIGO_CATEGORIA_MAP = {
    "110": "SUCESSO",
    "111": "SUCESSO",
    "203": "TRANSPORTADOR",
    "204": "PAGAMENTO",
    "205": "VALIDAÇÃO",
    "207": "TRANSPORTADOR",
    "208": "DATA",
    "209": "LOCALIZAÇÃO",
    "210": "LOCALIZAÇÃO",
    "211": "CARGA",
    "217": "PLACA",
    "219": "CIOT",
    "222": "CIOT",
    "225": "DATA",
    "234": "JANELA OPERACIONAL",
    "263": "EXCEPTION",
    "269": "TOLERÂNCIA",
    "500": "INTEGRAÇÃO"
}

# Expressões Regulares compiladas para extração de entidades operacionais
REGEX_CEP = r"\b\d{5}-\d{3}\b|\b\d{8}\b"
REGEX_PLACA = r"\b[A-Za-z]{3}[- ]?[0-9][A-Za-z0-9][0-9]{2}\b"
REGEX_CPF = r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b"
REGEX_CNPJ = r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{14}\b"
REGEX_RNTRC = r"(?i)rntrc\s*:?\s*\b(\d{8,12})\b"
REGEX_CIOT = r"(?i)ciot\s*:?\s*\b(\d{12,16})\b"
REGEX_EIXO = r"\b(\d+)\s*(?:eixo|eixos)\b"
REGEX_MUNICIPIO = r"(?i)munic(?:i|í)pio\s*:?\s*\b(\d{7})\b"

# Estilos CSS Customizados para Visual Premium (Tema Escuro com sotaques de azul/violeta e glassmorphism)
CUSTOM_CSS = """
<style>
    /* Estilos globais e fontes */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Outfit', sans-serif;
        background-color: #0b0f19;
        color: #f1f5f9;
    }
    
    /* Configuração de cabeçalhos */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Outfit', sans-serif;
        color: #ffffff;
        font-weight: 600;
    }
    
    /* Cards de métricas premium com glassmorphism */
    div.css-card-premium {
        background: rgba(17, 24, 39, 0.7);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.4);
        transition: transform 0.2s ease-in-out, border-color 0.2s ease-in-out;
    }
    
    div.css-card-premium:hover {
        transform: translateY(-2px);
        border-color: rgba(99, 102, 241, 0.3);
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #0d1222;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Custom alerts */
    .stAlert {
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
</style>
"""
