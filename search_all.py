import os

search_term = "date_sub"
found = False

for root, dirs, files in os.walk("."):
    # Ignora pastas de ambiente virtual
    if ".venv" in root or "venv" in root:
        continue
    for file in files:
        file_path = os.path.join(root, file)
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if search_term in line:
                        print(f"FOUND IN: {file_path} (Line {line_num}): {line.strip()}")
                        found = True
        except Exception as e:
            pass

if not found:
    print("No occurrences of 'date_sub' found in any file.")
