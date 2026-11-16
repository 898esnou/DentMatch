/**
 * admin.js
 * ---------------------------------------------------------------------
 * Panel de administración (Admin.html): Reportes, Verificaciones, Cuentas y Resumen.
 *
 * - Cada sección se pinta dentro de <main id="admin-contenido"> según el # de la URL.
 * - Los contadores del menú (reportes y verificaciones pendientes) se actualizan solos cada
 *   30 segundos; la bandeja de reportes también, sin perder el reporte que se está leyendo.
 * - Toda decisión pasa por un cuadro de confirmación con una nota interna opcional.
 *
 * Requiere session.js, api.js, utils.js (esc) y formulario-modal.js (apiJson, abrirFormulario...).
 * ---------------------------------------------------------------------
 */
(function () {
  const REFRESCO_MS = 30000;
  const contenido = document.getElementById("admin-contenido");

  /* ---------- estado ---------- */
  let seccion = "reportes";
  let filtroReportes = "Pendiente";
  let reportes = [];
  let reporteActivo = null;      // id del reporte abierto
  let detalle = null;            // su detalle completo
  let recienResuelto = null;     // reporte que acabo de resolver: sigue a la vista con su resolución
  let filtroVerif = "En Verificación";
  let busquedaCuentas = "";
  let filtroCuentas = "";

  const CATEGORIAS = { insulto: "Insulto", acoso: "Acoso o insinuación", fuera_de_tema: "Fuera de tema" };
  const FUENTES = { reglas: "Detectado por reglas", ia: "Detectado por IA" };

  /* ---------- utilidades ---------- */
  const iniciales = (nombre) => nombre.split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

  function fechaRel(iso) {
    const f = new Date(iso);
    const min = Math.round((Date.now() - f.getTime()) / 60000);
    if (min < 1) return "ahora";
    if (min < 60) return `hace ${min} min`;
    if (min < 60 * 24) return `hace ${Math.round(min / 60)} h`;
    if (min < 60 * 48) return "ayer";
    return f.toLocaleDateString("es-CL", { day: "2-digit", month: "short" });
  }
  const fechaLarga = (iso) => new Date(iso).toLocaleString("es-CL", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  const hora = (iso) => new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });

  const tag = (texto, color, icono) =>
    `<span class="tag tag--${color}">${icono ? `<span class="material-symbols-rounded">${icono}</span>` : ""}${esc(texto)}</span>`;

  function tagCuenta(estado) {
    if (estado === "baneado") return tag("Baneada", "rojo", "block");
    if (estado === "suspendido") return tag("En time-out", "ambar", "schedule");
    return tag("Activa", "verde", "check_circle");
  }
  const tagRol = (rol) => tag(rol === "estudiante" ? "Estudiante" : "Paciente", "azul");

  const vacio = (icono, texto) => `<p class="vacio-admin"><span class="material-symbols-rounded">${icono}</span>${esc(texto)}</p>`;

  function cabecera(titulo, subtitulo, extra = "") {
    return `<div class="admin__cabecera"><div><h1>${esc(titulo)}</h1><p>${esc(subtitulo)}</p></div>${extra}</div>`;
  }

  async function llamar(ruta, metodo, cuerpo) {
    try {
      return await apiJson(ruta, metodo, cuerpo);
    } catch (e) {
      return { ok: false, status: 0, data: null };
    }
  }

  /* ---------- navegación ---------- */
  function irA(nombre) {
    seccion = nombre;
    document.querySelectorAll(".admin__link").forEach((b) =>
      b.classList.toggle("admin__link--activo", b.dataset.seccion === nombre));
    if (location.hash !== `#${nombre}`) history.replaceState(null, "", `#${nombre}`);
    pintarSeccion();
  }

  function pintarSeccion() {
    if (seccion === "reportes") return verReportes();
    if (seccion === "verificaciones") return verVerificaciones();
    if (seccion === "cuentas") return verCuentas();
    return verResumen();
  }

  document.querySelector(".admin__menu").addEventListener("click", (e) => {
    const b = e.target.closest("[data-seccion]");
    if (b) irA(b.dataset.seccion);
  });

  /* ---------- contadores del menú ---------- */
  function contador(id, n) {
    const el = document.getElementById(id);
    el.textContent = n > 99 ? "99+" : n;
    el.hidden = n === 0;
  }

  async function actualizarContadores() {
    const r = await llamar("/api/admin/resumen");
    if (!r.ok) return null;
    contador("cnt-reportes", r.data.reportes_pendientes);
    contador("cnt-verificaciones", r.data.verificaciones_pendientes);
    return r.data;
  }

  /* =====================================================================
     REPORTES
  ===================================================================== */
  async function verReportes(mantener = false) {
    if (!mantener) {
      contenido.innerHTML = cabecera("Reportes", "Revisa la evidencia y decide qué hacer con cada caso.") + `<p class="vacio-admin">Cargando…</p>`;
    }
    const r = await llamar(`/api/admin/reportes?estado=${encodeURIComponent(filtroReportes)}`);
    if (seccion !== "reportes") return;
    if (!r.ok) {
      contenido.innerHTML = cabecera("Reportes", "") + vacio("sync_problem", textoDeError(r, "No se pudieron cargar los reportes."));
      return;
    }
    reportes = r.data;
    if (!reportes.some((x) => x.id === reporteActivo) && reporteActivo !== recienResuelto) { reporteActivo = null; detalle = null; }
    pintarReportes();
    if (reporteActivo) await cargarDetalle(reporteActivo, true);
  }

  function pintarReportes() {
    const filtros = ["Pendiente", "Resuelto"].map((e) =>
      `<button type="button" class="filtro ${filtroReportes === e ? "filtro--activo" : ""}" data-filtro-reportes="${e}">${e === "Pendiente" ? "Pendientes" : "Resueltos"}</button>`).join("");
    const visibles = detalle && detalle.id === recienResuelto && !reportes.some((x) => x.id === detalle.id)
      ? [detalle, ...reportes] : reportes;
    const lista = visibles.length ? visibles.map((x) => `
      <button type="button" class="rep-item ${x.id === reporteActivo ? "rep-item--activo" : ""}" data-reporte="${x.id}">
        <span class="rep-item__fila">
          ${x.estado === "Resuelto" ? tag(etiquetaDecision(x.decision), "gris")
            : x.origen === "automatico" ? tag("Automático", "rojo", "smart_toy") : tag("Reporte", "ambar", "flag")}
          <span class="rep-item__fecha">${esc(fechaRel(x.fecha_creacion))}</span>
        </span>
        <span class="rep-item__nombre">${esc(x.reportado.nombre)}</span>
        <span class="rep-item__fila">${tagRol(x.reportado.rol)} ${tagCuenta(x.reportado.estado_cuenta)}</span>
        <span class="rep-item__motivo">${esc(x.motivo)}</span>
      </button>`).join("")
      : vacio("task_alt", filtroReportes === "Pendiente" ? "No hay reportes pendientes. Todo en orden." : "Aún no hay reportes resueltos.");

    contenido.innerHTML = cabecera(
      "Reportes",
      "Los automáticos (3 advertencias) aparecen primero: la cuenta ya está bloqueada esperando tu decisión.",
      `<div class="admin__filtros">${filtros}</div>`,
    ) + `<div class="reportes"><div class="reportes__lista">${lista}</div><article class="card detalle" id="rep-detalle">${htmlDetalle()}</article></div>`;
  }

  const etiquetaDecision = (d) => ({ baneo: "Baneada", suspension: "Time-out", descartar: "Descartado" }[d] || "Resuelto");

  async function cargarDetalle(id, silencioso = false) {
    reporteActivo = id;
    if (!silencioso) {
      detalle = null;
      document.querySelectorAll(".rep-item").forEach((b) => b.classList.toggle("rep-item--activo", Number(b.dataset.reporte) === id));
      const caja = document.getElementById("rep-detalle");
      if (caja) caja.innerHTML = `<p class="vacio-admin">Cargando…</p>`;
    }
    const r = await llamar(`/api/admin/reportes/${id}`);
    if (id !== reporteActivo || seccion !== "reportes") return;
    if (!r.ok) {
      const caja = document.getElementById("rep-detalle");
      if (caja) caja.innerHTML = vacio("sync_problem", textoDeError(r, "No se pudo abrir el reporte."));
      return;
    }
    detalle = r.data;
    const caja = document.getElementById("rep-detalle");
    if (caja) caja.innerHTML = htmlDetalle();
  }

  function htmlDetalle() {
    if (!detalle) return vacio("flag", "Elige un reporte de la lista para ver la evidencia.");
    const d = detalle;
    const rep = d.reportado;
    const quien = d.origen === "automatico" ? "Lo generó el sistema" : `Lo envió ${esc(d.reportante || "otra persona")}`;

    const bloqueados = d.bloqueados.length ? d.bloqueados.map((b) => `
      <div class="bloqueado">
        ${tag(CATEGORIAS[b.categoria] || b.categoria, "rojo")}
        <q>${esc(b.contenido)}</q>
        <small>${esc(FUENTES[b.fuente] || b.fuente)} · ${esc(hora(b.fecha))}</small>
      </div>`).join("") : `<div class="detalle__caja">La moderación no bloqueó ningún mensaje de esta persona en esta conversación.</div>`;

    const hilo = d.mensajes.length ? `<div class="hilo">${d.mensajes.map((m) => `
      <div class="hilo__msg ${m.de_reportado ? "hilo__msg--reportado" : ""}">
        <span class="hilo__burbuja">${esc(m.contenido)}</span>
        <small>${esc(m.autor)}${m.de_reportado ? " (reportado)" : ""} · ${esc(hora(m.fecha))}</small>
      </div>`).join("")}</div>`
      : `<div class="detalle__caja">No hay mensajes guardados en la copia de esta conversación.</div>`;

    let pie;
    if (d.estado === "Pendiente") {
      const baneada = rep.estado_cuenta === "baneado";
      const reactiva = d.origen === "automatico" && rep.estado_cuenta !== "activo";
      pie = `<div class="acciones">
        <button type="button" class="accion accion--peligro" data-decision="baneo">
          <strong><span class="material-symbols-rounded">block</span>${baneada ? "Mantener baneo" : "Banear cuenta"}</strong>
          <span class="accion__texto">La cuenta queda bloqueada sin fecha de término.</span>
        </button>
        <button type="button" class="accion accion--aviso" data-decision="suspension">
          <strong><span class="material-symbols-rounded">schedule</span>Dar time-out</strong>
          <span class="accion__texto">Bloquea la cuenta unos días y deja un mensaje para la persona.</span>
        </button>
        <button type="button" class="accion" data-decision="descartar">
          <strong><span class="material-symbols-rounded">check_circle</span>Descartar</strong>
          <span class="accion__texto">${reactiva ? "No hubo falta: se reactiva la cuenta." : "No hubo falta: la cuenta no cambia."}</span>
        </button>
      </div>`;
    } else {
      const x = d.resolucion || {};
      const detalleDecision = x.decision === "suspension" ? `Time-out de ${x.dias} día(s)` : etiquetaDecision(x.decision);
      pie = `<div class="resolucion"><strong>Resuelto: ${esc(detalleDecision)}</strong>
        Por ${esc(x.resuelto_por || "un administrador")}${x.fecha ? ` · ${esc(fechaLarga(x.fecha))}` : ""}
        ${x.nota ? `<br>Nota interna: ${esc(x.nota)}` : ""}</div>`;
    }

    return `
      <div class="detalle__cabecera">
        <span class="avatar">${esc(iniciales(rep.nombre))}</span>
        <div>
          <div class="detalle__nombre">${esc(rep.nombre)}</div>
          <div class="detalle__meta">${tagRol(rep.rol)} ${tagCuenta(rep.estado_cuenta)}
            <span>${rep.advertencias} advertencia(s) vigente(s)</span><span>·</span><span>${d.reportes_previos} reporte(s) previo(s)</span></div>
        </div>
      </div>
      <div class="detalle__bloque"><h3>Por qué se creó</h3>
        <div class="detalle__caja">${esc(d.motivo)}
          <small>${quien} · ${esc(fechaLarga(d.fecha_creacion))}${d.conversacion ? ` · Conversación sobre «${esc(d.conversacion)}»` : ""}${d.otra_persona ? ` con ${esc(d.otra_persona)}` : ""}</small></div></div>
      <div class="detalle__bloque"><h3>Mensajes que la moderación bloqueó</h3>${bloqueados}</div>
      <div class="detalle__bloque"><h3>Conversación (últimos mensajes)</h3>${hilo}</div>
      <div class="detalle__bloque"><h3>${d.estado === "Pendiente" ? "¿Qué quieres hacer?" : "Resolución"}</h3>${pie}</div>`;
  }

  /* ---------- decisiones sobre un reporte ---------- */
  function decidir(decision) {
    if (!detalle) return;
    const d = detalle;
    const nombre = d.reportado.nombre;
    const campoNota = { nombre: "nota", etiqueta: "Nota interna (opcional, solo la ven los administradores)", tipo: "textarea" };
    const enviar = async (valores) => {
      const cuerpo = { decision, nota: valores.nota };
      if (decision === "suspension") { cuerpo.dias = Number(valores.dias); cuerpo.mensaje = valores.mensaje; }
      const r = await llamar(`/api/admin/reportes/${d.id}/resolver`, "POST", cuerpo);
      if (!r.ok) return { ok: false, error: textoDeError(r) };
      mostrarAviso("Decisión guardada.");
      detalle = r.data;
      recienResuelto = d.id;
      actualizarContadores();
      await verReportes(true);
      return { ok: true };
    };

    if (decision === "baneo") {
      abrirFormulario({
        titulo: d.reportado.estado_cuenta === "baneado" ? "Mantener el baneo" : "Banear cuenta",
        descripcion: `${nombre} quedará bloqueado sin fecha de término. Se cancelan sus postulaciones activas y se avisa a las otras personas.`,
        textoBoton: "Confirmar baneo", campos: [campoNota], onEnviar: enviar,
      });
    } else if (decision === "suspension") {
      abrirFormulario({
        titulo: "Dar time-out",
        descripcion: `${nombre} no podrá entrar durante ese tiempo y luego volverá a tener acceso con sus advertencias en cero. Se cancelan sus postulaciones activas.`,
        textoBoton: "Aplicar time-out",
        campos: [
          { nombre: "dias", etiqueta: "Duración", tipo: "select", requerido: true, valor: "7",
            opciones: [1, 3, 7, 15, 30].map((n) => ({ valor: String(n), texto: n === 1 ? "1 día" : `${n} días` })) },
          { nombre: "mensaje", etiqueta: "Mensaje para la persona (lo verá al intentar entrar)", tipo: "textarea",
            placeholder: "Ej.: Te pedimos mantener un trato respetuoso con los pacientes." },
          campoNota,
        ],
        onEnviar: enviar,
      });
    } else {
      const reactiva = d.origen === "automatico" && d.reportado.estado_cuenta !== "activo";
      abrirFormulario({
        titulo: "Descartar reporte",
        descripcion: reactiva
          ? `No se encontró una falta: la cuenta de ${nombre} se reactiva y sus advertencias vuelven a cero. Los chats que se detuvieron no se reabren, pero se avisa a ambas personas.`
          : "No se encontró una falta: la cuenta no cambia. Quien reportó recibirá un aviso de que se revisó.",
        textoBoton: "Descartar", campos: [campoNota], onEnviar: enviar,
      });
    }
  }

  contenido.addEventListener("click", (e) => {
    const f = e.target.closest("[data-filtro-reportes]");
    if (f) { filtroReportes = f.dataset.filtroReportes; reporteActivo = null; detalle = null; recienResuelto = null; return verReportes(); }
    const item = e.target.closest("[data-reporte]");
    if (item) { recienResuelto = null; return cargarDetalle(Number(item.dataset.reporte)); }
    const accion = e.target.closest("[data-decision]");
    if (accion) decidir(accion.dataset.decision);
  });

  /* =====================================================================
     VERIFICACIONES (certificados de alumno regular)
  ===================================================================== */
  const ESTADOS_VERIF = ["En Verificación", "No verificado", "Activo", "Rechazado", ""];
  const COLOR_VERIF = { "En Verificación": "ambar", "No verificado": "gris", Activo: "verde", Rechazado: "rojo" };

  let listaVerif = [];

  async function verVerificaciones() {
    const filtros = `<select class="admin__select" id="filtro-verif" aria-label="Estado">
      ${ESTADOS_VERIF.map((e) => `<option value="${e}" ${e === filtroVerif ? "selected" : ""}>${e || "Todos los estados"}</option>`).join("")}</select>`;
    contenido.innerHTML = cabecera("Verificaciones", "Estudiantes que subieron su certificado de alumno regular. Revísalo y apruébalo o recházalo.", filtros)
      + `<p class="vacio-admin">Cargando…</p>`;
    const r = await llamar(`/api/admin/estudiantes${filtroVerif ? `?estado=${encodeURIComponent(filtroVerif)}` : ""}`);
    if (seccion !== "verificaciones") return;
    listaVerif = r.ok ? r.data : [];
    const lista = !r.ok ? vacio("sync_problem", textoDeError(r, "No se pudo cargar la lista."))
      : r.data.length ? `<div class="filas">${r.data.map((u) => `
        <div class="fila">
          <div class="fila__persona"><span class="avatar">${esc(iniciales(u.nombre_completo))}</span>
            <div><strong>${esc(u.nombre_completo)}</strong><small>${esc(u.correo)}${u.rut ? ` · ${esc(u.rut)}` : ""}</small></div></div>
          <div class="fila__datos"><span>${esc(u.universidad)} · ${u.ano_carrera}º año</span>${tag(u.estado_verificacion, COLOR_VERIF[u.estado_verificacion] || "gris")}</div>
          <div class="fila__acciones">
            <button type="button" class="btn btn--ghost btn--sm" data-revisar="${u.id}"><span class="material-symbols-rounded">fact_check</span> Revisar solicitud</button>
            <button type="button" class="btn btn--primary btn--sm" data-verif="Activo" data-id="${u.id}" data-nombre="${esc(u.nombre_completo)}"><span class="material-symbols-rounded">check</span> Aprobar</button>
            <button type="button" class="btn btn--ghost btn--sm" data-verif="Rechazado" data-id="${u.id}" data-nombre="${esc(u.nombre_completo)}"><span class="material-symbols-rounded">close</span> Rechazar</button>
          </div>
        </div>`).join("")}</div>`
        : vacio("task_alt", filtroVerif === "En Verificación" ? "No hay certificados esperando revisión." : "No hay estudiantes con ese estado.");
    contenido.innerHTML = cabecera("Verificaciones", "Estudiantes que subieron su certificado de alumno regular. Revísalo y apruébalo o recházalo.", filtros) + lista;
  }

  async function abrirCertificado(id) {
    const respuesta = await apiFetch(`/api/admin/estudiantes/${id}/certificado`);
    if (!respuesta.ok) return mostrarAviso("No se pudo abrir el certificado.", true);
    const url = URL.createObjectURL(await respuesta.blob());
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  /** Revisión con todo a la vista: los datos que ingresó el estudiante y su certificado, lado a lado. */
  async function revisarSolicitud(id) {
    const u = listaVerif.find((x) => String(x.id) === String(id));
    if (!u) return;
    const fila = (etiqueta, valor) => `<div><dt>${etiqueta}</dt><dd>${valor}</dd></div>`;
    const auto = u.certificado_revision
      ? (u.certificado_resuelto_por === "sistema"
          ? (u.certificado_revision === "Aprobada" ? "El sistema validó el certificado (QR)."
            : `El sistema lo rechazó: ${esc(u.certificado_motivo || "los datos no corresponden")}.`)
          : u.certificado_revision === "Pendiente" ? "Pendiente de revisión manual."
          : `Resuelto por un administrador (${esc(u.certificado_revision.toLowerCase())}).`)
      : "Todavía no sube un certificado.";
    const dialogo = document.createElement("dialog");
    dialogo.className = "rev";
    dialogo.innerHTML = `
      <header class="rev__cab">
        <div><h2>Solicitud de ${esc(u.nombre_completo)}</h2><small>Compara los datos con el certificado antes de decidir.</small></div>
        <button type="button" class="btn btn--ghost btn--sm" data-rev="cerrar" aria-label="Cerrar"><span class="material-symbols-rounded">close</span></button>
      </header>
      <div class="rev__cuerpo">
        <dl class="rev__datos">
          ${fila("Nombre", esc(u.nombre_completo))}
          ${fila("RUT", esc(u.rut || "—"))}
          ${fila("Correo", esc(u.correo))}
          ${fila("Universidad", esc(u.universidad))}
          ${fila("Año de carrera", `${esc(u.ano_carrera)}º año`)}
          ${fila("Cuenta creada", u.fecha_registro ? esc(fechaLarga(u.fecha_registro)) : "—")}
          ${fila("Estado", tag(u.estado_verificacion, COLOR_VERIF[u.estado_verificacion] || "gris"))}
          ${fila("Certificado subido", u.certificado_fecha ? esc(fechaLarga(u.certificado_fecha)) : "—")}
          ${fila("Revisión automática", auto)}
        </dl>
        <div class="rev__visor" id="rev-visor"><p class="vacio-admin">Cargando certificado…</p></div>
      </div>
      <footer class="rev__pie">
        <button type="button" class="btn btn--ghost" data-rev="rechazar"><span class="material-symbols-rounded">close</span> Rechazar</button>
        <button type="button" class="btn btn--primary" data-rev="aprobar"><span class="material-symbols-rounded">check</span> Aprobar</button>
      </footer>`;
    document.body.appendChild(dialogo);
    let urlBlob = null;
    const cerrar = () => { if (urlBlob) URL.revokeObjectURL(urlBlob); dialogo.close(); dialogo.remove(); };
    dialogo.addEventListener("click", (e) => {
      const b = e.target.closest("[data-rev]");
      if (!b) return;
      cerrar();
      if (b.dataset.rev === "aprobar") decidirVerificacion(u.id, "Activo", u.nombre_completo);
      if (b.dataset.rev === "rechazar") decidirVerificacion(u.id, "Rechazado", u.nombre_completo);
    });
    dialogo.addEventListener("cancel", (e) => { e.preventDefault(); cerrar(); });
    dialogo.showModal();

    const visor = dialogo.querySelector("#rev-visor");
    if (!u.certificado_documento) { visor.innerHTML = vacio("description", "Este estudiante todavía no subió su certificado."); return; }
    const respuesta = await apiFetch(`/api/admin/estudiantes/${u.id}/certificado`);
    if (!respuesta.ok) { visor.innerHTML = vacio("sync_problem", "No se pudo abrir el certificado."); return; }
    const blob = await respuesta.blob();
    urlBlob = URL.createObjectURL(blob);
    const documento = blob.type.startsWith("image/")
      ? `<img src="${urlBlob}" alt="Certificado de alumno regular de ${esc(u.nombre_completo)}" />`
      : `<iframe src="${urlBlob}" title="Certificado de alumno regular de ${esc(u.nombre_completo)}"></iframe>`;
    // Si el navegador no muestra el PDF dentro de la ventana, queda el enlace para abrirlo aparte.
    visor.innerHTML = `<a class="rev__abrir" href="${urlBlob}" target="_blank" rel="noopener"><span class="material-symbols-rounded">open_in_new</span> Abrir en una pestaña nueva</a>${documento}`;
  }

  function decidirVerificacion(id, estado, nombre) {
    const rechazo = estado === "Rechazado";
    abrirFormulario({
      titulo: rechazo ? "Rechazar certificado" : "Aprobar certificado",
      descripcion: rechazo
        ? `${nombre} verá el motivo para corregirlo y volver a subir su certificado.`
        : `${nombre} quedará verificado y podrá postular a casos y chatear con pacientes.`,
      textoBoton: rechazo ? "Rechazar" : "Aprobar",
      campos: rechazo ? [{ nombre: "motivo", etiqueta: "Qué debe corregir", tipo: "textarea", requerido: true }] : [],
      onEnviar: async (valores) => {
        const r = await llamar(`/api/admin/estudiantes/${id}/verificacion`, "PATCH", { estado, motivo: valores.motivo });
        if (!r.ok) return { ok: false, error: textoDeError(r) };
        mostrarAviso(rechazo ? "Certificado rechazado." : "Estudiante verificado.");
        actualizarContadores();
        verVerificaciones();
        return { ok: true };
      },
    });
  }

  contenido.addEventListener("change", (e) => {
    if (e.target.id === "filtro-verif") { filtroVerif = e.target.value; verVerificaciones(); }
    if (e.target.id === "filtro-cuentas") { filtroCuentas = e.target.value; verCuentas(true); }
  });
  contenido.addEventListener("click", (e) => {
    const cert = e.target.closest("[data-cert]");
    if (cert) return abrirCertificado(cert.dataset.cert);
    const rev = e.target.closest("[data-revisar]");
    if (rev) return revisarSolicitud(rev.dataset.revisar);
    const v = e.target.closest("[data-verif]");
    if (v) decidirVerificacion(v.dataset.id, v.dataset.verif, v.dataset.nombre);
  });

  /* =====================================================================
     CUENTAS
  ===================================================================== */
  let temporizadorBusqueda = null;

  async function verCuentas(sinRepintar = false) {
    if (!sinRepintar || !document.getElementById("buscar-cuentas")) {
      contenido.innerHTML = cabecera("Cuentas", "Busca a una persona para ver su estado y levantar una sanción si corresponde.",
        `<div class="admin__filtros">
          <input type="search" class="admin__buscar" id="buscar-cuentas" placeholder="Buscar por nombre o correo" aria-label="Buscar" value="${esc(busquedaCuentas)}" />
          <select class="admin__select" id="filtro-cuentas" aria-label="Estado de la cuenta">
            <option value="">Todas</option><option value="baneado">Baneadas</option><option value="suspendido">En time-out</option><option value="activo">Activas</option>
          </select></div>`) + `<div id="lista-cuentas"><p class="vacio-admin">Cargando…</p></div>`;
      document.getElementById("filtro-cuentas").value = filtroCuentas;
    }
    const params = new URLSearchParams();
    if (busquedaCuentas.trim()) params.set("q", busquedaCuentas.trim());
    if (filtroCuentas) params.set("estado", filtroCuentas);
    const r = await llamar(`/api/admin/cuentas?${params}`);
    if (seccion !== "cuentas") return;
    const caja = document.getElementById("lista-cuentas");
    if (!caja) return;
    caja.innerHTML = !r.ok ? vacio("sync_problem", textoDeError(r, "No se pudo cargar la lista."))
      : r.data.length ? `<div class="filas">${r.data.map((c) => `
        <div class="fila">
          <div class="fila__persona"><span class="avatar">${esc(iniciales(c.nombre_completo))}</span>
            <div><strong>${esc(c.nombre_completo)}</strong><small>${esc(c.correo)}</small></div></div>
          <div class="fila__datos">${tagRol(c.rol)} ${tagCuenta(c.estado_cuenta)}
            ${c.suspendido_hasta ? `<span>hasta el ${esc(new Date(c.suspendido_hasta).toLocaleDateString("es-CL"))}</span>` : ""}
            <span>${c.advertencias} advertencia(s)</span><span>·</span><span>${c.reportes_recibidos} reporte(s)</span></div>
          ${c.estado_cuenta !== "activo" ? `<div class="fila__acciones"><button type="button" class="btn btn--ghost btn--sm" data-levantar="${c.id}" data-nombre="${esc(c.nombre_completo)}"><span class="material-symbols-rounded">lock_open</span> Levantar sanción</button></div>` : ""}
        </div>`).join("")}</div>`
      : vacio("search_off", "No hay cuentas que coincidan.");
  }

  function levantarSancion(id, nombre) {
    abrirFormulario({
      titulo: "Levantar sanción",
      descripcion: `${nombre} podrá volver a entrar y sus advertencias vuelven a cero. Los chats que se cancelaron no se reabren, pero se avisa a ambas personas.`,
      textoBoton: "Levantar sanción", campos: [],
      onEnviar: async () => {
        const r = await llamar(`/api/admin/cuentas/${id}/levantar-sancion`, "POST");
        if (!r.ok) return { ok: false, error: textoDeError(r) };
        mostrarAviso("Sanción levantada.");
        actualizarContadores();
        verCuentas(true);
        return { ok: true };
      },
    });
  }

  contenido.addEventListener("input", (e) => {
    if (e.target.id !== "buscar-cuentas") return;
    busquedaCuentas = e.target.value;
    clearTimeout(temporizadorBusqueda);
    temporizadorBusqueda = setTimeout(() => verCuentas(true), 350);
  });
  contenido.addEventListener("click", (e) => {
    const b = e.target.closest("[data-levantar]");
    if (b) levantarSancion(b.dataset.levantar, b.dataset.nombre);
  });

  /* =====================================================================
     RESUMEN
  ===================================================================== */
  async function verResumen() {
    contenido.innerHTML = cabecera("Resumen", "Cómo va la convivencia en la plataforma.") + `<p class="vacio-admin">Cargando…</p>`;
    const r = await actualizarContadores();
    if (seccion !== "resumen") return;
    if (!r) { contenido.innerHTML = cabecera("Resumen", "") + vacio("sync_problem", "No se pudo cargar el resumen."); return; }
    const m = (icono, titulo, valor, destino, alerta) => `
      <button type="button" class="metrica ${alerta && valor ? "metrica--alerta" : ""}" data-ir="${destino}">
        <small><span class="material-symbols-rounded">${icono}</span>${esc(titulo)}</small><strong>${valor}</strong></button>`;
    contenido.innerHTML = cabecera("Resumen", "Cómo va la convivencia en la plataforma.") + `
      <div class="metricas">
        ${m("flag", "Reportes pendientes", r.reportes_pendientes, "reportes", true)}
        ${m("smart_toy", "Automáticos pendientes", r.reportes_automaticos_pendientes, "reportes", true)}
        ${m("task_alt", "Resueltos en 30 días", r.reportes_resueltos_30d, "reportes", false)}
        ${m("block", "Cuentas baneadas", r.cuentas_baneadas, "cuentas", false)}
        ${m("schedule", "Cuentas en time-out", r.cuentas_suspendidas, "cuentas", false)}
        ${m("school", "Certificados por revisar", r.verificaciones_pendientes, "verificaciones", true)}
      </div>
      <div class="nota-info"><strong>Cómo funciona la moderación.</strong> Los mensajes con insultos, insinuaciones o fuera de tema
        se bloquean antes de llegar a la otra persona. Insultos e insinuaciones suman una advertencia durante 30 días; a la tercera
        la cuenta se banea sola y aparece aquí como un reporte automático. Las personas también pueden reportar una conversación
        desde el chat.</div>`;
  }

  contenido.addEventListener("click", (e) => {
    const m = e.target.closest("[data-ir]");
    if (m) irA(m.dataset.ir);
  });

  /* ---------- arranque y refresco ---------- */
  window.addEventListener("hashchange", () => {
    const destino = location.hash.slice(1);
    if (["reportes", "verificaciones", "cuentas", "resumen"].includes(destino) && destino !== seccion) irA(destino);
  });

  setInterval(async () => {
    if (document.hidden || document.querySelector("dialog.pm")) return;   // no molestar si hay un cuadro abierto
    await actualizarContadores();
    if (seccion === "reportes") verReportes(true);
  }, REFRESCO_MS);

  const inicial = location.hash.slice(1);
  actualizarContadores();
  irA(["reportes", "verificaciones", "cuentas", "resumen"].includes(inicial) ? inicial : "reportes");
})();
