"""
SANDOVAL Dashboard - Exportador de datos a Excel
"""

import os
from datetime import datetime

def export_ordenes_excel(filepath: str = None) -> str:
    """Exporta todas las órdenes a Excel"""
    import pandas as pd
    from utils.models import get_db, Orden, Cliente
    
    if not filepath:
        os.makedirs('exports', exist_ok=True)
        filepath = f"exports/ordenes_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    
    db = get_db()
    try:
        ordenes = db.query(Orden).all()
        clients = {c.id: c for c in db.query(Cliente).all()}
        
        data = []
        for o in ordenes:
            c = clients.get(o.cliente_id)
            total = sum(float(i.get('total', 0)) for i in (o.items_cotizacion or []))
            data.append({
                'Orden': o.consecutivo,
                'Fecha': o.fecha,
                'Estado': o.estado,
                'Cliente': f"{c.nombre} {c.apellidos}".strip() if c else '-',
                'Doc. Cliente': o.cliente_id,
                'Placa': o.vehiculo_placa,
                'Motivo': o.motivo,
                'Técnico': o.tecnico,
                'KM': o.km,
                'Tipo': o.tipo,
                'Total Cotización': total,
                'Aprobación': o.approval_status,
            })
        
        df = pd.DataFrame(data)
        df.to_excel(filepath, index=False, sheet_name='Órdenes')
    finally:
        db.close()
    
    return filepath


def export_clientes_excel(filepath: str = None) -> str:
    """Exporta clientes a Excel"""
    import pandas as pd
    from utils.models import get_db, Cliente
    
    if not filepath:
        os.makedirs('exports', exist_ok=True)
        filepath = f"exports/clientes_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    
    db = get_db()
    try:
        clientes = db.query(Cliente).all()
        data = [{
            'DNI/RUC': c.id, 'Nombre': c.nombre, 'Apellidos': c.apellidos,
            'Email': c.email, 'Teléfono': c.telefono, 'Dirección': c.direccion,
            'Ciudad': c.ciudad, 'País': c.pais, 'Tipo': c.tipo,
        } for c in clientes]
        pd.DataFrame(data).to_excel(filepath, index=False, sheet_name='Clientes')
    finally:
        db.close()
    return filepath


def export_inventario_excel(filepath: str = None) -> str:
    """Exporta inventario a Excel"""
    import pandas as pd
    from utils.models import get_db, ItemInventario
    
    if not filepath:
        os.makedirs('exports', exist_ok=True)
        filepath = f"exports/inventario_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    
    db = get_db()
    try:
        items = db.query(ItemInventario).all()
        data = [{
            'Código': i.codigo, 'Nombre': i.nombre, 'Categoría': i.categoria,
            'Tipo': i.tipo, 'Costo': i.costo, 'Rentabilidad %': i.rentabilidad,
            'Precio Venta': i.precio, 'Stock': i.stock, 'Stock Mínimo': i.stock_minimo,
            'Valor Total': i.costo * i.stock,
        } for i in items]
        pd.DataFrame(data).to_excel(filepath, index=False, sheet_name='Inventario')
    finally:
        db.close()
    return filepath


def import_clientes_excel(file_bytes: bytes) -> tuple:
    """Importa clientes desde Excel. Retorna (count, errors)"""
    import pandas as pd
    import io
    from utils.models import get_db, Cliente
    
    df = pd.read_excel(io.BytesIO(file_bytes))
    
    # Mapeo flexible de columnas
    col_map = {
        'id': ['id', 'dni', 'ruc', 'dni/ruc', 'documento', 'id documento'],
        'nombre': ['nombre', 'nombres', 'nombre completo', 'razón social', 'razon social'],
        'apellidos': ['apellido', 'apellidos'],
        'email': ['email', 'correo', 'e-mail'],
        'telefono': ['telefono', 'teléfono', 'celular', 'tel'],
        'direccion': ['direccion', 'dirección', 'address'],
        'ciudad': ['ciudad', 'city'],
        'tipo': ['tipo', 'type'],
    }
    
    mapped = {}
    lower_cols = {c.lower().strip(): c for c in df.columns}
    for field, aliases in col_map.items():
        for alias in aliases:
            if alias in lower_cols:
                mapped[field] = lower_cols[alias]
                break
    
    count = 0
    errors = []
    db = get_db()
    try:
        for _, row in df.iterrows():
            try:
                cid = str(row.get(mapped.get('id', ''), '')).strip()
                if not cid or cid == 'nan':
                    continue
                
                if db.query(Cliente).filter_by(id=cid).first():
                    continue  # Skip existing
                
                db.add(Cliente(
                    id=cid,
                    nombre=str(row.get(mapped.get('nombre', ''), '')).strip(),
                    apellidos=str(row.get(mapped.get('apellidos', ''), '')).strip() if 'apellidos' in mapped else '',
                    email=str(row.get(mapped.get('email', ''), '')).strip() if 'email' in mapped else '',
                    telefono=str(row.get(mapped.get('telefono', ''), '')).strip() if 'telefono' in mapped else '',
                    direccion=str(row.get(mapped.get('direccion', ''), '')).strip() if 'direccion' in mapped else '',
                    ciudad=str(row.get(mapped.get('ciudad', ''), '')).strip() if 'ciudad' in mapped else '',
                    tipo=str(row.get(mapped.get('tipo', ''), 'Persona')).strip() if 'tipo' in mapped else 'Persona',
                ))
                count += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(str(e))
    finally:
        db.close()
    
    return count, errors


def import_vehiculos_excel(file_bytes: bytes) -> tuple:
    """Importa vehículos desde Excel"""
    import pandas as pd
    import io
    from utils.models import get_db, Vehiculo
    
    df = pd.read_excel(io.BytesIO(file_bytes))
    
    col_map = {
        'placa': ['placa', 'plate', 'patente'],
        'cliente_id': ['cliente_id', 'id propietario', 'propietario', 'dueño', 'owner'],
        'marca': ['marca', 'brand'],
        'modelo': ['modelo', 'model'],
        'año': ['año', 'year', 'anio'],
        'color': ['color'],
        'vin': ['vin', 'chasis'],
    }
    
    mapped = {}
    lower_cols = {c.lower().strip(): c for c in df.columns}
    for field, aliases in col_map.items():
        for alias in aliases:
            if alias in lower_cols:
                mapped[field] = lower_cols[alias]
                break
    
    count = 0
    errors = []
    db = get_db()
    try:
        for _, row in df.iterrows():
            try:
                placa = str(row.get(mapped.get('placa', ''), '')).strip().upper()
                if not placa or placa == 'NAN':
                    continue
                if db.query(Vehiculo).filter_by(placa=placa).first():
                    continue
                db.add(Vehiculo(
                    placa=placa,
                    cliente_id=str(row.get(mapped.get('cliente_id', ''), '')).strip() if 'cliente_id' in mapped else None,
                    marca=str(row.get(mapped.get('marca', ''), '')).strip() if 'marca' in mapped else '',
                    modelo=str(row.get(mapped.get('modelo', ''), '')).strip() if 'modelo' in mapped else '',
                    año=str(row.get(mapped.get('año', ''), '')).strip() if 'año' in mapped else '',
                    color=str(row.get(mapped.get('color', ''), '')).strip() if 'color' in mapped else '',
                    vin=str(row.get(mapped.get('vin', ''), '')).strip() if 'vin' in mapped else '',
                ))
                count += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(str(e))
    finally:
        db.close()
    
    return count, errors


def export_generic_excel(title: str, headers: list, data: list, filename_prefix: "str", filepath: str = None) -> str:
    """Genera un archivo Excel sofisticado y profesional con formato premium"""
    import pandas as pd
    import os

    if not filepath:
        os.makedirs('exports', exist_ok=True)
        filename = f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join('exports', filename)

    # Crear el libro y la hoja directamente para máximo control
    import xlsxwriter
    workbook = xlsxwriter.Workbook(filepath)
    worksheet = workbook.add_worksheet('Reporte')
    
    # --- CONFIGURACIÓN DE ESTILOS ---
    # Fondo de pantalla (Watermark tiling)
    logo_path = 'assets/logo_sandoval.jpg'
    if os.path.exists(logo_path):
        worksheet.set_background(logo_path)

    # Formatos de celda
    fmt_title = workbook.add_format({
        'bold': True, 'font_size': 18, 'font_color': '#154c79',
        'align': 'left', 'valign': 'vcenter'
    })
    fmt_subtitle = workbook.add_format({
        'font_size': 10, 'font_color': '#666666',
        'align': 'left', 'valign': 'vcenter'
    })
    fmt_header = workbook.add_format({
        'bold': True, 'font_color': 'white', 'bg_color': '#154c79',
        'border': 1, 'border_color': '#0d2d48',
        'align': 'center', 'valign': 'vcenter', 'font_size': 10
    })
    fmt_cell = workbook.add_format({
        'border': 1, 'border_color': '#dddddd', 'font_size': 9,
        'valign': 'vcenter'
    })
    fmt_cell_alt = workbook.add_format({
        'border': 1, 'border_color': '#dddddd', 'font_size': 9,
        'valign': 'vcenter', 'bg_color': '#f9f9f9'
    })

    # --- ENCABEZADO ---
    # Insertar logo pequeño en el header (opcional si ya está de fondo, pero le da clase)
    if os.path.exists(logo_path):
        worksheet.insert_image('A1', logo_path, {'x_scale': 0.15, 'y_scale': 0.15, 'x_offset': 5, 'y_offset': 5})
    
    worksheet.write('B1', title, fmt_title)
    worksheet.write('B2', f'Generado el: {datetime.now().strftime("%d/%m/%Y %H:%M")}', fmt_subtitle)
    worksheet.write('B3', f'Mecánica y Repuestos Sandoval EIRL', fmt_subtitle)
    
    # Comenzar la tabla en la fila 5
    start_row = 5
    
    # Escribir cabeceras
    for col_num, header in enumerate(headers):
        worksheet.write(start_row, col_num, header, fmt_header)
        
    # Escribir datos con cebrado
    for row_num, row_data in enumerate(data):
        fmt = fmt_cell_alt if row_num % 2 == 1 else fmt_cell
        for col_num, cell_value in enumerate(row_data):
            worksheet.write(start_row + 1 + row_num, col_num, cell_value, fmt)

    # Ajuste automático de columnas
    for col_num, header in enumerate(headers):
        # Medir longitud máxima en esa columna
        max_len = len(str(header))
        for row in data:
            if row[col_num]:
                max_len = max(max_len, len(str(row[col_num])))
        worksheet.set_column(col_num, col_num, max_len + 5)

    # Autofiltros y congelar paneles
    worksheet.autofilter(start_row, 0, start_row + len(data), len(headers) - 1)
    worksheet.freeze_panes(start_row + 1, 0)

    workbook.close()
    return filepath


def ask_save_path(default_filename: str) -> str:
    """Abre un diálogo nativo de Windows para elegir dónde guardar el archivo"""
    import tkinter as tk
    from tkinter import filedialog
    
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    
    file_path = filedialog.asksaveasfilename(
        defaultextension=".xlsx",
        initialfile=default_filename,
        filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        title="Guardar reporte Excel"
    )
    
    root.destroy()
    return file_path
