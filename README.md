# 🔧 SANDOVAL Dashboard v2.0 Pro

**MECÁNICA Y REPUESTOS SANDOVAL EIRL**
Sistema de Gestión de Taller Mecánico Completo

---

## 🚀 Instalación

```bash
pip install -r requirements.txt
python main.py
```

O ejecuta **RUN_DASHBOARD.bat**

**Credenciales por defecto:**
- `Para crear el admin inicial: `BOOTSTRAP_ADMIN_PASSWORD=tu-password python -c "from utils.models import init_db; init_db()"`

---

## 📋 Módulos Completos

### 🔐 Autenticación y Roles
- Login con usuario/contraseña
- 3 roles: Admin, Técnico, Recepcionista
- Permisos por módulo según rol
- Registro de actividad (auditoría)

### 📊 Dashboard (Métricas)
- KPIs en tiempo real desde SQLite
- Gráficos Plotly: órdenes por estado, ingresos por orden
- Alertas de stock bajo
- Órdenes recientes

### 🔧 Órdenes de Servicio
- Flujo de 8 estados: RECEPCIÓN → DIAGNÓSTICO → REPUESTOS → APROBACIÓN → REPARACIÓN → CONTROL → ENTREGA → ARCHIVADO
- Vista de cards con filtro por estado
- Detalle completo: stepper visual, diagnóstico inline, cotización, historial
- Agregar ítems desde inventario o manualmente
- Generación de PDFs: Orden de Ingreso, Cotización, Factura/Boleta
- **Envío de link de aprobación al cliente: WhatsApp, Email, copiar link**
- Token de aprobación único por orden

### 👥 Clientes
- CRUD completo (crear, editar, eliminar)
- Búsqueda y filtros (Persona/Empresa)
- **Importación masiva desde Excel**
- Validación de duplicados

### 🚗 Vehículos
- CRUD vinculado a clientes
- **Historial de servicios por vehículo** (botón en tabla)
- Búsqueda por placa, marca, modelo

### 🏪 Proveedores
- CRUD completo con búsqueda

### 📦 Inventario
- CRUD con cálculo automático de precio (costo + rentabilidad %)
- Indicadores de stock (verde/naranja/rojo)
- Alerta de stock mínimo configurable

### 📅 Citas / Agenda
- Programar, confirmar, completar, cancelar citas
- Filtros por estado
- Vinculación con cliente y vehículo

### 📈 Reportes
- Distribución por estado (pie chart)
- Top ítems cotizados
- Valorización de inventario
- **Exportar a Excel:** Órdenes, Clientes, Inventario

### 👤 Usuarios
- Gestión de usuarios (solo admin)
- Crear/editar/desactivar usuarios
- Asignar roles
- **Registro de actividad** (quién hizo qué y cuándo)

### ⚙️ Configuración
- Datos de la empresa (razón social, RUC, dirección, teléfono, email)
- Lista de técnicos (desde usuarios con rol técnico)
- IGV configurable, moneda
- Info del sistema

### 🔔 Notificaciones
- Panel de notificaciones en header (campana con badge)
- Alertas de: stock bajo, órdenes pendientes, aprobaciones/rechazos de clientes
- Priorización por urgencia

### 🌐 Aprobación Pública
- Página web pública para que el cliente apruebe/rechace ordenes
- URL: `/aprobacion/{token}`
- Muestra: detalle orden, vehículo, cotización con total
- Botones Aprobar/Rechazar con comentario opcional
- Actualiza estado automáticamente en el sistema

---

## 🏗️ Arquitectura

```
SANDOVAL_Dashboard/
├── main.py                      # App principal NiceGUI + routes
├── theme.py                     # Tema visual + estados + notificaciones
├── requirements.txt
├── RUN_DASHBOARD.bat
│
├── components/                  # Módulos de UI
│   ├── sidebar.py               # Navegación con permisos
│   ├── metricas.py              # Dashboard con KPIs
│   ├── ordenes_servicio.py      # Órdenes (módulo principal)
│   ├── clientes.py              # Gestión clientes + importar Excel
│   ├── vehiculos.py             # Vehículos + historial servicios
│   ├── proveedores.py           # Proveedores
│   ├── inventario.py            # Inventario + stock
│   ├── citas.py                 # Agenda de citas
│   ├── reportes.py              # Reportes + exportar Excel
│   ├── usuarios.py              # Usuarios + actividad
│   └── configuracion.py         # Config del sistema
│
├── pages/
│   └── approval.py              # Página pública de aprobación
│
├── utils/
│   ├── models.py                # SQLAlchemy models + init DB + migración JSON
│   ├── auth.py                  # Login/logout + roles + permisos
│   ├── pdf_generator.py         # PDFs con ReportLab
│   ├── notifications.py         # Notificaciones + WhatsApp/Email msg
│   ├── excel_tools.py           # Importar/Exportar Excel
│   └── data_manager.py          # (legacy JSON, mantenido por compatibilidad)
│
├── data/
│   ├── sandoval.db              # Base de datos SQLite
│   └── *.json                   # Datos legacy (migrados a SQLite)
│
├── pdfs/                        # PDFs generados
├── exports/                     # Excel exportados
└── backups/                     # Backups automáticos
```

---

## 🔧 Stack Técnico
- **Backend:** Python 3.13 + NiceGUI 1.4
- **Base de datos:** SQLite via SQLAlchemy
- **Gráficos:** Plotly
- **PDFs:** ReportLab
- **Excel:** Pandas + OpenPyXL
- **Auth:** Sesiones con storage_secret
- **UI:** Quasar components (dark theme)

---

## 🎨 Diseño
- Tema oscuro profesional (#0e1117 / #1c2025)
- Accent verde lima (#ccff00)
- Animaciones CSS (fade-in, slide-in, hover, pulse)
- Cards interactivas con bordes hover
- Badges de estado con colores por fase
- Responsive para desktop y tablet

---

**v2.0 Pro - Febrero 2026**
**Desarrollado por Adbeel Sandoval**
