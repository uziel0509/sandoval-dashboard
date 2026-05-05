"""
SANDOVAL Dashboard — Login HTML puro (sin NiceGUI).

Endpoint: GET /login
- Detecta móvil → redirige a /app/ (PWA tiene su propio login).
- En PC: muestra form con tabs Staff/Cliente.
- POST a /api/auth/login (handler ya existente).
- Al éxito: guarda token en localStorage + cookie y redirige a /.
"""
from __future__ import annotations


def render_login_html() -> str:
    """Devuelve el HTML del login (autocontenido, no requiere assets externos
    salvo el logo y la fuente Inter)."""
    return """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#0f172a">
<title>Iniciar sesión — SANDOVAL EIRL</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  html,body{font-family:'Inter',system-ui,-apple-system,sans-serif;color:#0f172a;
            min-height:100vh;line-height:1.4;-webkit-font-smoothing:antialiased}
  body{background:linear-gradient(135deg,#0f172a 0%,#1e293b 30%,#274495 100%);
       background-size:400% 400%;animation:bg 15s ease infinite;
       overflow-x:hidden;display:flex;align-items:center;justify-content:center;
       padding:20px}
  @keyframes bg{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}

  /* Partículas decorativas */
  .particles{position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:0}
  .particle{position:absolute;width:3px;height:3px;background:rgba(255,255,255,.5);
            border-radius:50%;animation:floatp 20s linear infinite}
  @keyframes floatp{
    0%{transform:translateY(100vh) scale(0);opacity:0}
    10%,90%{opacity:1}
    100%{transform:translateY(-10vh) scale(1);opacity:0}
  }
  .particle:nth-child(1){left:10%;animation-delay:0s}
  .particle:nth-child(2){left:25%;animation-delay:2s}
  .particle:nth-child(3){left:40%;animation-delay:4s}
  .particle:nth-child(4){left:55%;animation-delay:1s}
  .particle:nth-child(5){left:70%;animation-delay:3s}
  .particle:nth-child(6){left:85%;animation-delay:5s}

  /* Card */
  .card{position:relative;z-index:10;background:rgba(255,255,255,.98);
        backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,.5);
        box-shadow:0 25px 60px -12px rgba(0,0,0,.4);border-radius:26px;
        padding:32px 28px;width:100%;max-width:400px;
        animation:enter .8s cubic-bezier(.4,0,.2,1) forwards}
  @keyframes enter{
    from{opacity:0;transform:translateY(40px) scale(.94)}
    to{opacity:1;transform:translateY(0) scale(1)}
  }

  /* Header */
  .brand{display:flex;flex-direction:column;align-items:center;margin-bottom:20px}
  .brand img{width:74px;height:74px;border-radius:18px;object-fit:contain;
             box-shadow:0 8px 22px rgba(39,68,149,.25);background:#fff;padding:6px;
             animation:floatLogo 6s ease-in-out infinite}
  @keyframes floatLogo{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
  .brand-tag{font-size:9px;color:#1e3a8a;font-weight:800;letter-spacing:.25em;
             text-transform:uppercase;margin-top:14px}
  .brand-name{font-size:22px;font-weight:900;color:#0f172a;letter-spacing:-.02em;
              margin-top:2px}
  .brand-sub{font-size:11px;color:#94a3b8;font-weight:600;letter-spacing:.04em;margin-top:3px}

  /* Tabs */
  .tabs{display:flex;background:#f8fafc;border-radius:14px;padding:4px;
        border:1px solid #e2e8f0;margin:18px 0 14px}
  .tab{flex:1;padding:10px 12px;border:none;background:transparent;cursor:pointer;
       font-family:inherit;font-size:11.5px;font-weight:800;letter-spacing:.04em;
       color:#64748b;border-radius:10px;transition:all .2s;
       display:flex;align-items:center;justify-content:center;gap:6px}
  .tab .ico{font-size:14px}
  .tab.active{background:#fff;color:#0f172a;box-shadow:0 2px 8px rgba(0,0,0,.08)}
  .tab:not(.active):hover{color:#1e293b}

  /* Formularios */
  .panel{display:none}
  .panel.active{display:block;animation:fade .25s ease}
  @keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}

  .panel-hint{font-size:10.5px;color:#94a3b8;text-align:center;font-weight:700;
              text-transform:uppercase;letter-spacing:.1em;margin-bottom:14px}

  .field{position:relative;margin-bottom:11px}
  .field label{display:block;font-size:11px;font-weight:700;color:#64748b;margin-bottom:4px;
               text-transform:uppercase;letter-spacing:.06em}
  .field input{width:100%;border:1.5px solid #e2e8f0;border-radius:12px;
               padding:12px 14px;font-family:inherit;font-size:14px;color:#0f172a;
               background:#fff;outline:none;transition:all .15s;
               -webkit-appearance:none;appearance:none}
  .field input:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.12)}
  .field input::placeholder{color:#cbd5e1}
  .field.with-toggle input{padding-right:42px}
  .toggle{position:absolute;right:6px;top:24px;border:none;background:transparent;
          cursor:pointer;padding:8px;color:#94a3b8;font-size:16px}
  .toggle:hover{color:#3b82f6}
  .placa input{text-transform:uppercase;letter-spacing:.05em;font-weight:700}

  /* Submit */
  .submit{width:100%;background:linear-gradient(135deg,#1e40af,#3b82f6);color:#fff;
          font-weight:900;letter-spacing:.06em;padding:14px;border-radius:14px;
          border:none;cursor:pointer;margin-top:14px;font-size:13px;
          font-family:inherit;transition:all .2s;
          box-shadow:0 8px 22px rgba(59,130,246,.4);
          display:flex;align-items:center;justify-content:center;gap:8px}
  .submit:hover{transform:translateY(-1px);box-shadow:0 12px 28px rgba(59,130,246,.5)}
  .submit:disabled{opacity:.65;cursor:not-allowed;transform:none;box-shadow:none}
  .submit .spinner{width:14px;height:14px;border-radius:50%;
                   border:2px solid rgba(255,255,255,.4);border-top-color:#fff;
                   animation:spin 0.7s linear infinite;display:none}
  .submit.loading .spinner{display:inline-block}
  .submit.loading .label{display:none}
  @keyframes spin{to{transform:rotate(360deg)}}

  /* Error */
  .err{display:none;background:#fef2f2;color:#991b1b;border:1px solid #fecaca;
       border-radius:10px;padding:9px 12px;font-size:12px;font-weight:600;
       text-align:center;margin-top:10px}
  .err.show{display:block}

  /* Hint cliente */
  .client-hint{background:linear-gradient(135deg,#eff6ff,#dbeafe);
               border:1px solid #bfdbfe;color:#1e40af;font-size:11px;
               padding:11px 13px;border-radius:11px;line-height:1.5;
               margin-top:6px;font-weight:500}

  /* Help */
  .help{margin-top:14px;padding:11px 14px;background:#f1f5f9;border-radius:11px;
        border:1px solid #e2e8f0;font-size:10.5px;color:#64748b;line-height:1.6}
  .help b{color:#0f172a;font-weight:800}
  .help-foot{margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0;text-align:center}

  /* Footer */
  .foot{text-align:center;margin-top:14px;padding-top:14px;border-top:1px solid #e2e8f0;
        font-size:9px;color:#94a3b8;font-weight:700;letter-spacing:.18em}
  .foot-sub{font-size:9px;color:#cbd5e1;font-weight:500;letter-spacing:.04em;margin-top:2px}

  @media (max-width:420px){
    .card{padding:24px 20px}
    .brand img{width:64px;height:64px}
  }
</style>
</head>
<body>

<div class="particles" aria-hidden="true">
  <div class="particle"></div><div class="particle"></div><div class="particle"></div>
  <div class="particle"></div><div class="particle"></div><div class="particle"></div>
</div>

<main class="card">
  <header class="brand">
    <img src="/assets/logo_sandoval.jpg" alt="SANDOVAL" onerror="this.style.display='none'">
    <div class="brand-tag">MECÁNICA Y REPUESTOS</div>
    <div class="brand-name">SANDOVAL EIRL</div>
    <div class="brand-sub">Sistema profesional de gestión</div>
  </header>

  <div class="tabs" role="tablist">
    <button class="tab active" data-tab="staff" role="tab" aria-selected="true">
      <span class="ico">👔</span> PERSONAL
    </button>
    <button class="tab" data-tab="cliente" role="tab" aria-selected="false">
      <span class="ico">🚗</span> SOY CLIENTE
    </button>
  </div>

  <!-- Panel STAFF -->
  <form id="form-staff" class="panel active" autocomplete="on">
    <div class="panel-hint">Acceso exclusivo para personal autorizado</div>
    <div class="field">
      <label for="staff-user">Usuario</label>
      <input id="staff-user" type="text" name="username" autocomplete="username"
             placeholder="Tu nombre de usuario" required>
    </div>
    <div class="field with-toggle">
      <label for="staff-pass">Contraseña</label>
      <input id="staff-pass" type="password" name="password" autocomplete="current-password"
             placeholder="Tu clave segura" required>
      <button type="button" class="toggle" data-toggle="staff-pass" aria-label="Mostrar contraseña">👁</button>
    </div>
    <button type="submit" class="submit">
      <span class="spinner"></span>
      <span class="label">🔐 ENTRAR AL SISTEMA</span>
    </button>
    <div class="err" id="err-staff"></div>
  </form>

  <!-- Panel CLIENTE -->
  <form id="form-cliente" class="panel" autocomplete="on">
    <div class="panel-hint">Consulta el estado de tu vehículo en tiempo real</div>
    <div class="field placa">
      <label for="cli-placa">Placa del vehículo</label>
      <input id="cli-placa" type="text" name="placa" autocomplete="off"
             placeholder="Ej: ABC-123" maxlength="10" required>
    </div>
    <div class="field with-toggle">
      <label for="cli-pass">DNI / RUC</label>
      <input id="cli-pass" type="password" name="password" autocomplete="current-password"
             inputmode="numeric" placeholder="Tu documento" required>
      <button type="button" class="toggle" data-toggle="cli-pass" aria-label="Mostrar contraseña">👁</button>
    </div>
    <div class="client-hint">
      💡 Tu contraseña inicial es tu número de <b>DNI</b> o <b>RUC</b>.
    </div>
    <button type="submit" class="submit">
      <span class="spinner"></span>
      <span class="label">🚗 INGRESAR AL PORTAL</span>
    </button>
    <div class="err" id="err-cliente"></div>
  </form>

  <details class="help">
    <summary style="cursor:pointer;font-weight:700;color:#475569;letter-spacing:.04em">
      ❓ Ayuda para iniciar sesión
    </summary>
    <p style="margin-top:8px"><b>👔 Personal:</b> usuario y contraseña asignados.</p>
    <p style="margin-top:4px"><b>🚗 Clientes:</b> placa de tu vehículo + DNI/RUC.</p>
    <div class="help-foot">📞 +51 999 999 999</div>
  </details>

  <div class="foot">
    SANDOVAL v2.0 PRO
    <div class="foot-sub">© 2026 MECÁNICA Y REPUESTOS SANDOVAL EIRL</div>
  </div>
</main>

<script>
(function(){
  // Tabs
  const panels = {
    staff: document.getElementById('form-staff'),
    cliente: document.getElementById('form-cliente'),
  };
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      document.querySelectorAll('.tab').forEach(t => {
        const active = t === tab;
        t.classList.toggle('active', active);
        t.setAttribute('aria-selected', String(active));
      });
      Object.entries(panels).forEach(([k, el]) => el.classList.toggle('active', k === target));
      Object.values(errEls).forEach(el => el.classList.remove('show'));
    });
  });

  // Toggle password visibility
  document.querySelectorAll('.toggle[data-toggle]').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.toggle);
      if (!input) return;
      input.type = input.type === 'password' ? 'text' : 'password';
    });
  });

  // Auto-uppercase placa
  const placaInp = document.getElementById('cli-placa');
  placaInp.addEventListener('input', () => {
    placaInp.value = placaInp.value.toUpperCase().replace(/[^A-Z0-9-]/g, '');
  });

  const errEls = {
    staff: document.getElementById('err-staff'),
    cliente: document.getElementById('err-cliente'),
  };

  function showErr(which, msg){
    const el = errEls[which];
    el.textContent = msg;
    el.classList.add('show');
  }
  function clearErr(which){ errEls[which].classList.remove('show'); }

  async function postLogin(payload){
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
      credentials: 'include',
    });
    let data = {};
    try { data = await res.json(); } catch (_) {}
    return { res, data };
  }

  function persistAndRedirect(token, user){
    // 2026-05-04 SECURITY-REVIEWER #1 FIX: ya NO seteamos `sandoval_api_token`
    // como document.cookie JS-readable. El backend ya emite la cookie HttpOnly
    // real (`sandoval_token` o `sandoval_client_token`) via set_token_cookie()
    // en /api/login response. Esa cookie HttpOnly NO es robable por XSS.
    //
    // Mantenemos localStorage por compat con admin SPA y PWAs (Bearer token
    // legacy). El roadmap es eliminar localStorage cuando los 3 portales
    // migren 100% a cookies (Issue #3 del repo).
    try {
      localStorage.setItem('sandoval_token', token);
      localStorage.setItem('sandoval_user', JSON.stringify(user || {}));
    } catch (_) {}

    // Redirect: cliente → /app/, staff → / (admin SPA)
    const isClient = (user && (user.rol === 'cliente' || user.tipo === 'cliente'));
    if (isClient) {
      window.location.href = '/app/';
    } else {
      window.location.href = '/';
    }
  }

  // Submit STAFF
  panels.staff.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearErr('staff');
    const u = document.getElementById('staff-user').value.trim();
    const p = document.getElementById('staff-pass').value;
    if (!u || !p){ showErr('staff', '⚠️ Ingresa usuario y contraseña.'); return; }
    const btn = panels.staff.querySelector('.submit');
    btn.classList.add('loading'); btn.disabled = true;
    try {
      const { res, data } = await postLogin({ tipo:'staff', username:u, password:p });
      if (res.status === 429) { showErr('staff', '⛔ Demasiados intentos. Espera 15 minutos.'); return; }
      if (!res.ok || !data.token) {
        showErr('staff', data.error || data.detail || '❌ Usuario o contraseña incorrectos.');
        return;
      }
      persistAndRedirect(data.token, data.user);
    } catch (err) {
      showErr('staff', '⚠️ Error de red. Verifica tu conexión.');
    } finally {
      btn.classList.remove('loading'); btn.disabled = false;
    }
  });

  // Submit CLIENTE
  panels.cliente.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearErr('cliente');
    const placa = document.getElementById('cli-placa').value.trim().toUpperCase();
    const pass = document.getElementById('cli-pass').value.trim();
    if (!placa || !pass){ showErr('cliente', '⚠️ Ingresa placa y contraseña.'); return; }
    const btn = panels.cliente.querySelector('.submit');
    btn.classList.add('loading'); btn.disabled = true;
    try {
      const { res, data } = await postLogin({ tipo:'cliente', placa, password: pass });
      if (res.status === 429) { showErr('cliente', '⛔ Demasiados intentos. Espera 15 minutos.'); return; }
      if (!res.ok || !data.token) {
        showErr('cliente', data.error || data.detail ||
          '❌ Placa o documento incorrectos. Tu contraseña inicial es tu DNI o RUC.');
        return;
      }
      persistAndRedirect(data.token, data.user);
    } catch (err) {
      showErr('cliente', '⚠️ Error de red. Verifica tu conexión.');
    } finally {
      btn.classList.remove('loading'); btn.disabled = false;
    }
  });

  // Si ya hay token guardado, redirigir directo (UX: evitar mostrar login al ya logueado)
  try {
    const tok = localStorage.getItem('sandoval_token');
    const usrRaw = localStorage.getItem('sandoval_user');
    if (tok && usrRaw){
      const usr = JSON.parse(usrRaw);
      // Validar que el token siga vivo antes de redirigir
      fetch('/api/auth/me', { headers: { 'Authorization': 'Bearer ' + tok } })
        .then(r => { if (r.ok) persistAndRedirect(tok, usr); })
        .catch(() => {});
    }
  } catch (_) {}
})();
</script>

</body></html>"""
