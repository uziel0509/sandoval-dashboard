"""schemas.py — Pydantic V2 schemas para endpoints criticos.
Cubre: login, registrar abono, crear orden, crear factura, cliente aprobar.
"""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator


# ─── Auth ──────────────────────────────────────────────────────────────
class LoginPayload(BaseModel):
    """Login admin / staff / cliente."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4, max_length=128)

    @field_validator('username')
    @classmethod
    def _normalize_username(cls, v: str) -> str:
        return v.strip().lower()


class CambioPasswordPayload(BaseModel):
    """Cambio de password (admin / cliente)."""
    actual: str = Field(..., min_length=4, max_length=128)
    nueva: str = Field(..., min_length=10, max_length=128)


# ─── Ordenes ───────────────────────────────────────────────────────────
class AbonoPayload(BaseModel):
    """Registrar abono parcial sobre orden."""
    monto: float = Field(..., gt=0, le=99_999_999.99)
    metodo_pago: str = Field(..., min_length=2, max_length=30)
    observaciones: Optional[str] = Field(None, max_length=500)

    @field_validator('metodo_pago')
    @classmethod
    def _check_metodo(cls, v: str) -> str:
        allowed = {'efectivo', 'yape', 'plin', 'transferencia', 'tarjeta', 'credito'}
        v_norm = v.strip().lower()
        if v_norm not in allowed:
            raise ValueError(f'metodo_pago debe ser uno de: {sorted(allowed)}')
        return v_norm


class OrdenItemPayload(BaseModel):
    """Item dentro de cotizacion de orden."""
    descripcion: str = Field(..., min_length=2, max_length=200)
    cantidad: float = Field(..., gt=0, le=10_000)
    precio_unitario: float = Field(..., ge=0, le=99_999.99)


class OrdenCreatePayload(BaseModel):
    """Crear nueva orden de servicio."""
    cliente_id: str = Field(..., min_length=1, max_length=20)
    vehiculo_placa: str = Field(..., min_length=3, max_length=20)
    motivo: str = Field(..., min_length=3, max_length=500)
    diagnostico: Optional[str] = Field(None, max_length=2000)
    items: List[OrdenItemPayload] = Field(default_factory=list, max_length=200)
    km: Optional[str] = Field(None, max_length=20)


# ─── Facturas ──────────────────────────────────────────────────────────
class FacturaPayload(BaseModel):
    """Crear factura de proveedor."""
    proveedor: str = Field(..., min_length=2, max_length=200)
    numero_factura: str = Field(..., max_length=30)
    fecha: str = Field(..., max_length=20)  # ISO date or DD/MM/YYYY
    subtotal: float = Field(..., ge=0, le=999_999.99)
    igv: float = Field(..., ge=0, le=999_999.99)
    total: float = Field(..., ge=0, le=999_999.99)
    ruc_proveedor: str = Field(default='', pattern=r'^\d{11}$|^$')
    tipo: str = Field(default='mercaderia', max_length=20)
    notas: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode='after')
    def _coherencia_total(self):
        if abs(self.total - (self.subtotal + self.igv)) > 0.51:
            raise ValueError(
                f'total ({self.total}) no cuadra con subtotal+igv '
                f'({self.subtotal + self.igv})'
            )
        return self


# ─── Cliente Portal ────────────────────────────────────────────────────
class ClienteAprobarPayload(BaseModel):
    """Cliente aprueba/rechaza cotizacion via URL token publica."""
    decision: str = Field(..., pattern=r'^(aprobada|rechazada)$')
    firma_b64: Optional[str] = Field(None, max_length=2_000_000)  # max ~2MB base64
    comentarios: Optional[str] = Field(None, max_length=500)


# ═══════════════════════════════════════════════════════════════════════════
# 2026-05-05 EXPANSIÓN FastAPI score (4.2 → 8.5+):
# Schemas adicionales para endpoints de alto tráfico.
# ═══════════════════════════════════════════════════════════════════════════

# ─── Cliente / Vehículo CRUD ──────────────────────────────────────────────
class ClientePayload(BaseModel):
    """Crear/actualizar cliente."""
    documento: str = Field(..., min_length=8, max_length=15)  # DNI 8 / RUC 11
    nombre: str = Field(..., min_length=2, max_length=200)
    telefono: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=120)
    direccion: Optional[str] = Field(None, max_length=300)
    pin_acceso: Optional[str] = Field(None, min_length=4, max_length=20)
    tipo: Optional[str] = Field('individual', pattern=r'^(individual|empresa|jefe)$')

    @field_validator('documento')
    @classmethod
    def _normalize_doc(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError('documento debe ser numérico')
        if len(v) not in (8, 11):
            raise ValueError('documento debe ser DNI(8) o RUC(11)')
        return v


class VehiculoPayload(BaseModel):
    """Crear/actualizar vehículo."""
    placa: str = Field(..., min_length=4, max_length=20)
    cliente_id: str = Field(..., min_length=1, max_length=20)
    marca: Optional[str] = Field(None, max_length=50)
    modelo: Optional[str] = Field(None, max_length=50)
    anio: Optional[int] = Field(None, ge=1950, le=2100)
    color: Optional[str] = Field(None, max_length=30)
    km_actual: Optional[int] = Field(None, ge=0, le=2_000_000)
    conductor_nombre: Optional[str] = Field(None, max_length=200)
    conductor_telefono: Optional[str] = Field(None, max_length=20)
    conductor_pin: Optional[str] = Field(None, min_length=4, max_length=20)

    @field_validator('placa')
    @classmethod
    def _norm_placa(cls, v: str) -> str:
        return v.strip().upper().replace(' ', '')


# ─── Citas ────────────────────────────────────────────────────────────────
class CitaPayload(BaseModel):
    """Crear cita."""
    cliente_id: Optional[str] = Field(None, max_length=20)
    cliente_nombre: Optional[str] = Field(None, max_length=200)
    placa: str = Field(..., min_length=3, max_length=20)
    fecha: str = Field(..., min_length=8, max_length=20)  # YYYY-MM-DD
    hora: str = Field(..., pattern=r'^\d{2}:\d{2}$')
    motivo: str = Field(..., min_length=3, max_length=500)
    telefono: Optional[str] = Field(None, max_length=20)


# ─── Inventario ───────────────────────────────────────────────────────────
class InventarioPayload(BaseModel):
    """Crear/actualizar producto inventario."""
    codigo: str = Field(..., min_length=1, max_length=30)
    descripcion: str = Field(..., min_length=2, max_length=300)
    categoria: Optional[str] = Field(None, max_length=80)
    unidad: Optional[str] = Field('UND', max_length=10)
    stock: float = Field(..., ge=0, le=1_000_000)
    stock_min: Optional[float] = Field(0, ge=0, le=1_000_000)
    costo_unitario: float = Field(..., ge=0, le=999_999.99)
    precio_venta: Optional[float] = Field(None, ge=0, le=999_999.99)
    proveedor: Optional[str] = Field(None, max_length=200)


class StockAdjustPayload(BaseModel):
    """Ajustar stock manual."""
    delta: float = Field(..., gt=-1_000_000, lt=1_000_000)
    motivo: str = Field(..., min_length=3, max_length=300)


# ─── Notas de Venta ───────────────────────────────────────────────────────
class NotaItemPayload(BaseModel):
    descripcion: str = Field(..., min_length=2, max_length=200)
    cantidad: float = Field(..., gt=0, le=10_000)
    precio_unitario: float = Field(..., ge=0, le=99_999.99)


class NotaVentaPayload(BaseModel):
    """Crear nota de venta."""
    cliente_id: Optional[str] = Field(None, max_length=20)
    cliente_nombre: Optional[str] = Field(None, max_length=200)
    placa: Optional[str] = Field(None, max_length=20)
    items: List[NotaItemPayload] = Field(..., min_length=1, max_length=200)
    metodo_pago: Optional[str] = Field('efectivo', max_length=30)
    observaciones: Optional[str] = Field(None, max_length=500)


# ─── Gastos operativos ────────────────────────────────────────────────────
class GastoPayload(BaseModel):
    """Registrar gasto operativo."""
    fecha: str = Field(..., min_length=8, max_length=20)
    concepto: str = Field(..., min_length=3, max_length=300)
    monto: float = Field(..., gt=0, le=999_999.99)
    categoria: Optional[str] = Field('otros', max_length=80)
    metodo_pago: Optional[str] = Field('efectivo', max_length=30)
    proveedor: Optional[str] = Field(None, max_length=200)
    observaciones: Optional[str] = Field(None, max_length=500)


# ─── Push subscription ────────────────────────────────────────────────────
class PushKeysPayload(BaseModel):
    p256dh: str = Field(..., min_length=10, max_length=300)
    auth: str = Field(..., min_length=10, max_length=300)


class PushSubscriptionPayload(BaseModel):
    """Suscripción Web Push (VAPID)."""
    endpoint: str = Field(..., min_length=10, max_length=600)
    keys: PushKeysPayload


class PushSubscribeWrapper(BaseModel):
    """Wrapper que el frontend envía: { subscription: {...} }"""
    subscription: PushSubscriptionPayload


# ─── 2FA ──────────────────────────────────────────────────────────────────
class TotpVerifyPayload(BaseModel):
    """Activar 2FA tras escanear QR."""
    code: str = Field(..., pattern=r'^\d{6}$')


class TotpDisablePayload(BaseModel):
    """Desactivar 2FA (código TOTP o backup)."""
    code: str = Field(..., min_length=6, max_length=12)


class Login2FAPayload(BaseModel):
    """Paso 2 del login con 2FA."""
    temp_token: str = Field(..., min_length=20, max_length=600)
    code: str = Field(..., min_length=6, max_length=12)


# ─── Cambio de fase orden ────────────────────────────────────────────────
class FaseChangePayload(BaseModel):
    fase: str = Field(..., pattern=r'^(RECEPCIÓN|DIAGNÓSTICO|REPUESTOS|APROBACIÓN|REPARACIÓN|CONTROL CALIDAD|LISTO PARA ENTREGA|ARCHIVADO)$')


# ═══════════════════════════════════════════════════════════════════════════
# Response models (para response_model= en endpoints)
# ═══════════════════════════════════════════════════════════════════════════
class HealthResponse(BaseModel):
    status: str = Field(..., pattern=r'^(ok|degraded|error)$')
    version: Optional[str] = None
    database: Optional[str] = None


class TokenResponse(BaseModel):
    """Respuesta de login exitoso."""
    token: str
    user: dict  # estructura libre por compat con múltiples roles


class OkResponse(BaseModel):
    """Respuesta genérica OK."""
    ok: bool = True
    message: Optional[str] = None
