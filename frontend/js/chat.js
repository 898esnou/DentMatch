/**
 * chat.js
 * ---------------------------------------------------------------------
 * Sección "Mensajes" de los dos portales (paciente y estudiante).
 * Una conversación por postulación aceptada: lista a la izquierda, hilo a la derecha.
 *
 * - Se pinta dentro de <div id="chat-app"> (ver los HTML de los portales).
 * - Cualquier botón con data-accion="chatear" data-id="<id postulación>" lleva
 *   a la sección y abre esa conversación.
 * - Sin WebSockets: se consulta la API cada pocos segundos (polling).
 * - Si la conversación está cerrada (cancelada o terminada) es solo lectura y
 *   se avisa cuándo se borra el historial (30 días después del cierre).
 *
 * Requiere session.js, api.js, utils.js (esc) y formulario-modal.js (apiJson).
 * ---------------------------------------------------------------------
 */
(function () {
  const REFRESCO_MS = 5000;   // cada cuánto se consulta la API
  const DIAS_HISTORIAL = 30;  // debe coincidir con DIAS_HISTORIAL del backend (app/routers/chat.py)

  /* ---------- estado ---------- */
  let conversaciones = [];
  let activa = null;          // id de la postulación abierta (o null)
  let hilo = null;            // última respuesta del hilo abierto

  const app = document.getElementById("chat-app");
  if (!app) return;

  /* ---------- utilidades de formato ---------- */
  function iniciales(nombre) {
    return nombre.split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
  }

  // Hora si es de hoy; si no, día y mes.
  function fechaCorta(iso) {
    const f = new Date(iso);
    if (f.toDateString() === new Date().toDateString()) {
      return f.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });
    }
    return f.toLocaleDateString("es-CL", { day: "2-digit", month: "short" });
  }

  function hora(iso) {
    return new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });
  }

  function diasHasta(iso) {
    return Math.max(Math.ceil((new Date(iso) - new Date()) / 86400000), 0);
  }

  /* ---------- estructura fija (se crea una sola vez) ---------- */
  app.innerHTML = `
    <div class="chat__aviso-privacidad">
      <span class="material-symbols-rounded">schedule</span>
      Por tu privacidad, cuando una conversación se cancela o el tratamiento termina,
      el historial se elimina automáticamente <strong>${DIAS_HISTORIAL} días</strong> después.
    </div>
    <div class="chat">
      <aside class="chat__lista" id="chat-lista" aria-label="Conversaciones"></aside>
      <section class="chat__hilo">
        <header class="chat__cabecera" id="chat-cabecera"></header>
        <div class="chat__mensajes" id="chat-mensajes" aria-live="polite"></div>
        <form class="chat__form" id="chat-form" autocomplete="off" hidden>
          <input id="chat-texto" type="text" maxlength="1000" placeholder="Escribe un mensaje…" aria-label="Mensaje" />
          <button type="submit" class="btn btn--primary btn--pill" id="chat-enviar">Enviar</button>
        </form>
      </section>
    </div>`;

  const elLista = document.getElementById("chat-lista");
  const elCabecera = document.getElementById("chat-cabecera");
  const elMensajes = document.getElementById("chat-mensajes");
  const elForm = document.getElementById("chat-form");
  const elTexto = document.getElementById("chat-texto");
  const elEnviar = document.getElementById("chat-enviar");

  /* ---------- pintado ---------- */
  function pintarLista() {
    if (!conversaciones.length) {
      elLista.innerHTML = `<p class="chat__vacio">Aún no tienes conversaciones. Cuando una postulación sea aceptada, podrás coordinar aquí la atención.</p>`;
      return;
    }
    elLista.innerHTML = conversaciones.map((c) => `
      <button type="button" class="chat__conv ${c.postulacion_id === activa ? "chat__conv--activa" : ""}"
              data-conversacion="${c.postulacion_id}">
        <span class="avatar chat__avatar">${esc(iniciales(c.otra_parte.nombre))}</span>
        <span class="chat__conv-texto">
          <strong>${esc(c.otra_parte.nombre)}</strong>
          <small>${esc(c.solicitud_codigo)} · ${esc(c.titulo)}</small>
          <span class="chat__previa">${esc(c.ultimo_mensaje || "Aún sin mensajes")}</span>
        </span>
        <span class="chat__lateral">
          ${c.ultima_fecha ? `<small>${esc(fechaCorta(c.ultima_fecha))}</small>` : ""}
          ${c.no_leidos ? `<span class="chat__nuevos">${c.no_leidos}</span>` : ""}
        </span>
      </button>`).join("");
  }

  function pintarHilo() {
    if (activa == null || !hilo) {
      elCabecera.innerHTML = "";
      elMensajes.innerHTML = `<p class="chat__vacio chat__vacio--centro"><span class="material-symbols-rounded">forum</span><br>Elige una conversación para ver los mensajes.</p>`;
      elForm.hidden = true;
      return;
    }
    const c = hilo.conversacion;
    elCabecera.innerHTML = `
      <span class="avatar chat__avatar">${esc(iniciales(c.otra_parte.nombre))}</span>
      <div><strong>${esc(c.otra_parte.nombre)}</strong>
        <small>${esc(c.solicitud_codigo)} · ${esc(c.titulo)}</small></div>`;

    // Solo bajamos al final si ya estaba abajo (para no molestar a quien lee mensajes antiguos).
    const estabaAbajo = elMensajes.scrollHeight - elMensajes.scrollTop - elMensajes.clientHeight < 80;
    const mensajes = hilo.mensajes.map((m) => `
      <div class="chat__msg ${m.mio ? "chat__msg--mio" : ""}">
        <div class="chat__burbuja">${esc(m.contenido)}</div>
        <small>${esc(hora(m.fecha_creacion))}${m.mio ? ` · ${m.leido ? "Visto" : "Enviado"}` : ""}</small>
      </div>`).join("");
    const vacio = hilo.mensajes.length ? "" :
      `<p class="chat__vacio chat__vacio--centro">Aún no hay mensajes. Coordinen aquí fecha, hora y detalles de la atención.</p>`;
    const cerrada = c.puede_escribir ? "" : `
      <p class="chat__cerrada">
        <span class="material-symbols-rounded">lock</span>
        Conversación cerrada: solo puedes leerla. El historial se eliminará
        ${c.se_borra_el ? `en ${diasHasta(c.se_borra_el)} día(s)` : `a los ${DIAS_HISTORIAL} días`}.
      </p>`;
    elMensajes.innerHTML = vacio + mensajes + cerrada;
    elForm.hidden = !c.puede_escribir;
    if (estabaAbajo) elMensajes.scrollTop = elMensajes.scrollHeight;
  }

  /* ---------- datos ---------- */
  async function cargarLista() {
    const r = await apiJson("/api/chat/conversaciones");
    if (!r.ok) return;
    conversaciones = r.data;
    pintarLista();
    pintarContador();
  }

  async function cargarHilo() {
    if (activa == null) return;
    const id = activa;
    const r = await apiJson(`/api/chat/${id}/mensajes`);
    if (id !== activa) return;            // cambió de conversación mientras cargaba
    if (!r.ok) { activa = null; hilo = null; return pintarHilo(); }
    // Solo se repinta si algo cambió (evita parpadeos y saltos de scroll).
    if (!hilo || JSON.stringify(hilo) !== JSON.stringify(r.data)) {
      const eraNueva = !hilo;
      hilo = r.data;
      pintarHilo();
      if (eraNueva) elMensajes.scrollTop = elMensajes.scrollHeight;
    }
  }

  // Mensajes sin leer en total, junto al enlace "Mensajes" del menú.
  function pintarContador() {
    const insignia = document.getElementById("chat-contador");
    if (!insignia) return;
    const total = conversaciones.reduce((suma, c) => suma + c.no_leidos, 0);
    insignia.textContent = total > 99 ? "99+" : total;
    insignia.hidden = total === 0;
  }

  async function refrescar() {
    if (document.hidden) return;
    await cargarLista();
    await cargarHilo();   // abrir/mantener el hilo abierto marca sus mensajes como leídos
    await cargarLista();  // ...y se refleja en la lista y en el contador
  }

  /* ---------- acciones ---------- */
  async function abrirConversacion(id) {
    activa = id;
    hilo = null;
    pintarLista();
    pintarHilo();
    await cargarHilo();
    await cargarLista();
    if (!elForm.hidden) elTexto.focus();
  }

  async function enviar(evento) {
    evento.preventDefault();
    const contenido = elTexto.value.trim();
    if (!contenido || activa == null) return;
    elEnviar.disabled = true;
    try {
      const r = await apiJson(`/api/chat/${activa}/mensajes`, "POST", { contenido });
      if (!r.ok) return mostrarAviso(textoDeError(r), true);
      elTexto.value = "";
      await cargarHilo();
      await cargarLista();
    } catch (error) {
      mostrarAviso("No se pudo enviar el mensaje. Revisa tu conexión.", true);
    } finally {
      elEnviar.disabled = false;
      elTexto.focus();
    }
  }

  /* ---------- eventos ---------- */
  elLista.addEventListener("click", (e) => {
    const fila = e.target.closest("[data-conversacion]");
    if (fila) abrirConversacion(Number(fila.dataset.conversacion));
  });
  elForm.addEventListener("submit", enviar);

  // Botones "Chatear" de las postulaciones: llevan a la sección y abren la conversación.
  document.addEventListener("click", async (e) => {
    const boton = e.target.closest('[data-accion="chatear"]');
    if (!boton) return;
    document.getElementById("mensajes").scrollIntoView({ behavior: "smooth", block: "start" });
    await cargarLista();
    abrirConversacion(Number(boton.dataset.id));
  });

  /* ---------- inicio ---------- */
  pintarLista();
  pintarHilo();
  refrescar().catch(() => {});
  setInterval(() => refrescar().catch(() => {}), REFRESCO_MS);
})();
