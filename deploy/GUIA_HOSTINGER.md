# 🚀 Guía de Despliegue — SANDOVAL Dashboard en Hostinger VPS

## ⚠️ Requisito: Plan VPS (no hosting compartido)

Tu aplicación es **Python + NiceGUI + SQLite** con servidor backend.
Necesitas un **VPS de Hostinger** (Ubuntu 22.04 LTS, mínimo 1GB RAM).  
Plan recomendado: **KVM 1** (~$5-7 USD/mes)

---

## 📋 FASE 1: Preparar el código (en tu PC)

### 1.1 Instalar Git en Windows
Descarga e instala: https://git-scm.com/download/win

### 1.2 Crear repositorio en GitHub
1. Ve a https://github.com y crea una cuenta (o inicia sesión)
2. Crea un nuevo repositorio llamado `sandoval-dashboard` (privado)
3. Copia la URL del repositorio (ej: `https://github.com/tuusuario/sandoval-dashboard.git`)

### 1.3 Subir tu proyecto a GitHub
Abre PowerShell en la carpeta `proyecto final` y ejecuta:

```powershell
git init
git add .
git commit -m "Primer despliegue - SANDOVAL Dashboard v2.0"
git branch -M main
git remote add origin https://github.com/TUUSUARIO/sandoval-dashboard.git
git push -u origin main
```

---

## 📋 FASE 2: Configurar el VPS en Hostinger

### 2.1 Conectar al VPS por SSH

**En Windows**, abre PowerShell y escribe:
```powershell
ssh root@TU_IP_DEL_VPS
# Ejemplo: ssh root@89.116.74.123
```
La IP y contraseña las encuentras en el panel de Hostinger → VPS → Detalles.

### 2.2 Clonar y configurar automáticamente
Una vez conectado al VPS, ejecuta estos comandos uno por uno:

```bash
# 1. Clonar el proyecto
cd /var/www
git clone https://github.com/TUUSUARIO/sandoval-dashboard.git sandoval
cd sandoval

# 2. Ejecutar el script de instalación automática
bash deploy/setup_vps.sh
```

¡El script hace todo solo! Dura unos 3-5 minutos.

---

## 📋 FASE 3: Verificar que funciona

```bash
# Ver estado del servicio
systemctl status sandoval

# Ver logs en tiempo real
journalctl -u sandoval -f

# Probar que responde (desde el VPS)
curl http://localhost:3000
```

Luego abre en tu navegador: **http://TU_IP_DEL_VPS**

---

## 🔄 FASE 4: Flujo de trabajo para cambios futuros

### Cuando hagas cambios en tu PC:

```powershell
# 1. En tu PC (PowerShell en la carpeta del proyecto):
git add .
git commit -m "Descripción del cambio que hiciste"
git push origin main
```

```bash
# 2. En el VPS (vía SSH):
ssh root@TU_IP
bash /var/www/sandoval/deploy/actualizar.sh
```

### Atajo con una sola línea desde tu PC:
```powershell
# Sube cambios Y reinicia el servidor automáticamente:
git add . ; git commit -m "Update" ; git push ; ssh root@TU_IP "bash /var/www/sandoval/deploy/actualizar.sh"
```

---

## 🐛 Cómo revisar errores en producción

```bash
# Ver últimos 50 logs del sistema
journalctl -u sandoval -n 50

# Ver logs en tiempo real (Ctrl+C para salir)
journalctl -u sandoval -f

# Ver archivo de boot del propio sistema
cat /var/www/sandoval/sandoval_boot.txt

# Reiniciar si algo falla
systemctl restart sandoval
```

---

## 🔒 Configurar dominio propio + HTTPS (opcional pero recomendado)

Si compraste un dominio (ej: `sandovaldashboard.com`):

```bash
# 1. Instalar Certbot
apt install certbot python3-certbot-nginx -y

# 2. Obtener certificado SSL gratuito
certbot --nginx -d sandovaldashboard.com -d www.sandovaldashboard.com

# 3. Listo, ya tiene HTTPS automáticamente
```

También en el archivo `deploy/nginx.conf`, cambia `tu-dominio.com` por tu dominio real.

---

## ✅ Comandos rápidos del día a día

| Acción | Comando en el VPS |
|--------|-------------------|
| Ver estado | `systemctl status sandoval` |
| Reiniciar | `systemctl restart sandoval` |
| Ver logs | `journalctl -u sandoval -f` |
| Actualizar código | `bash /var/www/sandoval/deploy/actualizar.sh` |
| Parar la app | `systemctl stop sandoval` |

---

## 📁 Archivos de despliegue creados

| Archivo | Descripción |
|---------|-------------|
| `deploy/setup_vps.sh` | Instalación completa automática (se ejecuta 1 sola vez) |
| `deploy/actualizar.sh` | Actualizar la app cuando hagas cambios |
| `deploy/sandoval.service` | Servicio systemd (mantiene la app corriendo 24/7) |
| `deploy/nginx.conf` | Configuración de Nginx (proxy reverso) |
