"""
Página Pública de Encuesta de Satisfacción
Acceso: /encuesta/{token}
"""

import json
from datetime import datetime
from nicegui import ui
from utils.models import get_db, Orden, Cliente, Vehiculo

def encuesta_page(token: str):
    db = get_db()
    try:
        order = db.query(Orden).filter_by(report_token=token).first()
        if not order:
            _not_found()
            return

        client = db.query(Cliente).filter_by(id=order.cliente_id).first() if order.cliente_id else None
        vehicle = db.query(Vehiculo).filter_by(placa=order.vehiculo_placa).first() if order.vehiculo_placa else None
        
        # Si ya respondió, mostrar agradecimiento
        existing_encuesta = order.encuesta
        if isinstance(existing_encuesta, str):
            try: existing_encuesta = json.loads(existing_encuesta)
            except: existing_encuesta = {}
        
        if existing_encuesta and existing_encuesta.get('completada'):
            _already_submitted()
            return

    finally:
        db.close()

    logo_url = '/assets/logo_sandoval.jpg'
    client_name = client.nombre if client else "estimado cliente"

    ui.add_head_html('''
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 0; }
        .hero { background: linear-gradient(135deg, #1e40af, #3b82f6); padding: 40px 20px; color: white; text-align: center; border-radius: 0 0 30px 30px; }
        .card { background: white; max-width: 500px; margin: -40px auto 40px; border-radius: 20px; padding: 30px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }
        .q-title { font-size: 14px; font-weight: 700; color: #475569; margin-bottom: 12px; display: block; }
        .rating-btn { padding: 10px; border-radius: 12px; border: 2px solid #e2e8f0; cursor: pointer; transition: all 0.2s; text-align: center; flex: 1; }
        .rating-btn:hover { border-color: #3b82f6; background: #eff6ff; }
        .rating-btn.active { background: #3b82f6; border-color: #1d4ed8; color: white; box-shadow: 0 4px 12px rgba(59,130,246,0.3); }
        .submit-btn { background: #10b981; color: white; font-weight: 800; padding: 16px; border-radius: 14px; width: 100%; border: none; cursor: pointer; margin-top: 20px; transition: transform 0.2s; }
        .submit-btn:active { transform: scale(0.98); }
    </style>
    ''')

    answers = {
        'calidad_trabajo': None,
        'tiempo_entrega': None,
        'atencion_cliente': None,
        'precio_justo': None,
        'limpieza_vehiculo': None,
        'recomendacion': None
    }

    def _set_rating(key, val, btns):
        answers[key] = val
        for v, b in btns.items():
            if v == val: b.classes('active', remove='bg-white')
            else: b.classes(remove='active')

    with ui.column().classes('w-full items-stretch gap-0'):
        # ── HERO ──
        with ui.element('div').classes('hero'):
            ui.image(logo_url).style('width:80px; margin-bottom:15px; border-radius:10px;')
            ui.label('¡Tu opinión nos importa!').style('font-size:24px; font-weight:800; display:block;')
            ui.label(f'Hola {client_name}, ayúdanos a mejorar nuestra calidad de servicio.').style('opacity:0.8; font-size:14px;')

        # ── FORM ──
        with ui.element('div').classes('card'):
            ui.label('Califica nuestra atención').classes('text-xl font-bold mb-6 block text-center')

            def _rating_row(label, key):
                ui.label(label).classes('q-title mt-4')
                btns = {}
                with ui.row().classes('w-full gap-2'):
                    for i in range(1, 6):
                        icon = 'sentiment_very_dissatisfied' if i==1 else 'sentiment_dissatisfied' if i==2 else 'sentiment_neutral' if i==3 else 'sentiment_satisfied' if i==4 else 'sentiment_very_satisfied'
                        color = '#ef4444' if i==1 else '#f97316' if i==2 else '#eab308' if i==3 else '#84cc16' if i==4 else '#10b981'
                        
                        btn = ui.element('div').classes('rating-btn')
                        with btn:
                            ui.icon(icon, size='24px').style(f'color:{color}' if i > 0 else '')
                            ui.label(str(i)).classes('text-[10px] font-bold block mt-1')
                        
                        btns[i] = btn
                        btn.on('click', lambda _, k=key, v=i, b=btns: _set_rating(k, v, b))

            _rating_row('¿Qué tan satisfecho estás con el trabajo técnico?', 'calidad_trabajo')
            _rating_row('¿Qué te pareció el tiempo de entrega?', 'tiempo_entrega')
            _rating_row('¿Cómo calificarías la atención del personal?', 'atencion_cliente')
            _rating_row('¿Consideras que el precio fue justo?', 'precio_justo')
            _rating_row('¿Cómo encontraste la limpieza de tu vehículo?', 'limpieza_vehiculo')

            ui.label('¿Nos recomendarías con amigos o familiares?').classes('q-title mt-6 text-center')
            recom_val = ui.slider(min=0, max=10, value=10).props('label-always color=green text-color=white')
            
            ui.label('¿Tienes algún comentario o sugerencia?').classes('q-title mt-6')
            comentarios = ui.textarea(placeholder='Escribe aquí...').props('outlined rounded bg-color=slate-50').classes('w-full')

            async def _submit():
                if any(v is None for v in answers.values() if v != answers['recomendacion']):
                    ui.notify('Por favor, califica todos los puntos.', type='warning')
                    return
                
                answers['recomendacion'] = recom_val.value
                answers['comentarios'] = comentarios.value
                answers['completada'] = True
                answers['fecha_encuesta'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                
                db_s = get_db()
                try:
                    o = db_s.query(Orden).filter_by(report_token=token).first()
                    o.encuesta = answers
                    db_s.commit()
                    ui.run_javascript('location.reload()')
                except Exception as ex:
                    ui.notify(f'Error al guardar: {ex}', type='negative')
                finally:
                    db_s.close()

            ui.button('ENVIAR MI CALIFICACIÓN', on_click=_submit).classes('submit-btn mt-8')

        with ui.column().classes('w-full items-center py-10'):
            ui.label('MECÁNICA Y REPUESTOS SANDOVAL').classes('text-[10px] font-bold text-gray-400 tracking-widest')
            ui.label('Pasión por el detalle técnico ✨').classes('text-[10px] italic text-gray-300')

def _not_found():
    with ui.column().classes('w-full h-screen items-center justify-center p-8'):
        ui.icon('error_outline', size='64px', color='grey-4')
        ui.label('Encuesta no válida').classes('text-xl font-bold text-gray-500 mt-4')
        ui.label('El link ha expirado o no existe.').classes('text-gray-400')

def _already_submitted():
    with ui.column().classes('w-full h-screen items-center justify-center p-8 text-center'):
        ui.icon('check_circle', size='80px', color='green-5')
        ui.label('¡Muchas gracias por tu tiempo!').classes('text-2xl font-black text-gray-800 mt-6')
        ui.label('Tu opinión ha sido registrada exitosamente. Nos ayuda a seguir brindándote el mejor servicio técnico de la región.').classes('text-gray-500 max-w-sm mt-2')
        ui.button('CERRAR', on_click=lambda: ui.run_javascript('window.close()')).props('outline color=green').classes('mt-8 px-10')
