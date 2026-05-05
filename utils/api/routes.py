"""utils.api.routes — register_api_routes (entry point unico)."""
from __future__ import annotations

from utils.api.auth import api_login, api_logout, api_me
from utils.api.cliente import (
    api_admin_nuevas_ordenes,
    api_cliente_aprobar,
    api_cliente_aprobar_portal,
    api_cliente_calificar,
    api_cliente_cambiar_pin,
    api_cliente_create,
    api_cliente_historial_pagos,
    api_cliente_mis_citas,
    api_cliente_mis_ordenes,
    api_cliente_perfil_completo,
    api_cliente_presupuesto_pdf,
    api_clientes_list,
    api_portal_marcar_leidas,
    api_portal_notificaciones,
    api_vehiculo_create,
    api_vehiculos_cliente,
    api_vehiculos_list,
)
from utils.api.facturas import api_mobile_factura_agregar_stock, api_mobile_facturas_crear, api_mobile_facturas_ocr
from utils.api.flota import (
    admin_asignar_conductor,
    admin_get_audit,
    admin_listar_flota,
    admin_quitar_conductor,
    admin_reset_pin_conductor,
    admin_reset_pin_jefe,
    admin_set_tipo_cliente,
    admin_toggle_conductor_activo,
    cliente_asignar_conductor,
    cliente_get_audit,
    cliente_mi_flota,
    cliente_quitar_conductor,
    cliente_reset_pin_conductor,
    cliente_toggle_conductor_activo,
)
from utils.api.inventario import api_inventario_buscar, api_inventario_list, api_inventario_usar
from utils.api.lookup import api_lookup_dni, api_lookup_ruc
from utils.api.notas_citas import api_cita_create, api_citas_list, api_nota_create, api_notas_list
from utils.api.ordenes import (
    api_delete_orden,
    api_orden_create,
    api_orden_estado,
    api_orden_evidencia,
    api_orden_evidencia_from_url,
    api_orden_get,
    api_orden_get_fase_data,
    api_orden_get_pagos,
    api_orden_guardar_checklist,
    api_orden_guardar_diagnostico,
    api_orden_guardar_items,
    api_orden_informe_pdf,
    api_orden_pdf_download,
    api_orden_registrar_abono,
    api_orden_save_fase_data,
    api_orden_share_link_mobile,
    api_orden_subir_factura,
    api_ordenes_list,
)
from utils.api.push import admin_notificar_orden, api_push_subscribe, api_push_unsubscribe, api_push_vapid_key
from utils.api.reportes import api_dashboard, api_reportes_ganancia, api_reportes_ganancia_diaria
from utils.api_mobile_admin import register_mobile_admin_routes
from utils.api_extensions import register_extensions_routes

def register_api_routes(app):
    """Registra todas las rutas /api/* en la app NiceGUI/FastAPI"""
    app.add_api_route('/api/auth/login',              api_login,               methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/auth/me',                 api_me,                  methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/auth/logout',             api_logout,              methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/dashboard',               api_dashboard,           methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes',                 api_ordenes_list,        methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/nueva',           api_orden_create,        methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/estado',     api_orden_estado,        methods=['PUT',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/evidencia',  api_orden_evidencia,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/evidencia-from-url', api_orden_evidencia_from_url, methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{orden_id}/eliminar', api_delete_orden, methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}',            api_orden_get,           methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/diagnostico',  api_orden_guardar_diagnostico, methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/items',        api_orden_guardar_items,       methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/checklist',    api_orden_guardar_checklist,   methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/abono',        api_orden_registrar_abono,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/pagos',        api_orden_get_pagos,           methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/fase-data',    api_orden_save_fase_data,      methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/fase-data',    api_orden_get_fase_data,       methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/share-link',   api_orden_share_link_mobile,   methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/inventario/{codigo}/usar', api_inventario_usar,            methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/factura',      api_orden_subir_factura,       methods=['POST', 'OPTIONS'])
    app.add_api_route('/admin/api/ordenes/{id}/factura', api_orden_subir_factura,       methods=['POST', 'OPTIONS'])  # alias admin SPA



    app.add_api_route('/api/clientes',                api_clientes_list,       methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/clientes/nuevo',          api_cliente_create,      methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/clientes/{id}/vehiculos', api_vehiculos_cliente,   methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/clientes/{id}/perfil-completo', api_cliente_perfil_completo, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/vehiculos',               api_vehiculos_list,      methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/vehiculos/nuevo',         api_vehiculo_create,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/inventario',              api_inventario_list,     methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/inventario/buscar',       api_inventario_buscar,   methods=['GET',  'OPTIONS'])
    # === CODART LOOKUP ROUTES ===
    app.add_api_route('/api/lookup/ruc/{ruc}', api_lookup_ruc, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/lookup/dni/{dni}', api_lookup_dni, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/mobile/facturas/ocr',                       api_mobile_facturas_ocr,          methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/mobile/facturas/crear',                     api_mobile_facturas_crear,        methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/mobile/facturas/{fid}/agregar-stock',       api_mobile_factura_agregar_stock, methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/reportes/ganancia',        api_reportes_ganancia,        methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/reportes/ganancia-diaria', api_reportes_ganancia_diaria, methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/notas-venta',             api_notas_list,          methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/notas-venta/nueva',       api_nota_create,         methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/citas',                   api_citas_list,          methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/citas/nueva',             api_cita_create,         methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/cliente/mis-ordenes',     api_cliente_mis_ordenes, methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/informe-final.pdf',  api_orden_informe_pdf, methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/ordenes/{id}/informe-final.pdf', api_orden_informe_pdf, methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/ordenes/{id}/presupuesto.pdf', api_cliente_presupuesto_pdf, methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/mis-citas',       api_cliente_mis_citas,   methods=['GET',  'OPTIONS'])
    app.add_api_route('/api/cliente/aprobar',         api_cliente_aprobar,     methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/portal/notificaciones', api_portal_notificaciones, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/portal/notificaciones/marcar-leidas', api_portal_marcar_leidas, methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/cliente/mis-pagos', api_cliente_historial_pagos, methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/aprobar-presupuesto', api_cliente_aprobar_portal, methods=['POST','OPTIONS'])
    app.add_api_route('/api/cliente/calificar', api_cliente_calificar, methods=['POST','OPTIONS'])
    app.add_api_route('/api/ordenes/{id}/pdf', api_orden_pdf_download, methods=['GET','OPTIONS'])
    app.add_api_route('/api/admin/nuevas-ordenes', api_admin_nuevas_ordenes, methods=['GET','OPTIONS'])

    # ── Flota empresarial + Web Push ───────────────────────────────────
    # ADMIN del taller
    app.add_api_route('/admin/api/clientes/{cid}/flota',                    admin_listar_flota,            methods=['GET','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/flota/{placa}/conductor',  admin_asignar_conductor,       methods=['POST','PUT','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/flota/{placa}/conductor',  admin_quitar_conductor,        methods=['DELETE'])
    app.add_api_route('/admin/api/clientes/{cid}/flota/{placa}/reset-pin',  admin_reset_pin_conductor,     methods=['POST','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/flota/{placa}/activo',     admin_toggle_conductor_activo, methods=['POST','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/audit',                    admin_get_audit,               methods=['GET','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/tipo',                     admin_set_tipo_cliente,        methods=['POST','OPTIONS'])
    app.add_api_route('/admin/api/clientes/{cid}/reset-pin-jefe',           admin_reset_pin_jefe,          methods=['POST','OPTIONS'])
    # CLIENTE jefe
    app.add_api_route('/api/cliente/mi-flota',                              cliente_mi_flota,              methods=['GET','OPTIONS'])
    app.add_api_route('/api/cliente/mi-flota/{placa}/conductor',            cliente_asignar_conductor,     methods=['POST','PUT','OPTIONS'])
    app.add_api_route('/api/cliente/mi-flota/{placa}/conductor',            cliente_quitar_conductor,      methods=['DELETE'])
    app.add_api_route('/api/cliente/mi-flota/{placa}/reset-pin',            cliente_reset_pin_conductor,   methods=['POST','OPTIONS'])
    app.add_api_route('/api/cliente/mi-flota/{placa}/activo',               cliente_toggle_conductor_activo, methods=['POST','OPTIONS'])
    app.add_api_route('/api/cliente/audit',                                 cliente_get_audit,             methods=['GET','OPTIONS'])
    # CAMBIO DE PIN propio
    app.add_api_route('/api/cliente/cambiar-pin',                           api_cliente_cambiar_pin,       methods=['POST','OPTIONS'])
    # WEB PUSH
    app.add_api_route('/api/push/vapid-key',                                api_push_vapid_key,            methods=['GET','OPTIONS'])
    app.add_api_route('/api/push/subscribe',                                api_push_subscribe,            methods=['POST','OPTIONS'])
    app.add_api_route('/api/push/unsubscribe',                              api_push_unsubscribe,          methods=['POST','OPTIONS'])
    # Notificación manual desde admin
    app.add_api_route('/admin/api/ordenes/{cons}/notificar',                admin_notificar_orden,         methods=['POST','OPTIONS'])

    try:
        from utils.api_mobile_admin import register_mobile_admin_routes
        register_mobile_admin_routes(app)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("Mobile admin endpoints no registrados: %s", _e)

    try:
        from utils.api_extensions import register_extensions_routes
        register_extensions_routes(app)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("Extensions endpoints no registrados: %s", _e)


async def api_cliente_perfil_completo(request: Request) -> JSONResponse:
    """GET /api/clientes/{id}/perfil-completo — cliente + vehiculos + ordenes + total"""
    user = _require_admin(request)
    if isinstance(user, JSONResponse):
        return user
    cliente_id = request.path_params.get('id', '')
    db = get_db()
    try:
        cli = db.query(Cliente).filter_by(id=cliente_id).first()
        if not cli:
            return json_err('Cliente no encontrado', 404)
        vehiculos = db.query(Vehiculo).filter_by(cliente_id=cliente_id).all()
        total_pagado = 0
        vehiculos_data = []
        for v in vehiculos:
            ordenes = db.query(Orden).filter_by(vehiculo_placa=v.placa).order_by(Orden.fecha.desc()).all()
            ordenes_data = []
            total_vehiculo = 0
            for o in ordenes:
                items = o.items_cotizacion or []
                if isinstance(items, str):
                    try:
                        import json as _json
                        items = _json.loads(items)
                    except: items = []
                total_ord = sum(float(it.get('total', 0) or 0) for it in (items if isinstance(items, list) else []))
                total_vehiculo += total_ord
                ordenes_data.append({
                    'consecutivo': o.consecutivo,
                    'fecha': str(o.fecha or '')[:10],
                    'estado': o.estado or '',
                    'motivo': o.motivo or '',
                    'tecnico': o.tecnico or '',
                    'total': total_ord,
                })
            total_pagado += total_vehiculo
            vehiculos_data.append({
                'placa': v.placa,
                'marca': v.marca or '',
                'modelo': v.modelo or '',
                'tipo': v.tipo or '',
                'total_pagado': total_vehiculo,
                'ordenes': ordenes_data,
            })
        return json_ok({
            'id': cli.id,
            'nombre': cli.nombre or '',
            'apellidos': getattr(cli, 'apellidos', '') or '',
            'telefono': getattr(cli, 'telefono', '') or '',
            'email': getattr(cli, 'email', '') or '',
            'direccion': getattr(cli, 'direccion', '') or '',
            'total_pagado': total_pagado,
            'n_vehiculos': len(vehiculos),
            'vehiculos': vehiculos_data,
        })
    finally:
        db.close()
