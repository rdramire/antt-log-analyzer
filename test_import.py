import ui.dashboard
import inspect

print("File imported:", ui.dashboard.__file__)
# Imprime as linhas 110-116 do arquivo importado para ver o que o Python está de fato lendo em memória
lines, start = inspect.getsourcelines(ui.dashboard.render_overview_tab)
print("\nSource code in memory:")
for i in range(100, 118):
    if i < len(lines):
        print(start + i, lines[i].rstrip())
