/* =========================================================================
   PORTAL DEL ESTUDIANTE - lógica de la página (datos reales desde la API)
   1. Ayudas y catálogos
   2. Perfil y resumen
   3. Casos clínicos (solicitudes de pacientes) y postulación
   4. Clínicas por ramo
   5. Requerimientos clínicos (con su tutor)
   6. Postulaciones
   7. Acciones (un solo oyente para todos los botones)
   Requiere session.js, api.js, utils.js, formulario-modal.js y verificacion.js cargados antes.
   ========================================================================= */

/* ---------- 1. AYUDAS Y CATÁLOGOS ---------- */
let AREAS = [];            // [{clave, nombre}] desde /api/catalogos
let DIAS = [];
let requerimientos = [];   // los míos (se usan para vincular al postular)
let casos = [];
let postulaciones = [];
let ramos = [];
let filtroActual = "todos";  // pestaña activa de "Explorar pacientes" (clave de FILTROS)

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
const soloFecha = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("es-CL", { dateStyle: "medium" });

/* ---------- 2. PERFIL Y RESUMEN ---------- */
async function cargarPerfil() {
  const datos = await obtenerJson("/api/perfil");
  const e = datos.estudiante;
  if (!e) return;
  poner("perfil-ano", `${e.ano_carrera}° Año de Carrera`);
  const zona = e.comuna_atencion && e.comuna_atencion !== "Por definir" ? ` · Atiende en ${e.comuna_atencion}` : "";
  poner("perfil-universidad", `${e.universidad}${zona}`);
  const estado = e.estado_verificacion || "No verificado";
  poner("estado-verificacion", estado === "Activo" ? "Perfil verificado" : estado);
  document.getElementById("estado-verificacion").className = claseEstado(estado);
}

/* "Mostrar más / menos": muestra solo los primeros `limite` elementos y un botón para el resto. */
const LIMITE_TAGS_RAMOS = 4;
const LIMITE_CLINICAS = 3;
const LIMITE_LISTA = 3;    // casos, requerimientos y postulaciones
const expandido = {};      // clave de lista -> true si está expandida
let nombresRamos = [];

// Lista con "Mostrar más / menos" (conVerMas viene de utils.js).
const listaConVerMas = (clave, items, limite, fila) => conVerMas(clave, items, limite, fila, expandido[clave]);

const tagRamo = (n) => `<span class="chip-tag chip-tag--soft"><span class="dot"></span> ${esc(n)}</span>`;
const vacio = (texto) => `<p class="vacio">${texto}</p>`;

function pintarTagsRamos() {
  document.getElementById("tags-ramos").innerHTML = listaConVerMas("ramos", nombresRamos, LIMITE_TAGS_RAMOS, tagRamo);
}

function pintarClinicas() {
  document.getElementById("lista-clinicas").innerHTML = ramos.length
    ? listaConVerMas("clinicas", ramos, LIMITE_CLINICAS, tarjetaClinica)
    : `<p class="empty">Aún no agregas ramos. Usa "Agregar Ramo".</p>`;
}

function pintarCasos() {
  document.getElementById("lista-casos").innerHTML = casos.length
    ? listaConVerMas("casos", casos, LIMITE_LISTA, filaCaso)
    : `<p class="empty">No hay casos disponibles con ese filtro.</p>`;
}

function pintarRequerimientos() {
  document.getElementById("lista-requerimientos").innerHTML = requerimientos.length
    ? listaConVerMas("requerimientos", requerimientos, LIMITE_LISTA, filaRequerimiento)
    : vacio('Aún no declaras requerimientos. Usa "Declarar requerimiento" e indica tu profesor.');
}

function pintarPostulaciones() {
  document.getElementById("lista-postulaciones").innerHTML = postulaciones.length
    ? listaConVerMas("postulaciones", postulaciones, LIMITE_LISTA, filaPostulacion)
    : vacio("Aún no tienes postulaciones. Postula a un caso o espera solicitudes de pacientes.");
}

// Cada clave de "Mostrar más" sabe cómo volver a dibujar su lista.
const REPINTAR = {
  ramos: pintarTagsRamos, clinicas: pintarClinicas, casos: pintarCasos,
  requerimientos: pintarRequerimientos, postulaciones: pintarPostulaciones,
};

async function cargarResumen() {
  const r = await obtenerJson("/api/resumen");
  poner("stat-abiertos", r.requerimientos_abiertos);
  poner("stat-completados", r.requerimientos_completados);
  poner("stat-recibidas", r.postulaciones_recibidas);
  poner("stat-ramos", r.ramos.length);
  nombresRamos = r.ramos;
  pintarTagsRamos();
  const badge = document.getElementById("badge-notificaciones");
  badge.textContent = r.notificaciones;
  badge.hidden = !r.notificaciones;
}

/* ---------- 3. CASOS CLÍNICOS ---------- */
// El título es el comienzo de lo que escribió el paciente (cortado con «…»): se muestra el texto completo una sola vez.
function textoCaso(c) {
  const inicio = (c.titulo || "").replace(/(\.{3}|…)\s*$/, "").trim();
  return c.descripcion && c.descripcion.startsWith(inicio) ? c.descripcion : c.titulo;
}

function botonesCaso(c) {
  const estado = c.mi_postulacion_estado;
  if (estado === null || estado === undefined) {
    if (!estaVerificado()) {
      return `<button class="btn btn--soft" data-accion="verificar-perfil">
         <span class="material-symbols-rounded" style="color:inherit">lock</span> Verifica tu perfil para postular
       </button>`;
    }
    return `<button class="btn ${c.urgente ? "btn--primary" : "btn--soft"}" data-accion="postular" data-id="${c.id}">
         Postular a Caso <span class="material-symbols-rounded" style="color:inherit">arrow_forward</span>
       </button>`;
  }
  if (estado !== "Pendiente") {
    return `<button class="btn btn--soft" disabled>Postulación ${esc(estado.toLowerCase())}</button>`;
  }
  // Pendiente: si la envió el paciente decides tú; si la enviaste tú, puedes retirarla.
  if (c.mi_postulacion_puede_responder) {
    return `<span class="case-row__estado">El paciente te solicitó atención</span>
      <button class="btn btn--primary" data-accion="responder" data-respuesta="aceptar" data-id="${c.mi_postulacion_id}">Aceptar</button>
      <button class="btn btn--danger-soft" data-accion="responder" data-respuesta="rechazar" data-id="${c.mi_postulacion_id}">Rechazar</button>`;
  }
  return `<span class="case-row__estado">Postulación pendiente</span>
    <button class="btn btn--danger-soft" data-accion="cancelar-postulacion" data-id="${c.mi_postulacion_id}">Cancelar postulación</button>`;
}

function filaCaso(c) {
  return `
    <article class="card case-row${c.urgente ? " case-row--top" : ""}" data-id="${c.id}">
      <div class="case-row__main">
        <div class="case-row__head">
          <span class="case-row__badge${c.urgente ? " case-row__badge--top" : ""}">${c.urgente ? `<span class="material-symbols-rounded">bolt</span>Urgente` : esc(c.area_nombre)}</span>
          <span class="case-row__note case-row__note--muted">${esc(c.codigo)}</span>
        </div>
        <h3>${esc(textoCaso(c))}</h3>
        <div class="case-row__meta">
          <span><span class="material-symbols-rounded">person</span>${esc(c.paciente)}</span>
          <span><span class="material-symbols-rounded">location_on</span>${esc(c.comuna || "Comuna sin especificar")}${c.disponibilidad ? ` (${esc(c.disponibilidad)})` : ""}</span>
          <span class="area"><span class="material-symbols-rounded">bookmark</span>${esc(c.area_nombre)}</span>
        </div>
      </div>
      <div class="case-row__side">${botonesCaso(c)}</div>
    </article>`;
}

async function cargarCasos() {
  casos = await obtenerJson(`/api/casos${FILTROS[filtroActual]}`);
  pintarCasos();
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
        <span class="clinic__acciones">
          <button class="icon-btn" aria-label="Editar ramo" title="Editar ramo" data-accion="editar-ramo" data-id="${c.id}">
            <span class="material-symbols-rounded">edit</span>
          </button>
          <button class="icon-btn" aria-label="Quitar ramo" title="Quitar ramo" data-accion="borrar-ramo" data-id="${c.id}">
            <span class="material-symbols-rounded">delete</span>
          </button>
        </span>
      </div>
      <p class="hours"><span class="material-symbols-rounded">schedule</span>${esc(horario)}</p>
      <p><span class="material-symbols-rounded">${ICONO_AREA[c.area] || "bookmark"}</span>${esc(c.clinica || nombreArea(c.area))}</p>
      ${c.tutor ? `<p><span class="material-symbols-rounded">verified_user</span>Profesor: ${esc(c.tutor)}</p>` : ""}
      ${c.lugar ? `<p><span class="material-symbols-rounded">location_on</span>${esc(c.lugar)}</p>` : ""}
    </div>`;
}

async function cargarRamos() {
  ramos = await obtenerJson("/api/ramos");
  pintarClinicas();
}

function camposRamo(r = {}) {
  return [
    { nombre: "ramo", etiqueta: "Ramo", requerido: true, valor: r.ramo, placeholder: "Endodoncia I" },
    { nombre: "area", etiqueta: "Área clínica", tipo: "select", opciones: opcionesAreas(), valor: r.area || "otra" },
    { nombre: "tutor", etiqueta: "Profesor", valor: r.tutor, placeholder: "Prof. Ricardo" },
    { nombre: "dia_semana", etiqueta: "Día", tipo: "select", valor: r.dia_semana || "",
      opciones: [{ valor: "", texto: "Sin definir" }, ...DIAS.map((d) => ({ valor: d, texto: d }))] },
    { nombre: "hora_inicio", etiqueta: "Hora de inicio", tipo: "time", valor: r.hora_inicio },
    { nombre: "hora_fin", etiqueta: "Hora de término", tipo: "time", valor: r.hora_fin },
    { nombre: "clinica", etiqueta: "Clínica", valor: r.clinica, placeholder: "Clínica Endodoncia I" },
    { nombre: "lugar", etiqueta: "Lugar / box", valor: r.lugar, placeholder: "Pabellón Central · Box 08-B" },
  ];
}

function abrirNuevoRamo() {
  abrirFormulario({
    titulo: "Agregar ramo",
    descripcion: "Registra tu clínica semanal y el profesor a cargo.",
    textoBoton: "Agregar ramo",
    campos: camposRamo(),
    onEnviar: async (valores) => {
      const r = await apiJson("/api/ramos", "POST", valores);
      if (!r.ok) return { ok: false, error: textoDeError(r) };
      mostrarAviso("Ramo agregado.");
      await Promise.all([cargarRamos(), cargarResumen()]);
      return { ok: true };
    },
  });
}

function abrirEditarRamo(id) {
  const ramo = ramos.find((r) => r.id === id);
  if (!ramo) return;
  abrirFormulario({
    titulo: "Editar ramo",
    descripcion: "Cambia el horario, la clínica o el profesor.",
    textoBoton: "Guardar cambios",
    campos: camposRamo(ramo),
    onEnviar: async (valores) => {
      const r = await apiJson(`/api/ramos/${id}`, "PUT", valores);
      if (!r.ok) return { ok: false, error: textoDeError(r) };
      mostrarAviso("Ramo actualizado.");
      await cargarRamos();
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
            <span>Profesor: <strong>${esc(r.tutor)}</strong></span>
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
      ${r.estado === "Cancelado" ? `
      <div class="fila__acciones" style="margin-top:12px">
        <button class="icon-btn" aria-label="Eliminar requerimiento" title="Eliminar requerimiento" data-accion="eliminar-requerimiento" data-id="${r.id}">
          <span class="material-symbols-rounded">delete</span>
        </button>
      </div>` : ""}
      ${abierto ? `
      <div class="fila__acciones" style="margin-top:12px">
        <button class="btn btn--soft btn--sm" data-accion="avance" data-id="${r.id}">+1 realizado</button>
        <button class="btn btn--outline btn--sm" data-accion="editar-requerimiento" data-id="${r.id}">Editar</button>
        <button class="btn btn--danger-soft btn--sm" data-accion="cancelar-requerimiento" data-id="${r.id}">Cancelar</button>
      </div>` : ""}
    </div>`;
}

async function cargarRequerimientos() {
  requerimientos = await obtenerJson("/api/requerimientos");
  pintarRequerimientos();
}

function camposRequerimiento(r = {}) {
  return [
    { nombre: "tratamiento", etiqueta: "Tratamiento / procedimiento", requerido: true, valor: r.tratamiento, placeholder: "Endodoncia unirradicular" },
    { nombre: "area", etiqueta: "Área clínica", tipo: "select", opciones: opcionesAreas(), valor: r.area || "otra" },
    { nombre: "tutor", etiqueta: "Profesor", requerido: true, valor: r.tutor, placeholder: "Prof. Ricardo" },
    { nombre: "catedra", etiqueta: "Cátedra / asignatura", valor: r.catedra, placeholder: "Odontología Restauradora" },
    { nombre: "cantidad_requerida", etiqueta: "Cantidad requerida", tipo: "number", min: 1, max: 50, valor: r.cantidad_requerida || 1, requerido: true },
    { nombre: "plazo", etiqueta: "Plazo", tipo: "date", valor: r.plazo },
    { nombre: "detalle", etiqueta: "Detalle clínico", tipo: "textarea", valor: r.detalle, placeholder: "Piezas dentales, tipo de caso, indicaciones del profesor…" },
  ];
}

function abrirNuevoRequerimiento() {
  abrirFormulario({
    titulo: "Declarar requerimiento clínico",
    descripcion: "Indica qué procedimiento debes completar y con qué profesor.",
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

/* ---------- 6. POSTULACIONES ---------- */
function botonesPostulacion(p) {
  const b = [];
  if (p.puede_responder) {
    b.push(`<button class="btn btn--primary btn--sm" data-accion="responder" data-respuesta="aceptar" data-id="${p.id}">Aceptar</button>`);
    b.push(`<button class="btn btn--danger-soft btn--sm" data-accion="responder" data-respuesta="rechazar" data-id="${p.id}">Rechazar</button>`);
  } else if (p.estado === "Pendiente") {
    b.push(`<button class="btn btn--outline btn--sm" data-accion="cancelar-postulacion" data-id="${p.id}">Cancelar postulación</button>`);
  } else if (p.estado === "Aceptada") {
    b.push(`<button class="btn btn--outline btn--sm" data-accion="chatear" data-id="${p.id}"><span class="material-symbols-rounded">chat</span> Chatear</button>`);
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
            ${p.requerimiento ? `<span>•</span><span>Requerimiento: ${esc(p.requerimiento.tratamiento)} (profesor ${esc(p.requerimiento.tutor)})</span>` : ""}
          </div>
          ${p.mensaje ? `<p class="fila__texto">"${esc(p.mensaje)}"</p>` : ""}
        </div>
        <div class="fila__acciones">${botonesPostulacion(p)}</div>
      </div>
    </div>`;
}

async function cargarPostulaciones() {
  postulaciones = await obtenerJson("/api/postulaciones");
  pintarPostulaciones();
}

async function responder(id, accion) {
  const r = await apiJson(`/api/postulaciones/${id}/responder`, "POST", { accion });
  if (!r.ok) return mostrarAviso(textoDeError(r), true);
  mostrarAviso(accion === "aceptar" ? "Postulación aceptada." : "Postulación rechazada.");
  await recargarFlujo();
}

async function recargarFlujo() {
  await Promise.all([cargarCasos(), cargarPostulaciones(), cargarRequerimientos(), cargarResumen()]);
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
  "responder", "completar",
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
    case "eliminar-requerimiento":
      if (confirm("¿Eliminar este requerimiento cancelado? Dejará de aparecer en tu lista.")) accion(`/api/requerimientos/${id}/definitivo`, "DELETE", undefined, "Requerimiento eliminado.", () => Promise.all([cargarRequerimientos(), cargarResumen()]));
      return;
    case "ver-mas": {
      const clave = el.dataset.lista;
      expandido[clave] = !expandido[clave];
      return REPINTAR[clave]();
    }
    case "nuevo-ramo": return abrirNuevoRamo();
    case "editar-ramo": return abrirEditarRamo(id);
    case "borrar-ramo":
      if (confirm("¿Quitar este ramo?")) accion(`/api/ramos/${id}`, "DELETE", undefined, "Ramo eliminado.", () => Promise.all([cargarRamos(), cargarResumen()]));
      return;
    case "postular": return postular(id);
    case "responder": return responder(id, el.dataset.respuesta);
    case "cancelar-postulacion":
      if (confirm("¿Cancelar esta postulación?")) accion(`/api/postulaciones/${id}/cancelar`, "POST", undefined, "Postulación cancelada.");
      return;
    case "completar":
      if (confirm("¿Confirmas que el tratamiento ya se realizó? Se sumará a tu requerimiento.")) accion(`/api/postulaciones/${id}/completar`, "POST", undefined, "Tratamiento registrado como realizado.");
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
  const catalogos = await obtenerJson("/api/catalogos");
  AREAS = catalogos.areas;
  DIAS = catalogos.dias_semana;
  // la verificación primero: define si los botones de los casos están activos
  await cargarVerificacion(false).catch(() => mostrarAviso("No se pudo cargar tu estado de verificación.", true));
  // requerimientos después: se usan al postular a un caso
  await cargarRequerimientos();
  const tareas = [cargarPerfil, cargarResumen, cargarRamos, cargarCasos, cargarPostulaciones];
  const resultados = await Promise.allSettled(tareas.map((t) => t()));
  if (resultados.some((r) => r.status === "rejected")) {
    mostrarAviso("Algunos datos no se pudieron cargar. Recarga la página.", true);
  }
}

iniciar().catch(() => mostrarAviso("No se pudo conectar con el servidor.", true));
