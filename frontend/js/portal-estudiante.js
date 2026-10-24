/* =========================================================================
   PORTAL DEL ESTUDIANTE - lógica de la página (datos reales desde la API)
   1. Ayudas y catálogos
   2. Perfil y resumen
   3. Casos clínicos (solicitudes de pacientes) y postulación
   4. Clínicas por ramo
   5. Requerimientos clínicos (con su tutor)
   6. Postulaciones y citas
   7. Acciones (un solo oyente para todos los botones)
   Requiere session.js, api.js, utils.js y formulario-modal.js cargados antes.
   ========================================================================= */

/* ---------- 1. AYUDAS Y CATÁLOGOS ---------- */
let AREAS = [];            // [{clave, nombre}] desde /api/catalogos
let DIAS = [];
let requerimientos = [];   // los míos (se usan para vincular al postular)
let casos = [];
let postulaciones = [];
let citas = [];
let ramos = [];
let filtroActual = "todos";

const ICONO_AREA = {
  prevencion: "dentistry", operatoria: "dentistry", endodoncia: "bookmark", periodoncia: "biotech",
  rehabilitacion: "dentistry", cirugia: "healing", diagnostico: "biotech", otra: "bookmark",
};

const FILTROS = {
  todos: "",
  urgencia: "?urgente=true",
  operatoria: "?area=operatoria",
  endodoncia: "?area=endodoncia",
  periodoncia: "?area=periodoncia",
};

const nombreArea = (clave) => (AREAS.find((a) => a.clave === clave) || {}).nombre || clave;
const opcionesAreas = () => AREAS.map((a) => ({ valor: a.clave, texto: a.nombre }));
const fechaHora = (iso) => new Date(iso).toLocaleString("es-CL", { dateStyle: "medium", timeStyle: "short" });
const soloFecha = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("es-CL", { dateStyle: "medium" });
const poner = (id, texto) => { document.getElementById(id).textContent = texto; };

function claseEstado(estado) {
  if (["Aceptada", "Completado", "Completada", "Realizada", "Activo"].includes(estado)) return "chip-tag chip-tag--green";
  if (["Rechazada", "Rechazado", "Cancelada", "Cancelado"].includes(estado)) return "chip-tag chip-tag--danger";
  return "chip-tag chip-tag--warn";
}

async function cargar(ruta) {
  const r = await apiJson(ruta);
  if (!r.ok) throw new Error(textoDeError(r));
  return r.data;
}

/* ---------- 2. PERFIL Y RESUMEN ---------- */
async function cargarPerfil() {
  const datos = await cargar("/api/perfil");
  const e = datos.estudiante;
  if (!e) return;
  poner("perfil-ano", `${e.ano_carrera}° Año de Carrera`);
  const zona = e.comuna_atencion && e.comuna_atencion !== "Por definir" ? ` · Atiende en ${e.comuna_atencion}` : "";
  poner("perfil-universidad", `${e.universidad}${zona}`);
  const estado = e.estado_verificacion || "No verificado";
  poner("estado-verificacion", estado === "Activo" ? "Perfil verificado" : estado);
  document.getElementById("estado-verificacion").className = claseEstado(estado);
}

async function cargarResumen() {
  const r = await cargar("/api/resumen");
  poner("stat-abiertos", r.requerimientos_abiertos);
  poner("stat-completados", r.requerimientos_completados);
  poner("stat-recibidas", r.postulaciones_recibidas);
  poner("stat-citas", r.citas_proximas);
  poner("stat-ramos", r.ramos.length);
  document.getElementById("tags-ramos").innerHTML = r.ramos
    .map((n) => `<span class="chip-tag chip-tag--soft"><span class="dot"></span> ${esc(n)}</span>`)
    .join("");
  const badge = document.getElementById("badge-notificaciones");
  badge.textContent = r.notificaciones;
  badge.hidden = !r.notificaciones;
}

/* ---------- 3. CASOS CLÍNICOS ---------- */
function filaCaso(c) {
  const yaPostule = c.mi_postulacion_estado !== null && c.mi_postulacion_estado !== undefined;
  const boton = yaPostule
    ? `<button class="btn btn--soft" disabled>Postulación ${esc(c.mi_postulacion_estado.toLowerCase())}</button>`
    : !estaVerificado()
    ? `<button class="btn btn--soft" data-accion="verificar-perfil">
         <span class="material-symbols-rounded" style="color:inherit">lock</span> Verifica tu perfil para postular
       </button>`
    : `<button class="btn ${c.urgente ? "btn--primary" : "btn--soft"}" data-accion="postular" data-id="${c.id}">
         Postular a Caso <span class="material-symbols-rounded" style="color:inherit">arrow_forward</span>
       </button>`;
  return `
    <article class="card case-row${c.urgente ? " case-row--top" : ""}" data-id="${c.id}">
      <div class="case-row__main">
        <div class="case-row__head">
          <span class="case-row__badge${c.urgente ? " case-row__badge--top" : ""}">${c.urgente ? `<span class="material-symbols-rounded">bolt</span>Urgente` : esc(c.area_nombre)}</span>
          <span class="case-row__note case-row__note--muted">${esc(c.codigo)}</span>
        </div>
        <h3>${esc(c.titulo)}</h3>
        ${c.descripcion && c.descripcion !== c.titulo ? `<p class="case-row__desc">${esc(c.descripcion)}</p>` : ""}
        <div class="case-row__meta">
          <span><span class="material-symbols-rounded">person</span>${esc(c.paciente)}</span>
          <span><span class="material-symbols-rounded">location_on</span>${esc(c.comuna || "Comuna sin especificar")}${c.disponibilidad ? ` (${esc(c.disponibilidad)})` : ""}</span>
          <span class="area"><span class="material-symbols-rounded">bookmark</span>${esc(c.area_nombre)}</span>
        </div>
      </div>
      <div class="case-row__side">${boton}</div>
    </article>`;
}

async function cargarCasos() {
  casos = await cargar(`/api/casos${FILTROS[filtroActual]}`);
  document.getElementById("lista-casos").innerHTML = casos.length
    ? casos.map(filaCaso).join("")
    : `<p class="empty">No hay casos disponibles con ese filtro.</p>`;
}

async function postular(solicitudId) {
  const caso = casos.find((c) => c.id === solicitudId);
  // Si tienes un requerimiento abierto de la misma área, se vincula automáticamente.
  const req = requerimientos.find((r) => r.estado === "Abierto" && caso && r.area === caso.area);
  const r = await apiJson("/api/postulaciones", "POST", {
    solicitud_id: solicitudId,
    requerimiento_id: req ? req.id : undefined,
  });
  if (!r.ok) return mostrarAviso(textoDeError(r), true);
  mostrarAviso(req ? `Postulación enviada, vinculada a "${req.tratamiento}".` : "Postulación enviada.");
  await Promise.all([cargarCasos(), cargarPostulaciones(), cargarResumen()]);
}

/* ---------- 4. CLÍNICAS POR RAMO ---------- */
function tarjetaClinica(c) {
  const horario = c.hora_inicio && c.hora_fin ? `${c.hora_inicio} a ${c.hora_fin} hrs` : "Horario por definir";
  return `
    <div class="clinic">
      <div class="clinic__head">
        <span><span class="clinic__day">${esc(c.dia_semana || "Sin día")}</span> ${esc(c.ramo)}</span>
        <button class="icon-btn" aria-label="Quitar ramo" title="Quitar ramo" data-accion="borrar-ramo" data-id="${c.id}">
          <span class="material-symbols-rounded">delete</span>
        </button>
      </div>
      <p class="hours"><span class="material-symbols-rounded">schedule</span>${esc(horario)}</p>
      <p><span class="material-symbols-rounded">${ICONO_AREA[c.area] || "bookmark"}</span>${esc(c.clinica || nombreArea(c.area))}</p>
      ${c.tutor ? `<p><span class="material-symbols-rounded">verified_user</span>Tutor: ${esc(c.tutor)}</p>` : ""}
      ${c.lugar ? `<p><span class="material-symbols-rounded">location_on</span>${esc(c.lugar)}</p>` : ""}
    </div>`;
}

async function cargarRamos() {
  ramos = await cargar("/api/ramos");
  document.getElementById("lista-clinicas").innerHTML = ramos.length
    ? ramos.map(tarjetaClinica).join("")
    : `<p class="empty">Aún no agregas ramos. Usa "Agregar Ramo / Turno".</p>`;
}

function abrirNuevoRamo() {
  abrirFormulario({
    titulo: "Agregar ramo / turno",
    descripcion: "Registra tu clínica semanal y el tutor a cargo.",
    textoBoton: "Agregar ramo",
    campos: [
      { nombre: "ramo", etiqueta: "Ramo", requerido: true, placeholder: "Endodoncia I" },
      { nombre: "area", etiqueta: "Área clínica", tipo: "select", opciones: opcionesAreas(), valor: "otra" },
      { nombre: "tutor", etiqueta: "Tutor / profesor", placeholder: "Prof. Ricardo" },
      { nombre: "dia_semana", etiqueta: "Día", tipo: "select",
        opciones: [{ valor: "", texto: "Sin definir" }, ...DIAS.map((d) => ({ valor: d, texto: d }))] },
      { nombre: "hora_inicio", etiqueta: "Hora de inicio", tipo: "time" },
      { nombre: "hora_fin", etiqueta: "Hora de término", tipo: "time" },
      { nombre: "clinica", etiqueta: "Clínica", placeholder: "Clínica Endodoncia I" },
      { nombre: "lugar", etiqueta: "Lugar / box", placeholder: "Pabellón Central · Box 08-B" },
    ],
    onEnviar: async (valores) => {
      const r = await apiJson("/api/ramos", "POST", valores);
      if (!r.ok) return { ok: false, error: textoDeError(r) };
      mostrarAviso("Ramo agregado.");
      await Promise.all([cargarRamos(), cargarResumen()]);
      return { ok: true };
    },
  });
}

/* ---------- 5. REQUERIMIENTOS CLÍNICOS ---------- */
function filaRequerimiento(r) {
  const pct = Math.round((r.cantidad_completada / r.cantidad_requerida) * 100);
  const abierto = r.estado === "Abierto";
  return `
    <div class="fila">
      <div class="fila__top">
        <div>
          <span class="fila__titulo">${esc(r.tratamiento)}</span>
          <span class="${claseEstado(r.estado)}">${esc(r.estado)}</span>
          <div class="fila__meta">
            <span>${esc(r.area_nombre)}</span><span>•</span>
            <span>Tutor: <strong>${esc(r.tutor)}</strong></span>
            ${r.catedra ? `<span>•</span><span>${esc(r.catedra)}</span>` : ""}
            ${r.plazo ? `<span>•</span><span>Plazo: ${esc(soloFecha(r.plazo))}</span>` : ""}
            ${r.postulaciones_pendientes ? `<span>•</span><span><strong>${r.postulaciones_pendientes}</strong> postulación(es) pendiente(s)</span>` : ""}
          </div>
          ${r.detalle ? `<p class="fila__texto">${esc(r.detalle)}</p>` : ""}
        </div>
        <div class="avance">
          <div class="barra"><span style="width:${pct}%"></span></div>
          ${r.cantidad_completada} / ${r.cantidad_requerida}
        </div>
      </div>
      ${abierto ? `
      <div class="fila__acciones" style="margin-top:12px">
        <button class="btn btn--soft btn--sm" data-accion="avance" data-id="${r.id}">+1 realizado</button>
        <button class="btn btn--outline btn--sm" data-accion="editar-requerimiento" data-id="${r.id}">Editar</button>
        <button class="btn btn--danger-soft btn--sm" data-accion="cancelar-requerimiento" data-id="${r.id}">Cancelar</button>
      </div>` : ""}
    </div>`;
}

async function cargarRequerimientos() {
  requerimientos = await cargar("/api/requerimientos");
  document.getElementById("lista-requerimientos").innerHTML = requerimientos.length
    ? requerimientos.map(filaRequerimiento).join("")
    : `<p class="vacio">Aún no declaras requerimientos. Usa "Declarar requerimiento" e indica tu tutor.</p>`;
}

function camposRequerimiento(r = {}) {
  return [
    { nombre: "tratamiento", etiqueta: "Tratamiento / procedimiento", requerido: true, valor: r.tratamiento, placeholder: "Endodoncia unirradicular" },
    { nombre: "area", etiqueta: "Área clínica", tipo: "select", opciones: opcionesAreas(), valor: r.area || "otra" },
    { nombre: "tutor", etiqueta: "Tutor / profesor", requerido: true, valor: r.tutor, placeholder: "Prof. Ricardo" },
    { nombre: "catedra", etiqueta: "Cátedra / asignatura", valor: r.catedra, placeholder: "Odontología Restauradora" },
    { nombre: "cantidad_requerida", etiqueta: "Cantidad requerida", tipo: "number", min: 1, max: 50, valor: r.cantidad_requerida || 1, requerido: true },
    { nombre: "plazo", etiqueta: "Plazo", tipo: "date", valor: r.plazo },
    { nombre: "detalle", etiqueta: "Detalle clínico", tipo: "textarea", valor: r.detalle, placeholder: "Piezas dentales, tipo de caso, indicaciones del tutor…" },
  ];
}

function abrirNuevoRequerimiento() {
  abrirFormulario({
    titulo: "Declarar requerimiento clínico",
    descripcion: "Indica qué procedimiento debes completar y con qué tutor.",
    textoBoton: "Declarar requerimiento",
    campos: camposRequerimiento(),
    onEnviar: async (valores) => {
      const r = await apiJson("/api/requerimientos", "POST", valores);
      if (!r.ok) return { ok: false, error: textoDeError(r) };
      mostrarAviso("Requerimiento declarado.");
      await Promise.all([cargarRequerimientos(), cargarResumen()]);
      return { ok: true };
    },
  });
}

function abrirEditarRequerimiento(id) {
  const req = requerimientos.find((r) => r.id === id);
  if (!req) return;
  abrirFormulario({
    titulo: "Editar requerimiento",
    textoBoton: "Guardar cambios",
    campos: camposRequerimiento(req),
    onEnviar: async (valores) => {
      const r = await apiJson(`/api/requerimientos/${id}`, "PATCH", valores);
      if (!r.ok) return { ok: false, error: textoDeError(r) };
      mostrarAviso("Requerimiento actualizado.");
      await Promise.all([cargarRequerimientos(), cargarResumen()]);
      return { ok: true };
    },
  });
}

/* ---------- 6. POSTULACIONES Y CITAS ---------- */
function botonesPostulacion(p) {
  const b = [];
  if (p.puede_responder) {
    b.push(`<button class="btn btn--primary btn--sm" data-accion="responder" data-respuesta="aceptar" data-id="${p.id}">Aceptar</button>`);
    b.push(`<button class="btn btn--danger-soft btn--sm" data-accion="responder" data-respuesta="rechazar" data-id="${p.id}">Rechazar</button>`);
  } else if (p.estado === "Pendiente") {
    b.push(`<button class="btn btn--outline btn--sm" data-accion="cancelar-postulacion" data-id="${p.id}">Cancelar postulación</button>`);
  } else if (p.estado === "Aceptada") {
    b.push(`<button class="btn btn--primary btn--sm" data-accion="agendar" data-id="${p.id}">Agendar cita</button>`);
    if (p.solicitud.estado !== "Completada") {
      b.push(`<button class="btn btn--soft btn--sm" data-accion="completar" data-id="${p.id}">Tratamiento realizado</button>`);
      b.push(`<button class="btn btn--danger-soft btn--sm" data-accion="cancelar-postulacion" data-id="${p.id}">Cancelar</button>`);
    }
  }
  return b.join("");
}

function filaPostulacion(p) {
  const origen = p.iniciada_por === "estudiante" ? "Postulaste tú" : "Te solicitó el paciente";
  return `
    <div class="fila">
      <div class="fila__top">
        <div>
          <span class="fila__titulo">${esc(p.solicitud.titulo)}</span>
          <span class="${claseEstado(p.estado)}">${esc(p.estado)}</span>
          <div class="fila__meta">
            <span><strong>${esc(p.solicitud.codigo)}</strong></span><span>•</span>
            <span>Paciente: ${esc(p.paciente.nombre)}</span><span>•</span>
            <span>${esc(origen)}</span>
            ${p.requerimiento ? `<span>•</span><span>Requerimiento: ${esc(p.requerimiento.tratamiento)} (tutor ${esc(p.requerimiento.tutor)})</span>` : ""}
          </div>
          ${p.mensaje ? `<p class="fila__texto">"${esc(p.mensaje)}"</p>` : ""}
        </div>
        <div class="fila__acciones">${botonesPostulacion(p)}</div>
      </div>
    </div>`;
}

async function cargarPostulaciones() {
  postulaciones = await cargar("/api/postulaciones");
  document.getElementById("lista-postulaciones").innerHTML = postulaciones.length
    ? postulaciones.map(filaPostulacion).join("")
    : `<p class="vacio">Aún no tienes postulaciones. Postula a un caso o espera solicitudes de pacientes.</p>`;
}

async function responder(id, accion) {
  const r = await apiJson(`/api/postulaciones/${id}/responder`, "POST", { accion });
  if (!r.ok) return mostrarAviso(textoDeError(r), true);
  mostrarAviso(accion === "aceptar" ? "Postulación aceptada." : "Postulación rechazada.");
  await recargarFlujo();
}

async function recargarFlujo() {
  await Promise.all([cargarCasos(), cargarPostulaciones(), cargarCitas(), cargarRequerimientos(), cargarResumen()]);
}

function filaCita(c) {
  const abierta = c.estado === "Agendada";
  return `
    <div class="fila">
      <div class="fila__top">
        <div>
          <span class="fila__titulo">${esc(fechaHora(c.fecha_hora))}</span>
          <span class="${claseEstado(c.estado)}">${esc(c.estado)}</span>
          <div class="fila__meta">
            <span><strong>${esc(c.solicitud_codigo)}</strong> ${esc(c.titulo)}</span><span>•</span>
            <span>Paciente: ${esc(c.paciente.nombre)}</span>
            ${c.lugar ? `<span>•</span><span>${esc(c.lugar)}</span>` : ""}
          </div>
          ${c.notas ? `<p class="fila__texto">${esc(c.notas)}</p>` : ""}
        </div>
        ${abierta ? `<div class="fila__acciones">
          <button class="btn btn--outline btn--sm" data-accion="cita-editar" data-id="${c.id}">Reprogramar</button>
          <button class="btn btn--danger-soft btn--sm" data-accion="cita-cancelar" data-id="${c.id}">Cancelar</button>
        </div>` : ""}
      </div>
    </div>`;
}

async function cargarCitas() {
  citas = await cargar("/api/citas");
  document.getElementById("lista-citas").innerHTML = citas.length
    ? citas.map(filaCita).join("")
    : `<p class="vacio">No tienes citas agendadas. Agenda una desde una postulación aceptada.</p>`;
}

function abrirAgendar(postulacionId) {
  abrirFormulario({
    titulo: "Agendar cita",
    textoBoton: "Agendar",
    campos: [
      { nombre: "fecha_hora", etiqueta: "Fecha y hora", tipo: "datetime-local", requerido: true },
      { nombre: "lugar", etiqueta: "Lugar / box", placeholder: "Clínica Norte · Box 8-B" },
      { nombre: "notas", etiqueta: "Notas para el paciente", tipo: "textarea", placeholder: "Traer radiografías, venir en ayunas…" },
    ],
    onEnviar: async (valores) => {
      const r = await apiJson("/api/citas", "POST", { postulacion_id: postulacionId, ...valores });
      if (!r.ok) return { ok: false, error: textoDeError(r) };
      mostrarAviso("Cita agendada.");
      await Promise.all([cargarCitas(), cargarResumen()]);
      return { ok: true };
    },
  });
}

function abrirReprogramar(citaId) {
  const cita = citas.find((c) => c.id === citaId);
  if (!cita) return;
  abrirFormulario({
    titulo: "Reprogramar cita",
    textoBoton: "Guardar",
    campos: [
      { nombre: "fecha_hora", etiqueta: "Fecha y hora", tipo: "datetime-local", valor: cita.fecha_hora.slice(0, 16), requerido: true },
      { nombre: "lugar", etiqueta: "Lugar / box", valor: cita.lugar },
      { nombre: "notas", etiqueta: "Notas", tipo: "textarea", valor: cita.notas },
    ],
    onEnviar: async (valores) => {
      const r = await apiJson(`/api/citas/${citaId}`, "PATCH", valores);
      if (!r.ok) return { ok: false, error: textoDeError(r) };
      mostrarAviso("Cita actualizada.");
      await cargarCitas();
      return { ok: true };
    },
  });
}

/* ---------- 7. ACCIONES ---------- */
// Una acción sencilla: llama a la API, avisa y recarga lo necesario.
async function accion(ruta, metodo, cuerpo, mensaje, recarga = recargarFlujo) {
  const r = await apiJson(ruta, metodo, cuerpo);
  if (!r.ok) return mostrarAviso(textoDeError(r), true);
  mostrarAviso(mensaje);
  await recarga();
}

// Acciones que exigen perfil verificado (el backend también lo exige: esto solo lo explica).
const ACCIONES_PROTEGIDAS = [
  "nuevo-requerimiento", "editar-requerimiento", "avance", "postular",
  "responder", "agendar", "completar", "cita-editar",
];

document.addEventListener("click", (evento) => {
  const el = evento.target.closest("[data-accion]");
  if (!el) return;
  const id = Number(el.dataset.id);
  if (ACCIONES_PROTEGIDAS.includes(el.dataset.accion) && !estaVerificado()) return pedirVerificacion();
  switch (el.dataset.accion) {
    case "nuevo-requerimiento": return abrirNuevoRequerimiento();
    case "editar-requerimiento": return abrirEditarRequerimiento(id);
    case "avance": return accion(`/api/requerimientos/${id}/avance`, "POST", {}, "Avance registrado.", () => Promise.all([cargarRequerimientos(), cargarResumen()]));
    case "cancelar-requerimiento":
      if (confirm("¿Cancelar este requerimiento?")) accion(`/api/requerimientos/${id}`, "DELETE", undefined, "Requerimiento cancelado.", () => Promise.all([cargarRequerimientos(), cargarResumen()]));
      return;
    case "nuevo-ramo": return abrirNuevoRamo();
    case "borrar-ramo":
      if (confirm("¿Quitar este ramo?")) accion(`/api/ramos/${id}`, "DELETE", undefined, "Ramo eliminado.", () => Promise.all([cargarRamos(), cargarResumen()]));
      return;
    case "postular": return postular(id);
    case "responder": return responder(id, el.dataset.respuesta);
    case "cancelar-postulacion":
      if (confirm("¿Cancelar esta postulación?")) accion(`/api/postulaciones/${id}/cancelar`, "POST", undefined, "Postulación cancelada.");
      return;
    case "agendar": return abrirAgendar(id);
    case "completar":
      if (confirm("¿Confirmas que el tratamiento ya se realizó? Se sumará a tu requerimiento.")) accion(`/api/postulaciones/${id}/completar`, "POST", undefined, "Tratamiento registrado como realizado.");
      return;
    case "cita-editar": return abrirReprogramar(id);
    case "cita-cancelar":
      if (confirm("¿Cancelar esta cita?")) accion(`/api/citas/${id}`, "PATCH", { estado: "Cancelada" }, "Cita cancelada.", () => Promise.all([cargarCitas(), cargarResumen()]));
      return;
  }
});

document.getElementById("tabs").addEventListener("click", async (evento) => {
  const tab = evento.target.closest(".tab");
  if (!tab) return;
  document.querySelectorAll("#tabs .tab").forEach((t) => t.classList.toggle("tab--active", t === tab));
  filtroActual = tab.dataset.filtro;
  try { await cargarCasos(); } catch (e) { mostrarAviso(e.message, true); }
});

document.addEventListener("perfil-actualizado", () => cargarPerfil().catch(() => {}));

// Al cambiar la verificación se refrescan el perfil, la campana y los botones de los casos.
document.addEventListener("verificacion-actualizada", () => {
  cargarPerfil().catch(() => {});
  cargarResumen().catch(() => {});
  cargarCasos().catch(() => {});
});

/* ---------- INICIO ---------- */
async function iniciar() {
  const catalogos = await cargar("/api/catalogos");
  AREAS = catalogos.areas;
  DIAS = catalogos.dias_semana;
  // la verificación primero: define si los botones de los casos están activos
  await cargarVerificacion(false).catch(() => mostrarAviso("No se pudo cargar tu estado de verificación.", true));
  // requerimientos después: se usan al postular a un caso
  await cargarRequerimientos();
  const tareas = [cargarPerfil, cargarResumen, cargarRamos, cargarCasos, cargarPostulaciones, cargarCitas];
  const resultados = await Promise.allSettled(tareas.map((t) => t()));
  if (resultados.some((r) => r.status === "rejected")) {
    mostrarAviso("Algunos datos no se pudieron cargar. Recarga la página.", true);
  }
}

iniciar().catch(() => mostrarAviso("No se pudo conectar con el servidor.", true));
