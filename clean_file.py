
with open('components/ordenes_servicio.py', 'rb') as f:
    content = f.read()

# Replace null bytes
clean_content = content.replace(b'\x00', b'')

# Also remove BOM if present (FF FE)
if clean_content.startswith(b'\xff\xfe'):
    clean_content = clean_content[2:]

with open('components/ordenes_servicio.py', 'wb') as f:
    f.write(clean_content)
