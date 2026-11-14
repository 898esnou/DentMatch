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
  let errorHilo = "";         // por qué no se pudo cargar el hilo abierto (se reintenta solo)

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
        <p class="chat__alerta" id="chat-alerta" role="alert" hidden></p>
        <form class="chat__form" id="chat-form" autocomplete="off" hidden>
          <input id="chat-texto" type="text" maxlength="1000" placeholder="Escribe un mensaje…" aria-label="Mensaje" />
          <button type="submit" class="btn btn--primary btn--pill" id="chat-enviar">Enviar</button>
        </form>
        <p class="chat__nota" id="chat-nota" hidden>
          <span class="material-symbols-rounded">shield</span>
          Los mensajes se revisan automáticamente para mantener un trato respetuoso. Si algo te incomoda, usa «Reportar».
        </p>
      </section>
    </div>`;

  const elLista = document.getElementById("chat-lista");
  const elCabecera = document.getElementById("chat-cabecera");
  const elMensajes = document.getElementById("chat-mensajes");
  const elForm = document.getElementById("chat-form");
  const elTexto = document.getElementById("chat-texto");
  const elEnviar = document.getElementById("chat-enviar");
  const elAlerta = document.getElementById("chat-alerta");
  const elNota = document.getElementById("chat-nota");

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
          <span class="chat__previa">${esc(c.cerrada_por_moderacion ? "Chat detenido" : (c.ultimo_mensaje || "Aún sin mensajes"))}</span>
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
      const texto = activa == null ? "Elige una conversación para ver los mensajes."
        : errorHilo ? `${esc(errorHilo)}<br><small>Reintentando automáticamente…</small>`
        : "Cargando conversación…";
      elMensajes.innerHTML = `<p class="chat__vacio chat__vacio--centro"><span class="material-symbols-rounded">${errorHilo ? "sync_problem" : "forum"}</span><br>${texto}</p>`;
      elForm.hidden = true;
      elNota.hidden = true;
      return;
    }
    const c = hilo.conversacion;
    elCabecera.innerHTML = `
      <span class="avatar chat__avatar">${esc(iniciales(c.otra_parte.nombre))}</span>
      <div class="chat__cabecera-datos"><strong>${esc(c.otra_parte.nombre)}</strong>
        <small>${esc(c.solicitud_codigo)} · ${esc(c.titulo)}</small></div>
      <div class="chat__acciones">
        ${c.puede_escribir ? `<button type="button" class="btn btn--ghost chat__reportar" data-accion="archivar">
          <span class="material-symbols-rounded">inventory_2</span> Archivar</button>` : ""}
        ${hilo.puede_reportar ? `<button type="button" class="btn btn--ghost chat__reportar" data-accion="reportar">
          <span class="material-symbols-rounded">flag</span> Reportar</button>` : ""}
      </div>`;

    // Solo bajamos al final si ya estaba abajo (para no molestar a quien lee mensajes antiguos).
    const estabaAbajo = elMensajes.scrollHeight - elMensajes.scrollTop - elMensajes.clientHeight < 80;
    const mensajes = hilo.mensajes.map((m) => `
      <div class="chat__msg ${m.mio ? "chat__msg--mio" : ""}">
        <div class="chat__burbuja">${esc(m.contenido)}</div>
        <small>${esc(hora(m.fecha_creacion))}${m.mio ? ` · ${m.leido ? "Visto" : "Enviado"}` : ""}</small>
      </div>`).join("");
    const vacio = hilo.mensajes.length ? "" :
      `<p class="chat__vacio chat__vacio--centro">Aún no hay mensajes. Coordinen aquí fecha, hora y detalles de la atención.</p>`;
    const cerrada = c.puede_escribir ? "" : (c.cerrada_por_moderacion ? `
      <p class="chat__sistema chat__sistema--detenido">
        <span class="material-symbols-rounded">block</span>${esc(c.mensaje_cierre)}
      </p>` : c.archivada ? `
      <p class="chat__cerrada">
        <span class="material-symbols-rounded">inventory_2</span>
        ${c.archivada_por_mi ? "Archivaste esta conversación" : "La otra persona archivó esta conversación"}: nadie puede enviar mensajes.
        El historial se eliminará ${c.se_borra_el ? `en ${diasHasta(c.se_borra_el)} día(s)` : `a los ${DIAS_HISTORIAL} días`}.
        ${c.archivada_por_mi ? `<button type="button" class="btn btn--outline btn--sm" data-accion="reabrir">Reabrir</button>` : ""}
      </p>` : `
      <p class="chat__cerrada">
        <span class="material-symbols-rounded">lock</span>
        Conversación cerrada: solo puedes leerla. El historial se eliminará
        ${c.se_borra_el ? `en ${diasHasta(c.se_borra_el)} día(s)` : `a los ${DIAS_HISTORIAL} días`}.
      </p>`);
    const moderacion = hilo.aviso_moderacion ? `
      <p class="chat__sistema">
        <span class="material-symbols-rounded">shield</span>${esc(hilo.aviso_moderacion)}
      </p>` : "";
    elMensajes.innerHTML = vacio + mensajes + moderacion + cerrada;
    elForm.hidden = !c.puede_escribir;
    elNota.hidden = !c.puede_escribir;
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
    let r;
    try {
      r = await apiJson(`/api/chat/${id}/mensajes`);
    } catch (error) {
      r = { ok: false, data: null };      // sin conexión
    }
    if (id !== activa) return;            // cambió de conversación mientras cargaba
    if (!r.ok) {
      // Un fallo pasajero no debe vaciar el chat: se avisa y el refresco automático reintenta.
      if (!hilo) {
        errorHilo = textoDeError(r, "No se pudo cargar la conversación.");
        pintarHilo();
      }
      return;
    }
    errorHilo = "";
    // Solo se repinta si algo cambió (evita parpadeos y saltos de scroll).
    if (hilo && hilo.aviso_moderacion && !r.data.aviso_moderacion) {
      r.data.aviso_moderacion = hilo.aviso_moderacion;  // el servidor lo entrega una sola vez
    }
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
  function mostrarAlerta(texto) {
    elAlerta.textContent = texto;
    elAlerta.hidden = !texto;
  }

  function archivar() {
    if (activa == null) return;
    const id = activa;
    abrirFormulario({
      titulo: "Archivar conversación",
      descripcion: "Nadie podrá enviar mensajes aquí, pero el historial se conserva 30 días y solo tú podrás reabrir la conversación. La postulación y las citas no cambian.",
      textoBoton: "Archivar",
      campos: [],
      onEnviar: async () => {
        const r = await apiJson(`/api/chat/${id}/archivar`, "POST");
        if (!r.ok) return { ok: false, error: textoDeError(r) };
        mostrarAviso("Conversación archivada.");
        await cargarHilo();
        await cargarLista();
        return { ok: true };
      },
    });
  }

  async function reabrir() {
    if (activa == null) return;
    const r = await apiJson(`/api/chat/${activa}/reabrir`, "POST");
    if (!r.ok) return mostrarAviso(textoDeError(r), true);
    mostrarAviso("Conversación reabierta.");
    await cargarHilo();
    await cargarLista();
  }

  function reportar() {
    if (activa == null) return;
    const id = activa;
    abrirFormulario({
      titulo: "Reportar esta conversación",
      descripcion: "Un administrador revisará la conversación. Cuéntanos qué pasó.",
      textoBoton: "Enviar reporte",
      campos: [{ nombre: "motivo", etiqueta: "¿Qué ocurrió?", tipo: "textarea", requerido: true,
                 placeholder: "Describe brevemente el problema…" }],
      onEnviar: async (valores) => {
        const r = await apiJson(`/api/chat/${id}/reportar`, "POST", { motivo: valores.motivo });
        if (!r.ok) return { ok: false, error: textoDeError(r) };
        mostrarAviso(r.data.mensaje);
        await cargarHilo();
        return { ok: true };
      },
    });
  }
  async function abrirConversacion(id) {
    activa = id;
    hilo = null;
    errorHilo = "";
    mostrarAlerta("");
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
      if (!r.ok) {
        // 422 = mensaje bloqueado por la moderación; 403 = la cuenta quedó suspendida.
        // (si fue suspensión, api.js ya muestra el cuadro de "Tu cuenta fue suspendida")
        if (!(r.status === 403 && /suspendida/i.test(textoDeError(r)))) mostrarAlerta(textoDeError(r));
        return;
      }
      mostrarAlerta("");
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
  elTexto.addEventListener("input", () => { if (!elAlerta.hidden) mostrarAlerta(""); });
  elCabecera.addEventListener("click", (e) => {
    if (e.target.closest('[data-accion="reportar"]')) reportar();
    if (e.target.closest('[data-accion="archivar"]')) archivar();
  });
  elMensajes.addEventListener("click", (e) => {
    if (e.target.closest('[data-accion="reabrir"]')) reabrir();
  });

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
