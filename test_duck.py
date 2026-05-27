import duckdb

conn = duckdb.connect()
conn.execute("CREATE TABLE t (d TIMESTAMP);")
conn.execute("INSERT INTO t VALUES ('2026-05-26 10:00:00'), ('2026-05-26 12:00:00');")
try:
    print("Testing date_diff('day', MIN(d), MAX(d)):")
    res = conn.execute("SELECT date_diff('day', MIN(d), MAX(d)) FROM t;").fetchone()[0]
    print("Result:", res)
except Exception as e:
    print("Error:", e)
