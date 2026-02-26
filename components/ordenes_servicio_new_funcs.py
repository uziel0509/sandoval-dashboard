
def open_customer_preview(consecutivo):
    """Muestra previsualización de lo que ve el cliente"""
    db = get_db()
    try:
        order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if not order:
            theme.notify_error('Orden no encontrada')
            return
        
        client = db.query(Cliente).filter_by(id=order.cliente_id).first()
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first()
        
        # Copiamos la lógica de render de approval.py
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl bg-[#1c2025] p-0 border border-[#333]'):
            with ui.row().classes('w-full items-center justify-between p-4 border-b border-[#333]'):
                ui.label(f'Vista Cliente - Orden {consecutivo}').classes('text-xl font-bold text-white')
                ui.button(icon='close', on_click=dialog.close).props('flat round color=grey')
            
            with ui.scroll_area().classes('w-full p-6').style('height: 80vh'):
                # Header Sandova
                with ui.card().classes('w-full bg-[#1c2025] border border-[#333] p-6 mb-4'):
                    with ui.row().classes('w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('build_circle', size='40px').classes('text-[#ccff00]')
                            with ui.column().classes('gap-0'):
                                ui.label('SANDOVAL').classes('text-2xl font-bold text-[#ccff00]')
                                ui.label('Mecánica y Repuestos').classes('text-xs text-gray-400')
                        ui.label(f'Orden {order.consecutivo}').classes('text-xl font-bold text-white')
                
                # Info Orden
                with ui.card().classes('w-full bg-[#1c2025] border border-[#333] p-6 mb-4'):
                    ui.label('DETALLE DE LA ORDEN').classes('text-lg font-bold text-[#ccff00] mb-4')
                    with ui.grid(columns=2).classes('w-full gap-4'):
                        with ui.column().classes('gap-0'):
                            ui.label('Estado').classes('text-xs text-gray-500 uppercase')
                            ui.label(order.estado).classes('text-white font-medium')
                        with ui.column().classes('gap-0'):
                            ui.label('Fecha').classes('text-xs text-gray-500 uppercase')
                            ui.label(order.fecha).classes('text-white font-medium')
                        with ui.column().classes('gap-0'):
                            ui.label('Técnico').classes('text-xs text-gray-500 uppercase')
                            ui.label(order.tecnico or 'Por asignar').classes('text-white font-medium')
                        with ui.column().classes('gap-0'):
                            ui.label('Kilometraje').classes('text-xs text-gray-500 uppercase')
                            ui.label(f'{order.km} km' if order.km else '-').classes('text-white font-medium')
                    
                    ui.separator().classes('my-4')
                    ui.label('MOTIVO DE INGRESO').classes('text-sm font-bold text-gray-400 mb-2')
                    ui.label(order.motivo or 'No especificado').classes('text-white')
                    
                    if order.diagnostico:
                        ui.separator().classes('my-4')
                        ui.label('DIAGNÓSTICO').classes('text-sm font-bold text-gray-400 mb-2')
                        ui.label(order.diagnostico).classes('text-white')
                
                # Info Vehículo
                if vehicle:
                    with ui.card().classes('w-full bg-[#1c2025] border border-[#333] p-6 mb-4'):
                        ui.label('VEHÍCULO').classes('text-lg font-bold text-[#ccff00] mb-4')
                        with ui.grid(columns=2).classes('w-full gap-4'):
                            with ui.column().classes('gap-0'):
                                ui.label('Marca/Modelo').classes('text-xs text-gray-500 uppercase')
                                ui.label(f'{vehicle.marca} {vehicle.modelo}').classes('text-white font-medium')
                            with ui.column().classes('gap-0'):
                                ui.label('Placa').classes('text-xs text-gray-500 uppercase')
                                ui.label(vehicle.placa).classes('text-white font-medium')
                            with ui.column().classes('gap-0'):
                                ui.label('Año').classes('text-xs text-gray-500 uppercase')
                                ui.label(vehicle.año).classes('text-white font-medium')
                            with ui.column().classes('gap-0'):
                                ui.label('Color').classes('text-xs text-gray-500 uppercase')
                                ui.label(vehicle.color).classes('text-white font-medium')
                            with ui.column().classes('gap-0'):
                                ui.label('VIN').classes('text-xs text-gray-500 uppercase')
                                ui.label(vehicle.vin or '-').classes('text-white font-medium')

                # Evidencia
                if order.fotos_evidencia and isinstance(order.fotos_evidencia, list):
                    with ui.card().classes('w-full bg-[#1c2025] border border-[#333] p-6 mb-4'):
                        ui.label('EVIDENCIA DE INGRESO').classes('text-lg font-bold text-[#ccff00] mb-4')
                        with ui.row().classes('w-full gap-2 flex-wrap'):
                            for path in order.fotos_evidencia:
                                with ui.card().classes('w-24 h-24 p-0 relative border border-gray-600 group'):
                                    ui.image(path).classes('w-full h-full object-cover rounded')
                                    ui.link('', path, new_tab=True).classes('absolute inset-0')

                # Cotización
                items = order.items_cotizacion or []
                if items:
                    with ui.card().classes('w-full bg-[#1c2025] border border-[#333] p-6 mb-4'):
                        ui.label('COTIZACIÓN').classes('text-lg font-bold text-[#ccff00] mb-4')
                        
                        subtotal = 0
                        for item in items:
                            item_total = float(item.get('total', 0))
                            subtotal += item_total
                            with ui.row().classes('w-full justify-between items-center py-2 border-b border-[#333]'):
                                with ui.column().classes('gap-0'):
                                    ui.label(item.get('nombre', '')).classes('text-white text-sm font-medium')
                                    ui.label(f"Cant: {item.get('cantidad', 1)} × S/ {float(item.get('precio_unitario', 0)):.2f}").classes('text-gray-400 text-xs')
                                ui.label(f'S/ {item_total:.2f}').classes('text-green-400 font-bold')
                        
                        igv = subtotal * 0.18
                        total = subtotal + igv
                        
                        ui.separator().classes('my-3')
                        with ui.column().classes('w-full items-end gap-1'):
                            ui.label(f'Subtotal: S/ {subtotal:.2f}').classes('text-gray-400')
                            ui.label(f'IGV (18%): S/ {igv:.2f}').classes('text-gray-400')
                            ui.label(f'TOTAL: S/ {total:.2f}').classes('text-2xl font-bold text-[#ccff00]')
            
        dialog.open()
    finally:
        db.close()


def open_edit_reception_dialog(consecutivo, container, state):
    """Edita datos iniciales de recepción"""
    db = get_db()
    try:
        order = db.query(Orden).filter_by(consecutivo=consecutivo).first()
        if not order: 
            return
        
        # Datos actuales para prellenar
        curr_motivo = order.motivo
        curr_km = order.km
        curr_tecnico = order.tecnico
        curr_diag_req = order.diagnostico_requerido
        curr_tipo = order.tipo
        curr_obs = order.observaciones # A veces guardamos combustible aqui
        
        # Intentar extraer combustible de obs si está formateado "Combustible: X"
        combustible_val = 'Reserva'
        if 'Combustible: ' in (curr_obs or ''):
            parts = curr_obs.split('Combustible: ')
            if len(parts) > 1:
                combustible_val = parts[1].split('\n')[0].strip()

    finally:
        db.close()

    tecnicos = _get_tecnicos()

    with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl bg-[#1c2025] p-0 border border-[#333]'):
        with ui.row().classes('w-full items-center justify-between p-4 border-b border-[#333]'):
            ui.label(f'Editar Recepción - {consecutivo}').classes('text-xl font-bold text-white')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey')
        
        with ui.row().classes('w-full p-6 gap-6'):
             with ui.column().classes('flex-1 gap-4'):
                 tipo_input = ui.toggle(['Express', 'Estándar'], value=curr_tipo).props('color=lime-13 toggle-color=black text-color=white')
                 
                 tecnico_input = ui.select(tecnicos, value=curr_tecnico, label='Técnico').props('outlined dense bg-[#1c2025]').classes('w-full')
                 
                 with ui.row().classes('w-full gap-4'):
                     km_input = ui.input('Kilometraje', value=curr_km).props('outlined dense').classes('flex-1')
                     comb_input = ui.select(['Reserva', '1/4', '1/2', '3/4', 'Full'], value=combustible_val, label='Nivel Combustible').props('outlined dense').classes('flex-1')

             with ui.column().classes('flex-1 gap-4'):
                 with ui.row().classes('w-full justify-between items-center'):
                     ui.label('¿Requiere diagnóstico?').classes('text-white')
                     diag_check = ui.switch(value=curr_diag_req).props('color=lime-13')
                 
                 motivo_input = ui.textarea('Motivo de ingreso', value=curr_motivo).props('outlined dense rows=5 bg-[#1c2025]').classes('w-full')

        with ui.row().classes('w-full justify-end gap-3 p-4 border-t border-[#333]'):
            ui.button('Cancelar', on_click=dialog.close).props('flat color=grey')
            
            def save_changes():
                ddb = get_db()
                try:
                    o = ddb.query(Orden).filter_by(consecutivo=consecutivo).first()
                    if o:
                        o.tipo = tipo_input.value
                        o.tecnico = tecnico_input.value
                        o.km = km_input.value
                        o.motivo = motivo_input.value
                        o.diagnostico_requerido = diag_check.value
                        # Update observaciones preserving other content? Simplification: overwrite check
                        o.observaciones = f"Combustible: {comb_input.value}"
                        ddb.commit()
                        theme.notify_success('Recepción actualizada')
                        dialog.close()
                        refresh_orders(container, state)
                except Exception as e:
                    ddb.rollback()
                    theme.notify_error(f'Error: {e}')
                finally:
                    ddb.close()

            ui.button('Guardar Cambios', icon='save', on_click=save_changes).props('unelevated color=lime-13 text-color=black')
        
    dialog.open()
