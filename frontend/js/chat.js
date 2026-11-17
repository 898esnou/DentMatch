/**
 * chat.js
 * ---------------------------------------------------------------------
 * Sección "Mensajes" de los dos portales (paciente y estudiante).
 * Una conversación por postulación aceptada: lista a la izquierda, hilo a la derecha.
 *
 * - Se pinta dentro de <div id="chat-app"> (ver los HTML de los portales).
 * - Cualquier botón con data-accion="chatear" data-id="<id postulación>" lleva
 *   a la sección y abre esa conversación.
 * - Sin WebSockets: se consulta la API cada pocos segundos (polling), más seguido
 *   con una conversación abierta. Lista e hilo se piden en paralelo.
 * - Lo que escribe la persona aparece al instante ("Enviando…") mientras el
 *   servidor lo modera y lo guarda; si se rechaza, se quita y se explica por qué.
 * - Si la conversación está cerrada (cancelada o terminada) es solo lectura y
 *   se avisa cuándo se borra el historial (30 días después del cierre).
 *
 * Requiere session.js, api.js, utils.js y formulario-modal.js (abrirFormulario).
 * ---------------------------------------------------------------------
 */
(function () {
  const REFRESCO_HILO_MS = 2500;   // con una conversación abierta: los mensajes nuevos llegan rápido
  const REFRESCO_LISTA_MS = 6000;  // sin conversación abierta: solo la lista y el contador
  const DIAS_HISTORIAL = 30;  // debe coincidir con DIAS_HISTORIAL del backend (app/routers/chat.py)
  const MIN_MENSAJES_REPORTAR = 3;  // debe coincidir con MIN_MENSAJES_REPORTAR de app/sanciones.py

  /* ---------- estado ---------- */
  let conversaciones = [];
  let activa = null;          // id de la postulación abierta (o null)
  let hilo = null;            // última respuesta del hilo abierto
  let errorHilo = "";         // por qué no se pudo cargar el hilo abierto (se reintenta solo)
  let verInapropiados = false; // el usuario decidió leer los mensajes bloqueados de la otra persona
  const hilosVistos = new Map();  // id -> último hilo cargado: al volver a una conversación se muestra al tiro
  let enviando = [];          // mensajes propios que el servidor aún no confirma: { clave, contenido, desdeId }
  let siguienteClave = 0;

  const app = document.getElementById("chat-app");
  if (!app) return;

  /* ---------- utilidades de formato (iniciales y esc vienen de utils.js) ---------- */
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

  const ETIQUETA_CATEGORIA = { insulto: "Insulto", acoso: "Acoso" };

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

  // Por qué el botón «Reportar» está desactivado (se mantiene visible para que se sepa que existe).
  function motivoSinReporte() {
    if (hilo.puede_reportar) return "Reportar a la otra persona";
    return hilo.mensajes.length < MIN_MENSAJES_REPORTAR
      ? `Podrás reportar cuando la conversación tenga al menos ${MIN_MENSAJES_REPORTAR} mensajes`
      : "Ya reportaste esta conversación: un administrador la está revisando";
  }

  // Mensajes bloqueados de la otra persona (cuenta sancionada): ocultos hasta que quien los recibe decida leerlos.
  function bloqueInapropiados() {
    const lista = hilo.mensajes_inapropiados || [];
    if (!lista.length) return "";
    const resumen = `<p class="chat__inap-titulo"><span class="material-symbols-rounded">visibility_off</span>
      La otra persona escribió ${lista.length === 1 ? "1 mensaje" : `${lista.length} mensajes`} con lenguaje inapropiado.
      La moderación los bloqueó y no te llegaron.</p>`;
    if (!verInapropiados) {
      return `<div class="chat__inap">${resumen}
        <button type="button" class="btn btn--outline btn--sm" data-accion="mostrar-inapropiados">
          <span class="material-symbols-rounded">visibility</span> Leer mensajes inapropiados</button></div>`;
    }
    const burbujas = lista.map((m) => `
      <div class="chat__msg">
        <div class="chat__burbuja chat__burbuja--inap">${esc(m.contenido)}</div>
        <small>${esc(ETIQUETA_CATEGORIA[m.categoria] || "Inapropiado")} · ${esc(hora(m.fecha))}</small>
      </div>`).join("");
    return `<div class="chat__inap chat__inap--abierto">${resumen}
      <p class="chat__inap-aviso"><span class="material-symbols-rounded">warning</span>
        Este es lenguaje inapropiado. Lo lees bajo tu responsabilidad.</p>
      ${burbujas}
      <button type="button" class="btn btn--outline btn--sm" data-accion="ocultar-inapropiados">
        <span class="material-symbols-rounded">visibility_off</span> Ocultar mensajes</button></div>`;
  }

  // Un mensaje «Enviando…» que el refresco ya trajo guardado (llegó antes que la respuesta del envío).
  function yaLlego(pendiente) {
    return hilo.mensajes.some((m) => m.mio && m.id > pendiente.desdeId && m.contenido === pendiente.contenido);
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
        ${c.puede_escribir ? `<button type="button" class="btn btn--ghost chat__reportar" data-accion="bloquear">
          <span class="material-symbols-rounded">block</span> Bloquear</button>` : ""}
        ${c.bloqueada_por_mi ? `<button type="button" class="btn btn--ghost chat__reportar" data-accion="desbloquear">
          <span class="material-symbols-rounded">lock_open</span> Desbloquear</button>` : ""}
        <button type="button" class="btn btn--ghost chat__reportar" data-accion="reportar"
                ${hilo.puede_reportar ? "" : "disabled"} title="${esc(motivoSinReporte())}">
          <span class="material-symbols-rounded">flag</span> Reportar</button>
      </div>`;

    // Solo bajamos al final si ya estaba abajo (para no molestar a quien lee mensajes antiguos).
    const estabaAbajo = elMensajes.scrollHeight - elMensajes.scrollTop - elMensajes.clientHeight < 80;
    const mensajes = hilo.mensajes.map((m) => `
      <div class="chat__msg ${m.mio ? "chat__msg--mio" : ""}">
        <div class="chat__burbuja">${esc(m.contenido)}</div>
        <small>${esc(hora(m.fecha_creacion))}${m.mio ? ` · ${m.leido ? "Visto" : "Enviado"}` : ""}</small>
      </div>`).join("") + enviando.filter((m) => !yaLlego(m)).map((m) => `
      <div class="chat__msg chat__msg--mio chat__msg--enviando">
        <div class="chat__burbuja">${esc(m.contenido)}</div>
        <small>Enviando…</small>
      </div>`).join("");
    const vacio = hilo.mensajes.length || enviando.length ? "" :
      `<p class="chat__vacio chat__vacio--centro">Aún no hay mensajes. Coordinen aquí fecha, hora y detalles de la atención.</p>`;
    const cerrada = c.puede_escribir ? "" : (c.cerrada_por_moderacion ? `
      <p class="chat__sistema chat__sistema--detenido">
        <span class="material-symbols-rounded">block</span>${esc(c.mensaje_cierre)}
      </p>` : c.bloqueada ? `
      <p class="chat__cerrada">
        <span class="material-symbols-rounded">block</span>
        ${c.bloqueada_por_mi ? "Bloqueaste esta conversación" : "La otra persona bloqueó esta conversación"}: nadie puede enviar mensajes.
        El historial se eliminará ${c.se_borra_el ? `en ${diasHasta(c.se_borra_el)} día(s)` : `a los ${DIAS_HISTORIAL} días`}.
        ${c.bloqueada_por_mi ? `<button type="button" class="btn btn--outline btn--sm" data-accion="desbloquear">Desbloquear</button>` : ""}
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
    elMensajes.innerHTML = vacio + mensajes + bloqueInapropiados() + moderacion + cerrada;
    elForm.hidden = !c.puede_escribir;
    elNota.hidden = !c.puede_escribir;
    if (estabaAbajo) elMensajes.scrollTop = elMensajes.scrollHeight;
  }

  /* ---------- datos ---------- */
  // La conversación abierta se está leyendo (el hilo la marca como leída en el servidor):
  // no muestra "no leídos" aunque la lista haya llegado antes que el hilo.
  function sinNoLeidosEnLaAbierta() {
    conversaciones.forEach((c) => { if (c.postulacion_id === activa) c.no_leidos = 0; });
  }

  async function cargarLista() {
    let r;
    try {
      r = await apiJson("/api/chat/conversaciones");
    } catch (error) {
      return;                             // sin conexión: se reintenta en el próximo refresco
    }
    if (!r.ok) return;
    conversaciones = r.data;
    sinNoLeidosEnLaAbierta();
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
    if (hilo && hilo.aviso_moderacion && !r.data.aviso_moderacion) {
      r.data.aviso_moderacion = hilo.aviso_moderacion;  // el servidor lo entrega una sola vez
    }
    hilosVistos.set(id, r.data);
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

  /* ---------- refresco automático ----------
     Lista e hilo se piden EN PARALELO (antes iban uno tras otro y la lista dos veces).
     Se usa setTimeout encadenado en vez de setInterval: si la red está lenta, una
     consulta nunca se encima con la siguiente. Con la pestaña oculta no se consulta. */
  let temporizador = null;
  let refrescando = null;   // la promesa del refresco en curso (para no duplicarlo)

  function refrescar() {
    if (refrescando) return refrescando;
    refrescando = Promise.all([cargarLista(), cargarHilo()])
      .catch(() => {})
      .finally(() => { refrescando = null; });
    return refrescando;
  }

  function programarRefresco() {
    clearTimeout(temporizador);
    temporizador = setTimeout(async () => {
      if (!document.hidden) await refrescar();
      programarRefresco();
    }, activa == null ? REFRESCO_LISTA_MS : REFRESCO_HILO_MS);
  }

  // Tras una acción del usuario (archivar, bloquear...): hilo y lista frescos, a la vez.
  // No reutiliza un refresco en curso, porque ese pudo empezar antes de la acción.
  function actualizarTodo() {
    return Promise.all([cargarHilo(), cargarLista()]);
  }

  // Al volver a la pestaña se actualiza al tiro, sin esperar al próximo ciclo.
  function refrescarAhora() {
    if (document.hidden) return;
    refrescar().finally(programarRefresco);
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
      descripcion: "Nadie podrá enviar mensajes aquí, pero el historial se conserva 30 días y solo tú podrás reabrir la conversación. La postulación no cambia.",
      textoBoton: "Archivar",
      campos: [],
      onEnviar: async () => {
        const r = await apiJson(`/api/chat/${id}/archivar`, "POST");
        if (!r.ok) return { ok: false, error: textoDeError(r) };
        mostrarAviso("Conversación archivada.");
        await actualizarTodo();
        return { ok: true };
      },
    });
  }

  async function reabrir() {
    if (activa == null) return;
    const r = await apiJson(`/api/chat/${activa}/reabrir`, "POST");
    if (!r.ok) return mostrarAviso(textoDeError(r), true);
    mostrarAviso("Conversación reabierta.");
    await actualizarTodo();
  }

  function bloquear() {
    if (activa == null) return;
    const id = activa;
    abrirFormulario({
      titulo: "Bloquear conversación",
      descripcion: "Nadie podrá enviar mensajes en este chat y solo tú podrás desbloquearlo. Si la persona se portó mal, también puedes reportarla.",
      textoBoton: "Bloquear",
      campos: [],
      onEnviar: async () => {
        const r = await apiJson(`/api/chat/${id}/bloquear`, "POST");
        if (!r.ok) return { ok: false, error: textoDeError(r) };
        mostrarAviso("Conversación bloqueada.");
        await actualizarTodo();
        return { ok: true };
      },
    });
  }

  async function desbloquear() {
    if (activa == null) return;
    const r = await apiJson(`/api/chat/${activa}/desbloquear`, "POST");
    if (!r.ok) return mostrarAviso(textoDeError(r), true);
    mostrarAviso("Conversación desbloqueada.");
    await actualizarTodo();
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
    const cambia = id !== activa;
    activa = id;
    if (cambia) {
      // Si ya se había abierto antes, se muestra lo último que se vio mientras llega lo nuevo.
      hilo = hilosVistos.get(id) || null;
      enviando = [];
      verInapropiados = false;
      mostrarAlerta("");
    }
    errorHilo = "";
    sinNoLeidosEnLaAbierta();
    pintarLista();
    pintarContador();
    pintarHilo();
    elMensajes.scrollTop = elMensajes.scrollHeight;
    await actualizarTodo();
    programarRefresco();  // con una conversación abierta se consulta más seguido
    if (!elForm.hidden) elTexto.focus();
  }

  /**
   * Envío "optimista": el mensaje se ve al instante como «Enviando…» y el cuadro queda libre
   * para seguir escribiendo. La moderación (que puede tardar un poco si consulta a la IA)
   * corre en el servidor; si lo rechaza, el mensaje se quita y vuelve al cuadro de texto.
   */
  async function enviar(evento) {
    evento.preventDefault();
    const contenido = elTexto.value.trim();
    if (!contenido || activa == null) return;
    const id = activa;
    const ultimo = hilo && hilo.mensajes.length ? hilo.mensajes[hilo.mensajes.length - 1].id : 0;
    const pendiente = { clave: siguienteClave++, contenido, desdeId: ultimo };
    enviando.push(pendiente);
    elTexto.value = "";
    mostrarAlerta("");
    pintarHilo();
    elMensajes.scrollTop = elMensajes.scrollHeight;

    let r;
    try {
      r = await apiJson(`/api/chat/${id}/mensajes`, "POST", { contenido });
    } catch (error) {
      r = null;                             // sin conexión
    }
    if (id !== activa) return;              // se cambió de conversación mientras se enviaba
    enviando = enviando.filter((m) => m.clave !== pendiente.clave);

    if (r && r.ok) {
      // Se agrega la respuesta del servidor (si el refresco no la trajo ya) sin esperar otra consulta.
      if (hilo && !hilo.mensajes.some((m) => m.id === r.data.id)) hilo.mensajes.push(r.data);
      pintarHilo();
      elMensajes.scrollTop = elMensajes.scrollHeight;
      refrescar();                          // actualiza vista previa y orden de la lista
      return;
    }
    // No se envió: se devuelve el texto al cuadro para que no se pierda.
    if (!elTexto.value) elTexto.value = contenido;
    pintarHilo();
    if (!r) {
      mostrarAviso("No se pudo enviar el mensaje. Revisa tu conexión.", true);
    } else if (!(r.status === 403 && /suspendida/i.test(textoDeError(r)))) {
      // 422 = bloqueado por la moderación; 409 = conversación cerrada.
      // (403 por suspensión: api.js ya muestra el cuadro de "Tu cuenta fue suspendida")
      mostrarAlerta(textoDeError(r));
      if (r.status === 409) refrescar();    // se cerró mientras tanto: se actualiza la vista
    }
    elTexto.focus();
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
    if (e.target.closest('[data-accion="bloquear"]')) bloquear();
    if (e.target.closest('[data-accion="desbloquear"]')) desbloquear();
  });
  elMensajes.addEventListener("click", (e) => {
    if (e.target.closest('[data-accion="reabrir"]')) reabrir();
    if (e.target.closest('[data-accion="desbloquear"]')) desbloquear();
    if (e.target.closest('[data-accion="mostrar-inapropiados"]')) { verInapropiados = true; pintarHilo(); }
    if (e.target.closest('[data-accion="ocultar-inapropiados"]')) { verInapropiados = false; pintarHilo(); }
  });

  // Botones "Chatear" de las postulaciones: llevan a la sección y abren la conversación.
  document.addEventListener("click", (e) => {
    const boton = e.target.closest('[data-accion="chatear"]');
    if (!boton) return;
    document.getElementById("mensajes").scrollIntoView({ behavior: "smooth", block: "start" });
    abrirConversacion(Number(boton.dataset.id));  // ya pide la lista y el hilo a la vez
  });

  document.addEventListener("visibilitychange", refrescarAhora);
  window.addEventListener("focus", refrescarAhora);

  /* ---------- inicio ---------- */
  pintarLista();
  pintarHilo();
  refrescarAhora();
})();
