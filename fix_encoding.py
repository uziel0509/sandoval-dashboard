
# Read with errors='replace' to load content despite corruption
with open('components/ordenes_servicio.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Fix common corrupted chars if any specific patterns seen (like REPLACEMENT CHAR)
# The specific error was: DIAGN STICO
content = content.replace('DIAGN STICO', 'DIAGNÓSTICO')
content = content.replace('DIAGNSTICO', 'DIAGNÓSTICO')
content = content.replace('', '') # Remove other replacement chars if any

# Re-save as proper UTF-8
with open('components/ordenes_servicio.py', 'w', encoding='utf-8') as f:
    f.write(content)
