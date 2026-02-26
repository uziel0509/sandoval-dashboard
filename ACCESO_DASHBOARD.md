# 🚨 IMPORTANTE: Acceso al Dashboard SANDOVAL

## Situación Actual

Tu proyecto **SANDOVAL Dashboard** es una aplicación **NiceGUI (Python)** que corre en el **puerto 8088**, pero Emergent está configurado para:
- Frontend React en puerto **3000**
- Backend FastAPI en puerto **8001**

## ✅ Soluciones Implementadas

### 1. **Página de Información en el Frontend**
He creado una página HTML en `/app/frontend/public/index.html` que explica cómo acceder al dashboard.

### 2. **Proxy en el Backend**
He creado `/app/backend/server_proxy.py` que proporciona información sobre el dashboard.

### 3. **Dashboard Corriendo**
El servidor SANDOVAL está corriendo correctamente en:
- **Puerto interno:** 8088
- **Servicio:** `sandoval_dashboard` (RUNNING)

---

## 🌐 Cómo Acceder al Dashboard

### Opción A: Desde el Navegador de Emergent (Recomendado)
1. Abre la URL de tu preview de Emergent
2. Verás una página de información con un botón
3. Haz clic en "Abrir Dashboard SANDOVAL"
4. Se abrirá en una nueva pestaña en `localhost:8088`

### Opción B: Acceso Directo Local
Si estás en el mismo servidor/contenedor:
```bash
http://localhost:8088
```

### Opción C: Ver Info del Sistema
Accede al endpoint de salud:
```bash
curl http://localhost:8001/api/health
```

---

## ⚠️ Limitación de Emergent

Emergent está diseñado para aplicaciones **React + FastAPI** que corren en puertos específicos (3000 y 8001). Tu aplicación NiceGUI corre en el puerto 8088, que NO está expuesto externamente por defecto en la configuración de Emergent.

---

## 🔧 Opciones para Solucionar

### Opción 1: Cambiar el Puerto de NiceGUI a 8001
Modificar `/app/main.py` para que corra en puerto 8001 en lugar de 8088.

**Ventaja:** Emergent expondría el dashboard automáticamente  
**Desventaja:** Conflicto con el backend proxy actual

### Opción 2: Configurar Nginx para Proxy
Agregar una configuración de Nginx para redirigir desde el puerto público al 8088.

**Ventaja:** Solución más limpia  
**Desventaja:** Requiere acceso a configuración de Nginx

### Opción 3: Usar como Aplicación Local
Mantener el dashboard como una aplicación local que se ejecuta en el servidor.

**Ventaja:** No requiere cambios  
**Desventaja:** No accesible externamente sin configuración adicional

---

## 🚀 Recomendación RÁPIDA

Para que funcione inmediatamente en Emergent:

1. **Cambiar el puerto del dashboard a 8001:**

```python
# En /app/main.py, línea 180:
port=8001,  # Cambiar de 8088 a 8001
```

2. **Detener el backend proxy:**
```bash
supervisorctl stop backend
```

3. **Reiniciar el dashboard:**
```bash
supervisorctl restart sandoval_dashboard
```

---

## 📝 Estado Actual de Servicios

```
sandoval_dashboard (puerto 8088)  ✅ RUNNING
backend (puerto 8001)             ✅ RUNNING
frontend (puerto 3000)            ✅ RUNNING
```

---

## 🎯 Siguiente Paso

¿Quieres que cambie el puerto del dashboard a 8001 para que funcione inmediatamente en Emergent?

Responde con:
- **"SI"** para cambiar el puerto y hacerlo accesible
- **"NO"** si prefieres mantener la configuración actual

---

## 📞 Información de Contacto

**Dashboard:** SANDOVAL v2.0 PRO  
**Puerto actual:** 8088  
**Credenciales:**
- Admin: admin / admin123
- Técnico: tecnico1 / tec123
- Cliente: PLACA / DNI

---

**Nota:** Todos los cambios visuales 3D y animaciones ya están implementados y funcionando correctamente. Solo necesitamos resolver el tema del puerto para acceso externo.
