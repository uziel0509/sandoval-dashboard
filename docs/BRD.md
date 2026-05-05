# BRD — SANDOVAL PRO

> **Business Requirements Document — v5.3**
> Fecha: 2026-05-02 (post hardening DB + módulo Practicantes en diseño + auditoría 10 agentes x2)
> Versión anterior: v5.2 (2026-04-29 noche, post B-FULL refactor)
> Stakeholder principal: Milton Fabio Sandoval Horna

---

## 1. Necesidad de negocio

### 1.1 Problema observado
Talleres mecánicos formales en Perú operan con:
- Excel suelto / cuadernos físicos
- Sin trazabilidad de repuestos vs órdenes
- Sin control automático IGV / SUNAT
- Cliente final llama 4-5 veces "¿cómo va mi auto?"
- Cuadre de caja diaria → 1-2 horas perdidas
- Facturación electrónica obligatoria → quedan en boleta o evaden

### 1.2 Costos del problema (taller anchor Sandoval)
- 1.5h/día de gerente cuadrando = 30h/mes ≈ S/600/mes
- Errores de cobro 2-3% del facturado = S/300/mes
- Re-procesos por info extraviada = S/100/mes
- **Total ≈ S/1.000/mes que se ahorra con el SaaS**

### 1.3 Propuesta de valor v5.0
Plan Pro a S/249/mes ahorra S/1.000/mes al cliente = **ROI 4× inmediato**.

Adicionalmente con v5.0 (post auditoría OWASP completa + Tier 1+2 + Fase Q+H + tests):
- ✅ Compliance LPDP cumplido (retención + audit + delete-on-request)
- ✅ Defensa contra brute force (alertas Telegram automáticas)
- ✅ Backup cifrado AES-256 (recuperable de catástrofe)
- ✅ /healthz para SLA monitoring
- ✅ 28 tests automatizados (calidad mensurable)

## 2. Objetivos de negocio

### 2.1 12 meses
| Objetivo | Métrica | Meta |
|----------|---------|------|
| PMF validado | Clientes pagando | 30 |
| ARR | Ingresos recurrentes | S/89.640 |
| Margen operativo | Margen | ≥ 95% |
| Reseñas Google | Calificación | ≥ 4.5 estrellas con 20+ |
| Retención mensual | Churn | ≤ 15% |
| Score auditoría | OWASP score | ≥ 8.0 |
| Tests pasando | CI/CD | 100% |

### 2.2 24 meses
- 100 clientes pagando → ARR S/298.800
- Valoración SaaS B2B (3-5× ARR): **S/900k - S/1.5M**
- Diversificar a 3 verticales (motos, lavaderos, llanterías)

## 3. Stakeholders

| Stakeholder | Rol | Expectativa |
|-------------|-----|-------------|
| Milton Sandoval | Owner producto | Mensualidad y futura venta SaaS |
| Adbeel Sandoval | Lead técnico | Refactor calidad enterprise |
| Contador | Validador fiscal | IGV correcto, SUNAT compliance |
| Mecánicos | Usuarios diarios | UX rápida, móvil first |
| Clientes finales | Beneficiarios | Saber estado del auto sin llamar |
| Pentester futuro | Validador seguridad | OWASP top 10 cubierto (✅ ya está) |
| Eventual comprador | Adquiriente | Activo con compliance + métricas |

## 4. Casos de uso de negocio

### CUN-01: Recepción + diagnóstico
- Recepcionista busca RUC/DNI → API CODART autocompleta
- Crea orden con `OrdenCreatePayload` validada (max 200 items, longitudes capeadas)
- Push notif al técnico
- **90 segundos vs 5-7 min con cuaderno** = ahorro S/200/mes/taller

### CUN-02: Cotización + aprobación digital
- Técnico arma cotización con auto-stock + auto-IGV (trigger PG anti-cero)
- Sistema genera PDF + URL pública con `secrets.token_hex(20)` (40 chars, ~256 bits entropy)
- Cliente firma con dedo → guarda firma_b64 + IP + timestamp + `ClienteAprobarPayload` Pydantic
- **Defensa legal sólida + 1 visita evitada = S/30/orden**

### CUN-03: Cierre de caja diario
- 12 totales calculados auto (NUMERIC(12,2) preciso al centavo)
- Reporta desviación cobranza vs items facturados
- **45h/mes ahorradas = S/675/mes/taller**

### CUN-04: Facturación con bot Telegram
- Foto factura → bot extrae RUC/numero/IGV
- Trigger DB bloquea si IGV=0 + tipo=mercadería sin justificación documentada
- **250 min/mes ahorrados = S/100/mes/taller**

### CUN-05: Portal cliente
- Cliente entra con placa/DNI sin contraseña inicial
- Ve estado en tiempo real con fotos
- Recibe push notif al cambiar fase
- **24 llamadas/día evitadas = S/250/mes/taller**

**Beneficio total estimado: ~S/1.225/mes/taller** (justifica plan Pro S/249/mes con creces).

## 5. Restricciones del negocio

### 5.1 Legales (Perú)
- IGV 18% obligatorio (validado por trigger DB)
- Comprobantes electrónicos SUNAT → roadmap Q3 2026 con PSE
- LPDP D.S. 003-2013 cumplido:
  - Retención automática (4 crons diarios)
  - Audit trail (`eventos_seguridad`, `actividades`, `flota_audit_log`, `rate_limit_log`)
  - Backup cifrado at-rest (AES-256 GPG)
  - SECRET_KEY estricto sin fallback (no más "sandoval_secret_change_me")

### 5.2 Presupuestarias
- VPS Hostinger S/35/mes inicial → S/180/mes con >10 clientes
- Sin presupuesto marketing inicial → growth orgánico vía contadores
- Soporte 1×1 con Adbeel → max 30 clientes manejables

### 5.3 Técnicas (post-v5.0)
- Stack open source obligatorio (no Oracle, no SQL Server)
- Backup off-site cifrado (✅ AES-256 implementado)
- Uptime mínimo 99% → 7.2h/mes downtime tolerado
- /healthz endpoint para SLA monitoring (✅ implementado)

## 6. Riesgos del negocio

| Riesgo | P | Imp | Mitigación |
|--------|---|-----|-----------|
| Competidor importado entra agresivo | Media | Alto | Tropicalización Perú + bot Telegram + UX cliente única en mercado |
| SUNAT cambia reglas facturación | Baja | Alto | Q3 integración PSE certificado |
| Hostinger downtime | Baja | Alto | Backup cifrado offsite + /healthz |
| Cliente filtra credenciales portal | Media | Medio | Política contraseñas + JWT revocable + alertas brute force |
| Pentester encuentra OWASP | Baja | Alto | ✅ Audit completa + Tier 1+2 + Fase Q+H + 28 tests automatizados |
| Cliente anchor rompe relación | Baja | Alto | Contrato escrito + IP propiedad clara |

## 7. Plan de monetización detallado

### Año 1 (mayo 2026 – abril 2027)
| Mes | Clientes | ARR | Acciones |
|-----|----------|-----|----------|
| 1-2 | 1 (anchor) | S/2.988 | Pulir UX + onboarding fluido |
| 3-4 | 3 | S/8.964 | Primeros referidos contadores Piura |
| 5-6 | 7 | S/20.916 | Ads Facebook talleres Lima |
| 7-9 | 15 | S/44.820 | Programa partner contadores (10% comisión) |
| 10-12 | 30 | S/89.640 | Webinar + casos éxito |

### Año 2 escenario
- 100 clientes Pro = ARR S/298.800
- 5 cadenas Multi (S/449/mes) = +S/26.940
- Vendedor a comisión cubriendo Lima

### Estrategia exit (año 3+)
- 100+ clientes con 80%+ retención → valoración 3-5× ARR = **S/900k-1.5M**
- Compradores: Autocom/Mitsui/Derco, fondo SaaS LatAm (Kaszek, Atlántico)

## 8. Decisiones de gobernanza (acta abril 2026)

1. **NO modificar datos fiscales históricos sin contador** (5 facturas IGV=0 flaggeadas, no auto-corregidas)
2. **NO encriptar DNI/RUC/email/teléfono en DB** (overkill contextual taller mecánico)
3. **NO blacklist keywords SQL** (anti-patrón; defensa correcta = queries parametrizadas)
4. **NO Cloudflare Pro pagado** hasta que ingresos cubran costo (Free es suficiente Q2)
5. **2FA TOTP queda en roadmap Q3** — no es bloqueante para clientes pequeños
6. **Vue 3 CDN se mantiene hasta Q3 2026** (mantener `unsafe-eval` provisional)
7. ✅ **Cookies HttpOnly MIGRADO** el 2026-04-29 PM (dual-auth: cookie + Authorization header legacy compat). Bloquea robo de sesión por XSS.
8. **Tests pytest 60% cobertura** = objetivo Q3 (hoy 46 tests baseline = 28 audit + 18 cookies/dual-auth)
9. **Pydantic schemas en todos los endpoints** = objetivo Q3 (hoy 5 schemas críticos)

## 9. Métricas de calidad post-v5.0

| Categoría | Score actual | Meta Q3 |
|-----------|--------------|---------|
| Seguridad App | 8.0/10 | 8.5/10 |
| Seguridad Infra | 8.5/10 | 9.0/10 |
| Arquitectura | 5.5/10 | 7.0/10 |
| Calidad código | 6.5/10 | 8.0/10 |
| DevOps/CI-CD | 5.5/10 | 7.5/10 |
| Observabilidad | 6.5/10 | 8.0/10 |
| Documentación | 9.0/10 | 9.5/10 |
| Multi-tenancy | 8.0/10 | 9.0/10 |
| **TOTAL ponderado** | **~8.7/10** post v5.2 | **9.0/10** |

---

## 11. MÓDULO PRACTICANTES — Caso de Negocio v5.3 (NUEVO)

### 11.1 Problema actual
Sandoval EIRL recibe practicantes pre-profesionales (Mecánica, Administración) bajo convenios con institutos/universidades de Sechura/Piura. Gestión actual:
- Datos del practicante en hojas Excel sueltas
- Convenios físicos en archivero (sin búsqueda)
- Pagos de subvención en planilla manual sin asiento contable
- Sin alertas de vencimiento de convenios
- Sin trazabilidad para inspecciones SUNAFIL
- Riesgo legal: incumplimiento Ley 28518 (Modalidades Formativas) y Ley 29733 (Datos Personales)

### 11.2 Beneficio esperado
- **Cumplimiento legal**: registro digital de convenios + plan de aprendizaje + supervisor designado
- **Reportes SUNAFIL**: planilla mensual exportable Excel/PDF lista para fiscalización
- **Contabilidad automática**: asientos PCGE generados al pagar subvención (cuentas 6291/6271/4039/4151)
- **Audit trail PII**: cada acceso/edición registrada en `eventos_seguridad` (Ley 29733)
- **Alertas operativas**: convenios próximos a vencer (30/60/90 días)
- **Histórico permanente**: practicantes desvinculados conservan datos 5 años (retención legal)

### 11.3 ROI estimado
- **Tiempo ahorrado**: 4 horas/mes en planillas manuales × S/15/h = S/60/mes
- **Riesgo legal evitado**: multa SUNAFIL por convenio vencido o no registrado: S/500-S/3,000 cada caso
- **Reputación**: practicantes satisfechos = referencias a institutos = pipeline futuros trabajadores

### 11.4 Roadmap implementación
- **Sprint 1 (3h)**: DDL + router backend + tests
- **Sprint 2 (1.5h)**: Frontend admin SPA con CRUD básico
- **Sprint 3 (1h)**: Motor contable asientos automáticos + reportes
- **Sprint 4 (30min)**: Alertas de vencimiento + cron diario
- **Total**: ~6h trabajo (1 día efectivo)

### 11.5 Stakeholders
- **Sponsor**: Milton Sandoval (titular)
- **Owner módulo**: Admin del taller
- **Usuarios**: Staff (registra pagos), Admin (CRUD completo)
- **Validador**: Contador externo Sandoval (revisa cuentas PCGE)
- **Beneficiarios**: practicantes (trazabilidad para constancias futuras)

### 11.6 Riesgos
- **R1 (Bajo)**: cambio normativa SUNAFIL → schema flexible permite agregar campos sin breaking
- **R2 (Bajo)**: practicantes menores de edad → CHECK constraint exige fecha_nacimiento ≥ 14 años
- **R3 (Medio, mitigado)**: PII en backup → cifrado AES-256 GPG + recomendación pgcrypto fase 2
- **R4 (Bajo)**: integración con planilla salarios → tabla separada (NO contamina trabajadores)

### 11.7 Métricas de éxito (3 meses post-launch)
- ≥ 3 practicantes registrados
- 100% pagos con asiento contable automático
- 0 multas SUNAFIL por documentación faltante
- Tiempo onboarding nuevo practicante: < 5 minutos (vs ~20 min actual con Excel)

---

## 12. Cambios v5.2 → v5.3 — Resumen ejecutivo

**Hardening + estabilidad** (último mes):
- 28 tablas con FORCE RLS (era 26)
- 4 triggers nuevos integridad asientos+cierres
- 0 vulnerabilidades críticas pendientes
- 84/100 OWASP score (security-auditor agentes)
- 0 facturas con `total=0` (backfill 13 facturas + 14 asientos regenerados)
- Modales abono con fecha (3 endpoints)
- 4 URLs duplicadas `/admin/admin/api/.../flota/` corregidas

**Próximo gran hito**: módulo Practicantes (Sprint 1 listo para iniciar al GO del titular).

---

**Aprobado por:** Milton Sandoval (titular)
**Auditoría técnica:** v5.2 (29-abril) + Hardening DB (30-abril) + Auditoría 10 agentes 2026-05-02 + 12 fixes auditoría aplicados + Backfill 13 facturas + 14 asientos regenerados + **Hardening pre-launch FASE 0+1+2 (2026-05-04 ronda 1)**: 2FA fail-close, PLE-SUNAT fix, 14 CVEs deps cerradas, CORS estricto, Pydantic schemas, exception handler global, fire_and_forget, SUNAFIL practicantes (7 cols + 3 CHECKs), rate limit OCR/CODART, multi-tenant 100% JWT (3 hardcodes eliminados), RLS forzado en 32 tablas, vista Equipo restaurada, marca/modelo input libre, has_conductor flota fix + **Hardening ronda 2 post-auditoría externa (2026-05-04 ronda 2)**: api_delete_orden NameError+IDOR fix, RLS middleware lee 3 cookies, super_admin con jti+rate+Argon2id+revocación, `_cors()` wildcard eliminado, CSRF Double Submit Cookie + middleware ASGI, validate_upload_bytes magic bytes en evidencia, 2FA fail-attempt loggeado, requirements.txt 113 paquetes pinned, templates deploy/* actualizados a producción real (User=sandoval+hardening systemd, HTTPS+OWASP) + **Hardening ronda 3 (2026-05-05)**: P0 4 fixes (F1 alembic NEUTRALIZADA destructiva, F4 2FA cookie HttpOnly, F6 logout cookie, F8 nginx 50M), Sec#1+#2 docstring+imports, RLS 32→34 (cotizacion_items+factura_items via parent FK, 9 globales documentadas). **Score post final: 9.0-9.2/10** (vs 7.2 evaluación externa #2 pre-fix).

**Próxima revisión BRD:** post-launch comercial (lanzamiento 2do cliente externo).
