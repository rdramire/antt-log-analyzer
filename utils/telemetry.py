import time
import streamlit as st

def log_metric(name: str, duration: float, metadata: dict = None):
    """
    Registra uma métrica de execução operacional na session state do Streamlit.
    Útil para auditoria e observabilidade em tempo real do pipeline de dados.
    """
    if "telemetry" not in st.session_state:
        st.session_state["telemetry"] = []
        
    st.session_state["telemetry"].append({
        "timestamp": datetime_now_str(),
        "metric_name": name,
        "duration_seconds": round(duration, 4),
        "metadata": metadata or {}
    })

def datetime_now_str():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

class Timer:
    """Helper simple para medir o tempo de execução de blocos de código."""
    def __init__(self, name: str, metadata: dict = None):
        self.name = name
        self.metadata = metadata or {}
        
    def __enter__(self):
        self.start = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start
        log_metric(self.name, duration, self.metadata)
