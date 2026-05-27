import os
import duckdb
import polars as pl
import pandas as pd
from datetime import datetime
from core.pipeline import run_etl_pipeline
from core.database import init_directories

def generate_mock_data():
    """Gera um conjunto de dados mock contendo todos os cenários analíticos e entidades."""
    mock_records = [
        # Cenário 1: 1 código, 1 mensagem (JSON) -> Placa sem vínculo
        {
            "protocolo": "PROT001",
            "data": "2026-05-26 10:00:00",
            "contratante": "12.345.678/0001-00",
            "funcionalidade": "Emitir CIOT",
            "cod_mensagem": '{"Codigo":"217"}',
            "des_resposta": '{"Codigo":"217", "Mensagem":"A placa AAA-1234 não pertence ao RNTRC 12345678."}'
        },
        # Cenário 2: 1 código, múltiplas mensagens (JSON) -> CEP não cadastrado e Município inválido
        {
            "protocolo": "PROT002",
            "data": "2026-05-26 10:15:00",
            "contratante": "98.765.432/0001-99",
            "funcionalidade": "Emitir CIOT",
            "cod_mensagem": '{"Codigo":"209"}',
            "des_resposta": '{"Codigo":"209", "Mensagem":["O CEP 01001-000 ainda não está cadastrado.", "O código do município de origem não existe."]}'
        },
        # Cenário 3: Múltiplos códigos, múltiplas mensagens (JSON) -> Municípios inválidos e CEPs
        {
            "protocolo": "PROT003",
            "data": "2026-05-26 10:30:00",
            "contratante": "123.456.789-10",
            "funcionalidade": "Retificar CIOT",
            "cod_mensagem": '{"Codigo":"209,210"}',
            "des_resposta": '{"Codigo":"209,210", "Mensagem":["Município origem inválido", "Município destino inválido", "CEP 13010-080 não cadastrado"]}'
        },
        # Cenário 4: Não-JSON (Unstructured) -> CPF não cadastrado, placa suspensa
        {
            "protocolo": "PROT004",
            "data": "2026-05-26 10:45:00",
            "contratante": "45.678.901/0001-22",
            "funcionalidade": "Cancelar CIOT",
            "cod_mensagem": "203",
            "des_resposta": "Transportador CPF/CNPJ 111.222.333-44 não encontrado na ANTT. Placa BBB1C23 inativa."
        },
        # Cenário 5: Transação de Sucesso
        {
            "protocolo": "PROT005",
            "data": "2026-05-26 11:00:00",
            "contratante": "12.345.678/0001-00",
            "funcionalidade": "Consultar CIOT",
            "cod_mensagem": "110",
            "des_resposta": "Operação realizada com sucesso."
        },
        # Cenário 6: Múltiplas rejeições em formato não-JSON com delimitador ","
        {
            "protocolo": "PROT006",
            "data": "2026-05-26 11:15:00",
            "contratante": "12.345.678/0001-00",
            "funcionalidade": "Emitir CIOT",
            "cod_mensagem": "217,203",
            "des_resposta": '["A placa AAA-1234 não pertence ao RNTRC 12345678.","Transportador CPF/CNPJ 111.222.333-44 não encontrado na ANTT."]'
        },
        # Cenário 7: Mensagem com vírgula gramatical comum (não deve dividir)
        {
            "protocolo": "PROT007",
            "data": "2026-05-26 11:30:00",
            "contratante": "12.345.678/0001-00",
            "funcionalidade": "Emitir CIOT",
            "cod_mensagem": "217",
            "des_resposta": "A placa AAA-1234 não pertence ao RNTRC, ou o transportador está suspenso."
        },
        # Cenário 8: Teste CPF/CNPJ como DOC sem formatar (evitar RNTRC 11 digitos)
        {
            "protocolo": "PROT008",
            "data": "2026-05-26 11:45:00",
            "contratante": "12.345.678/0001-00",
            "funcionalidade": "Emitir CIOT",
            "cod_mensagem": "207",
            "des_resposta": "Rejeição - Não foi encontrado nenhum transportador com CPF/CNPJ 12345678901 e RNTRC 12345678."
        },
        # Cenário 9: Teste placa nominal de 2 letras (EF08H59) e prefixo Rejeição:
        {
            "protocolo": "PROT009",
            "data": "2026-05-26 12:00:00",
            "contratante": "12.345.678/0001-00",
            "funcionalidade": "Emitir CIOT",
            "cod_mensagem": "217",
            "des_resposta": "Rejeição - A placa EF08H59 não pertence ao transportador de RNTRC 12345678, ou o mesmo não está ativo."
        },
        # Cenário 10: Teste colapso de múltiplos placeholders de placas consecutivas
        {
            "protocolo": "PROT010",
            "data": "2026-05-26 12:15:00",
            "contratante": "12.345.678/0001-00",
            "funcionalidade": "Emitir CIOT",
            "cod_mensagem": "217",
            "des_resposta": "Rejeição: O(s) veículo(s) de placas AAA1234, BBB5678 está(ão) contratado(s) para outro contratante."
        }
    ]
    
    df = pd.DataFrame(mock_records)
    file_path = os.path.join("uploads", "mock_antt_logs.csv")
    df.to_csv(file_path, sep=";", index=False, encoding="utf-8")
    print(f"Arquivo mock gerado em: {file_path}")
    return file_path

def run_validation():
    print("Iniciando Validação de Integridade Analítica Semântica...")
    init_directories()
    
    # 1. Gera dados mock
    file_path = generate_mock_data()
    file_hash = "mock_hash_test_semantic_official_130"
    
    # 2. Conecta ao DuckDB em memória
    conn = duckdb.connect()
    
    # 3. Executa o pipeline ETL
    result = run_etl_pipeline(file_path, file_hash, conn)
    print("\nResultados do ETL:")
    print(f"Status: {result['status']}")
    print(f"Total de Transações: {result['total_logs']}")
    print(f"Protocolos Únicos: {result['unique_protocols']}")
    
    # 4. Verifica dim_log
    print("\n--- Verificação de dim_log ---")
    df_logs = conn.execute("SELECT * FROM dim_log").df()
    print(df_logs)
    
    # 5. Verifica fact_rejeicoes_semanticas
    print("\n--- Verificação de fact_rejeicoes_semanticas ---")
    df_rejs = conn.execute("""
        SELECT r.rejeicao_id, p.protocolo, r.categoria_operacional, r.tipo_rejeicao_semantica, r.subtipo_rejeicao, r.severidade, r.orientacao_operacional, r.mensagem, r.mensagem_original, r.mensagem_normalizada, r.template_oficial
        FROM fact_rejeicoes_semanticas r 
        JOIN dim_log p ON p.log_id = r.log_id
    """).df()
    print(df_rejs)
    
    # 6. Verifica fact_entidades_extraidas (deve associar cada entidade à sua respectiva rejeição semântica)
    print("\n--- Verificação de fact_entidades_extraidas ---")
    df_ent = conn.execute("""
        SELECT e.entidade_id, r.tipo_rejeicao_semantica, e.entidade_tipo, e.entidade_valor, r.mensagem
        FROM fact_entidades_extraidas e 
        JOIN fact_rejeicoes_semanticas r ON r.rejeicao_id = e.rejeicao_id
    """).df()
    print(df_ent)
    
    # Validações assertions
    assert df_logs.shape[0] == 10, f"Erro: dim_log deve ter 10 linhas (teve {df_logs.shape[0]})!"
    
    # PROT003 tinha 3 mensagens distintas. Deve gerar 3 rejeições
    p3_rejs = df_rejs[df_rejs["protocolo"] == "PROT003"]
    assert p3_rejs.shape[0] == 3, f"Erro: PROT003 deve gerar 3 rejeições semânticas (gerou {p3_rejs.shape[0]})!"
    
    # PROT006 tinha 2 rejeições separadas por ",". Deve gerar 2 rejeições
    p6_rejs = df_rejs[df_rejs["protocolo"] == "PROT006"]
    assert p6_rejs.shape[0] == 2, f"Erro: PROT006 deve gerar 2 rejeições semânticas (gerou {p6_rejs.shape[0]})!"
    assert "PLACA_SEM_VINCULO_RNTRC" in p6_rejs["tipo_rejeicao_semantica"].tolist()
    assert "TRANSPORTADOR_NAO_ENCONTRADO" in p6_rejs["tipo_rejeicao_semantica"].tolist()
    
    # PROT007 tinha vírgula gramatical mas não delimitador de aspas. Deve gerar 1 rejeição
    p7_rejs = df_rejs[df_rejs["protocolo"] == "PROT007"]
    assert p7_rejs.shape[0] == 1, f"Erro: PROT007 deve gerar 1 rejeição semântica (gerou {p7_rejs.shape[0]})!"
    
    # PROT008 deve ter CPF normalizado como DOC e RNTRC como RNTRC
    p8_rejs = df_rejs[df_rejs["protocolo"] == "PROT008"]
    assert p8_rejs.shape[0] == 1
    norm_p8 = p8_rejs.iloc[0]["mensagem_normalizada"]
    assert "{DOC}" in norm_p8, f"Erro: CPF 11 digitos deveria ser {{DOC}}, mas veio: {norm_p8}"
    assert "{RNTRC}" in norm_p8, f"Erro: RNTRC deveria ser {{RNTRC}}, mas veio: {norm_p8}"
    assert norm_p8.startswith("Rejeição:"), f"Erro: Deveria iniciar com 'Rejeição:', mas veio: {norm_p8}"
    
    # PROT009 deve ter a placa EF08H59 normalizada como {PLACA} e prefixo Rejeição:
    p9_rejs = df_rejs[df_rejs["protocolo"] == "PROT009"]
    assert p9_rejs.shape[0] == 1
    norm_p9 = p9_rejs.iloc[0]["mensagem_normalizada"]
    assert "{PLACA}" in norm_p9, f"Erro: placa EF08H59 deveria ser {{PLACA}}, mas veio: {norm_p9}"
    assert norm_p9.startswith("Rejeição:"), f"Erro: Deveria iniciar com 'Rejeição:', mas veio: {norm_p9}"
    
    # PROT010 deve colapsar múltiplos {PLACA} em um único {PLACA}
    p10_rejs = df_rejs[df_rejs["protocolo"] == "PROT010"]
    assert p10_rejs.shape[0] == 1
    norm_p10 = p10_rejs.iloc[0]["mensagem_normalizada"]
    assert norm_p10.count("{PLACA}") == 1, f"Erro: Placas multiplas deveriam colapsar em 1 {{PLACA}}, mas veio: {norm_p10}"
    assert norm_p10.startswith("Rejeição:"), f"Erro: Deveria iniciar com 'Rejeição:', mas veio: {norm_p10}"
    
    # Valida o vínculo da placa da rejeição da Placa
    r_placa = df_rejs[df_rejs["tipo_rejeicao_semantica"] == "PLACA_SEM_VINCULO_RNTRC"]
    assert not r_placa.empty, "Erro: Rejeição PLACA_SEM_VINCULO_RNTRC não mapeada!"
    assert r_placa.iloc[0]["subtipo_rejeicao"] == "A placa {0} não pertence ao transportador de RNTRC {1}, ou o mesmo não está ativo", "Erro: Descrição da placa incorreta!"
    
    # A placa AAA1234 deve estar vinculada à rejeição correspondente
    entidades_placa_rntrc = df_ent[df_ent["tipo_rejeicao_semantica"] == "PLACA_SEM_VINCULO_RNTRC"]
    assert "AAA1234" in entidades_placa_rntrc["entidade_valor"].tolist(), "Erro: Placa AAA1234 não foi extraída ou vinculada corretamente!"
    
    # CPFs extraídos e vinculados a TRANSPORTADOR_NAO_ENCONTRADO
    entidades_transp = df_ent[df_ent["tipo_rejeicao_semantica"] == "TRANSPORTADOR_NAO_ENCONTRADO"]
    assert "111.222.333-44" in entidades_transp["entidade_valor"].tolist(), "Erro: CPF do transportador não vinculado corretamente!"
    
    # Valida colunas obrigatórias novas da camada analítica
    assert "mensagem_original" in df_rejs.columns, "Erro: coluna mensagem_original ausente!"
    assert "mensagem_normalizada" in df_rejs.columns, "Erro: coluna mensagem_normalizada ausente!"
    assert "template_oficial" in df_rejs.columns, "Erro: coluna template_oficial ausente!"
    
    # Valida normalização
    norm_val = df_rejs[df_rejs["tipo_rejeicao_semantica"] == "PLACA_SEM_VINCULO_RNTRC"].iloc[0]["mensagem_normalizada"]
    assert "{PLACA}" in norm_val, f"Erro: mensagem_normalizada deveria conter {{PLACA}}, mas é: {norm_val}"
    assert "{RNTRC}" in norm_val, f"Erro: mensagem_normalizada deveria conter {{RNTRC}}, mas é: {norm_val}"
    
    # Valida template_oficial
    tmpl_placa = df_rejs[df_rejs["tipo_rejeicao_semantica"] == "PLACA_SEM_VINCULO_RNTRC"].iloc[0]["template_oficial"]
    assert tmpl_placa == "PLACA_SEM_VINCULO_RNTRC", f"Erro: template oficial incorreto: {tmpl_placa}"
    
    print("\n[OK] TODAS AS VALIDACOES DE INTEGRIDADE ANALITICA PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    run_validation()
