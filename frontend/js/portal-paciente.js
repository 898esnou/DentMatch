/* =========================================================================
   PORTAL DEL PACIENTE - lógica de la página (datos reales desde la API)
   1. Ayudas y catálogos
   2. Perfil y resumen
   3. Publicar una solicitud (buscador)
   4. Estudiantes disponibles y "Solicitar atención"
   5. Mis solicitudes con sus candidatos (postulaciones)
   6. Mis citas
   7. Acciones (un solo oyente para todos los botones)
   Requiere session.js, api.js, utils.js y formulario-modal.js cargados antes.
   ========================================================================= */

/* ---------- 1. AYUDAS Y CATÁLOGOS ---------- */
let AREAS = [];
let solicitudes = [];
let postulaciones = [];
let estudiantes = [];
let filtroActual = "todos";
const abiertas = new Set(); // ids de solicitudes con sus candidatos desplegados

const nombreArea = (clave) => (AREAS.find((a) => a.clave === clave) || {}).nombre || clave;
const poner = (id, texto) => { document.getElementById(id).textContent = texto; };
const fechaHora = (iso) => new Date(iso).toLocaleString("es-CL", { dateStyle: "medium", timeStyle: "short" });

function hace(iso) {
  const dias = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (dias <= 0) return "Creada hoy";
  return dias === 1 ? "Creada hace 1 día" : `Creada hace ${dias} días`;
}

function claseEstado(estado) {
  if (["Aceptada", "Asignada", "Completada", "Realizada"].includes(estado)) return "chip-tag chip-tag--green";
  if (["Rechazada", "Cancelada"].includes(estado)) return "chip-tag chip-tag--danger";
  return "chip-tag chip-tag--warn";
}

async function cargar(ruta) {
  const r = await apiJson(ruta);
  if (!r.ok) throw new Error(textoDeError(r));
  return r.data;
}

const solicitudesAbiertas = () => solicitudes.filter((s) => ["Abierta", "En Revisión"].includes(s.estado));
const solicitudActiva = () => solicitudes.find((s) => String(s.id) === document.getElementById("solicitud-activa").value);

/* ---------- 2. PERFIL Y RESUMEN ---------- */
async function cargarPerfil() {
  const datos = await cargar("/api/perfil");
  const comuna = datos.paciente && datos.paciente.comuna;
  poner("perfil-comuna", comuna || "sin definir");
  poner("zona-activa", comuna || 'define tu comuna en "Editar perfil"');
}

async function cargarResumen() {
  const r = await cargar("/api/resumen");
  poner("stat-activas", r.solicitudes_activas);
  poner("stat-completados", r.tratamientos_completados);
  poner("stat-por-responder", r.notificaciones);
  poner("stat-citas", r.citas_proximas);
  const badge = document.getElementById("badge-notificaciones");
  badge.textContent = r.notificaciones;
  badge.hidden = !r.notificaciones;
}

/* ---------- 3. PUBLICAR UNA SOLICITUD ---------- */
function llenarAreas() {
  document.getElementById("area").innerHTML = AREAS
    .map((a) => `<option value="${esc(a.clave)}"${a.clave === "diagnostico" ? " selected" : ""}>${esc(a.nombre)}</option>`)
    .join("");
}

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.getElementById("consulta").value = chip.dataset.consulta;
    if (chip.dataset.area) document.getElementById("area").value = chip.dataset.area;
    document.getElementById("urgente").checked = chip.dataset.urgente === "1";
  });
});

document.getElementById("search-form").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const texto = document.getElementById("consulta").value.trim();
  if (texto.length < 10) return mostrarAviso("Cuéntanos un poco más (mínimo 10 caracteres).", true);

  const distancia = document.getElementById("distancia").value;
  const boton = document.getElementById("boton-publicar");
  boton.disabled = true;
  try {
    const r = await apiJson("/api/solicitudes", "POST", {
      titulo: texto.length > 60 ? `${texto.slice(0, 57)}…` : texto,
      descripcion: texto,
      area: document.getElementById("area").value,
      urgente: document.getElementById("urgente").checked,
      distancia_max_km: distancia ? Number(distancia) : undefined,
    });
    if (!r.ok) return mostrarAviso(textoDeError(r), true);
    mostrarAviso(`Solicitud ${r.data.codigo} publicada.`);
    document.getElementById("search-form").reset();
    document.getElementById("area").value = "diagnostico";
    await recargarTodo(r.data.id);
    document.getElementById("resultados").scrollIntoView({ behavior: "smooth", block: "start" });
  } finally {
    boton.disabled = false;
  }
});

/* ---------- 4. ESTUDIANTES DISPONIBLES ---------- */
function llenarSelectorSolicitud(seleccionarId) {
  const select = document.getElementById("solicitud-activa");
  const actual = seleccionarId ? String(seleccionarId) : select.value;
  const abiertas_ = solicitudesAbiertas();
  select.innerHTML = abiertas_.length
    ? abiertas_.map((s) => `<option value="${s.id}">${esc(s.codigo)} · ${esc(s.titulo)}</option>`).join("")
    : `<option value="">Crea una solicitud para poder pedir atención</option>`;
  if (abiertas_.some((s) => String(s.id) === actual)) select.value = actual;
}

function tarjetaEstudiante(e) {
  const verificado = e.estado_verificacion === "Activo";
  const necesidades = e.requerimientos_abiertos.length
    ? "Busca pacientes para: " + e.requerimientos_abiertos.map((r) => `${r.tratamiento} (${r.restantes} por realizar)`).join(", ")
    : "Aún no ha publicado requerimientos clínicos.";
  const estado = e.mi_postulacion_estado;
  const boton = estado
    ? `<button class="btn btn--soft" disabled>Solicitud ${esc(estado.toLowerCase())}</button>`
    : `<button class="btn btn--green" data-accion="solicitar" data-id="${e.id}">
         Solicitar atención <span class="material-symbols-rounded" style="color:inherit">arrow_forward</span>
       </button>`;
  return `
    <article class="card cand" data-id="${e.id}">
      <div class="cand__side">
        <div class="cand__photo">
          <span class="avatar">${esc(e.nombre.split(" ").slice(0, 2).map((p) => p[0]).join("").toUpperCase())}</span>
          <span class="cand__year">${esc(e.ano_carrera)}° Año</span>
        </div>
        <strong class="cand__name">${esc(e.nombre)}</strong>
        <span class="cand__uni">${esc(e.universidad)}</span>
        <span class="${verificado ? "chip-tag chip-tag--green" : "chip-tag chip-tag--warn"} cand__match">
          <span class="material-symbols-rounded">verified</span> ${verificado ? "Alumno verificado" : "En verificación"}
        </span>
      </div>
      <div class="cand__body">
        <div class="cand__tags">
          <span class="chip-tag"><span class="material-symbols-rounded">bookmark</span> ${e.ramos.length ? `Ramos: ${esc(e.ramos.join(", "))}` : "Sin ramos registrados"}</span>
          <span class="chip-tag chip-tag--soft"><span class="material-symbols-rounded">location_on</span> ${esc(e.comuna_atencion)}</span>
        </div>
        <p class="cand__desc">${esc(necesidades)}</p>
        <div class="cand__avail"><span class="material-symbols-rounded">calendar_month</span><strong>${esc(e.disponibilidad || "Disponibilidad por definir")}</strong></div>
        <div class="cand__foot">
          <span><span class="material-symbols-rounded">verified_user</span> ${e.tutores.length ? `Supervisado por ${esc(e.tutores.join(", "))}` : "Tutor por definir"}</span>
          ${boton}
        </div>
      </div>
    </article>`;
}

async function cargarEstudiantes() {
  const params = new URLSearchParams();
  const activa = solicitudActiva();
  if (activa) params.set("solicitud_id", activa.id);
  if (filtroActual === "manana" || filtroActual === "tarde") params.set("turno", filtroActual);
  if (filtroActual === "verificados") params.set("solo_verificados", "true");
  if (filtroActual === "coincidentes" && activa) params.set("area", activa.area);

  estudiantes = await cargar(`/api/estudiantes?${params}`);
  const aviso = filtroActual === "coincidentes" && !activa
    ? `<p class="empty">Crea una solicitud para ver estudiantes de tu tipo de tratamiento.</p>`
    : `<p class="empty">No hay estudiantes disponibles con ese filtro.</p>`;
  document.getElementById("lista-estudiantes").innerHTML = estudiantes.length
    ? estudiantes.map(tarjetaEstudiante).join("")
    : aviso;
  const n = estudiantes.length;
  poner("contador", `${n} Estudiante${n === 1 ? "" : "s"}`);
}

async function solicitar(estudianteId) {
  const activa = solicitudActiva();
  if (!activa) {
    mostrarAviso("Primero publica una solicitud para poder pedir atención.", true);
    document.getElementById("buscador").scrollIntoView({ behavior: "smooth" });
    return;
  }
  const est = estudiantes.find((e) => e.id === estudianteId);
  // Si el estudiante tiene un requerimiento abierto de tu misma área, se vincula automáticamente.
  const req = est && est.requerimientos_abiertos.find((r) => r.area === activa.area);
  const r = await apiJson("/api/postulaciones", "POST", {
    solicitud_id: activa.id,
    estudiante_id: estudianteId,
    requerimiento_id: req ? req.id : undefined,
  });
  if (!r.ok) return mostrarAviso(textoDeError(r), true);
  mostrarAviso("Solicitud enviada. El estudiante debe aceptarla.");
  await recargarTodo(activa.id);
}

document.getElementById("tabs").addEventListener("click", async (evento) => {
  const tab = evento.target.closest(".tab");
  if (!tab) return;
  document.querySelectorAll("#tabs .tab").forEach((t) => t.classList.toggle("tab--active", t === tab));
  filtroActual = tab.dataset.filtro;
  try { await cargarEstudiantes(); } catch (e) { mostrarAviso(e.message, true); }
});

document.getElementById("solicitud-activa").addEventListener("change", () => {
  cargarEstudiantes().catch((e) => mostrarAviso(e.message, true));
});

/* ---------- 5. MIS SOLICITUDES Y CANDIDATOS ---------- */
function botonesPostulacion(p) {
  if (p.puede_responder) {
    return `<button class="btn btn--primary btn--sm" data-accion="responder" data-respuesta="aceptar" data-id="${p.id}">Aceptar</button>
            <button class="btn btn--danger-soft btn--sm" data-accion="responder" data-respuesta="rechazar" data-id="${p.id}">Rechazar</button>`;
  }
  if (p.estado === "Pendiente" || (p.estado === "Aceptada" && p.solicitud.estado !== "Completada")) {
    return `<button class="btn btn--outline btn--sm" data-accion="cancelar-postulacion" data-id="${p.id}">Cancelar</button>`;
  }
  return "";
}

function filaCandidato(p) {
  const origen = p.iniciada_por === "estudiante" ? "Postuló a tu solicitud" : "Se lo solicitaste tú";
  return `
    <div class="fila fila--sub">
      <div class="fila__top">
        <div>
          <span class="fila__titulo">${esc(p.estudiante.nombre)}</span>
          <span class="${claseEstado(p.estado)}">${esc(p.estado)}</span>
          <div class="fila__meta">
            <span>${esc(origen)}</span>
            ${p.requerimiento ? `<span>•</span><span>Tratamiento: ${esc(p.requerimiento.tratamiento)} (tutor ${esc(p.requerimiento.tutor)})</span>` : ""}
          </div>
          ${p.mensaje ? `<p class="fila__texto">"${esc(p.mensaje)}"</p>` : ""}
        </div>
        <div class="fila__acciones">${botonesPostulacion(p)}</div>
      </div>
    </div>`;
}

function filaSolicitud(s) {
  const candidatos = postulaciones.filter((p) => p.solicitud.id === s.id && p.estado !== "Cancelada");
  const desplegada = abiertas.has(s.id);
  const activa = !["Completada", "Cancelada"].includes(s.estado);
  return `
    <div class="fila" data-id="${s.id}">
      <div class="fila__top">
        <div>
          <span class="fila__titulo">${esc(s.titulo)}</span>
          <span class="${claseEstado(s.estado)}">${esc(s.estado)}${s.postulaciones_pendientes ? ` · ${s.postulaciones_pendientes} pendiente(s)` : ""}</span>
          <div class="fila__meta">
            <span>Código <strong>${esc(s.codigo)}</strong></span><span>•</span>
            <span>${esc(hace(s.fecha_creacion))}</span><span>•</span>
            <span>${esc(nombreArea(s.area))}${s.urgente ? " · Urgente" : ""}</span>
            ${s.comuna ? `<span>•</span><span>${esc(s.comuna)}</span>` : ""}
          </div>
        </div>
        <div class="fila__acciones">
          <button class="btn btn--outline btn--sm" data-accion="candidatos" data-id="${s.id}">
            Candidatos (${candidatos.length}) <span class="material-symbols-rounded">${desplegada ? "expand_less" : "expand_more"}</span>
          </button>
          ${activa ? `<button class="btn btn--danger-soft btn--sm" data-accion="cancelar-solicitud" data-id="${s.id}">Cancelar</button>` : ""}
        </div>
      </div>
      ${desplegada ? `<div class="fila__sub">${candidatos.length ? candidatos.map(filaCandidato).join("") : `<p class="vacio">Aún no hay candidatos. Los estudiantes pueden postular o puedes solicitarles atención arriba.</p>`}</div>` : ""}
    </div>`;
}

async function cargarSolicitudes() {
  [solicitudes, postulaciones] = await Promise.all([cargar("/api/solicitudes"), cargar("/api/postulaciones")]);
  // Las solicitudes con postulaciones por responder se muestran desplegadas.
  postulaciones.filter((p) => p.puede_responder).forEach((p) => abiertas.add(p.solicitud.id));
  poner("total-solicitudes", solicitudes.length);
  document.getElementById("lista-solicitudes").innerHTML = solicitudes.length
    ? solicitudes.map(filaSolicitud).join("")
    : `<p class="vacio">Aún no has publicado solicitudes. Cuéntanos qué necesitas en el recuadro de arriba.</p>`;
}

/* ---------- 6. MIS CITAS ---------- */
function filaCita(c) {
  return `
    <div class="fila">
      <div class="fila__top">
        <div>
          <span class="fila__titulo">${esc(fechaHora(c.fecha_hora))}</span>
          <span class="${claseEstado(c.estado)}">${esc(c.estado)}</span>
          <div class="fila__meta">
            <span><strong>${esc(c.solicitud_codigo)}</strong> ${esc(c.titulo)}</span><span>•</span>
            <span>Estudiante: ${esc(c.estudiante.nombre)}</span>
            ${c.lugar ? `<span>•</span><span>${esc(c.lugar)}</span>` : ""}
          </div>
          ${c.notas ? `<p class="fila__texto">${esc(c.notas)}</p>` : ""}
        </div>
        ${c.estado === "Agendada" ? `<button class="btn btn--danger-soft btn--sm" data-accion="cita-cancelar" data-id="${c.id}">Cancelar cita</button>` : ""}
      </div>
    </div>`;
}

async function cargarCitas() {
  const citas = await cargar("/api/citas");
  document.getElementById("lista-citas").innerHTML = citas.length
    ? citas.map(filaCita).join("")
    : `<p class="vacio">Aún no tienes citas. Cuando un estudiante acepte tu solicitud, agendará la cita aquí.</p>`;
}

/* ---------- 7. ACCIONES ---------- */
async function recargarTodo(seleccionarSolicitudId) {
  await Promise.all([cargarSolicitudes(), cargarResumen(), cargarCitas()]);
  llenarSelectorSolicitud(seleccionarSolicitudId);
  await cargarEstudiantes();
}

async function accion(ruta, metodo, cuerpo, mensaje) {
  const r = await apiJson(ruta, metodo, cuerpo);
  if (!r.ok) return mostrarAviso(textoDeError(r), true);
  mostrarAviso(mensaje);
  await recargarTodo();
}

document.addEventListener("click", (evento) => {
  const el = evento.target.closest("[data-accion]");
  if (!el) return;
  const id = Number(el.dataset.id);
  switch (el.dataset.accion) {
    case "solicitar": return solicitar(id);
    case "candidatos":
      if (abiertas.has(id)) abiertas.delete(id); else abiertas.add(id);
      document.getElementById("lista-solicitudes").innerHTML = solicitudes.map(filaSolicitud).join("");
      return;
    case "responder":
      return accion(`/api/postulaciones/${id}/responder`, "POST", { accion: el.dataset.respuesta },
        el.dataset.respuesta === "aceptar" ? "Candidato aceptado. El estudiante agendará la cita." : "Candidato rechazado.");
    case "cancelar-postulacion":
      if (confirm("¿Cancelar esta postulación?")) accion(`/api/postulaciones/${id}/cancelar`, "POST", undefined, "Postulación cancelada.");
      return;
    case "cancelar-solicitud":
      if (confirm("¿Cancelar esta solicitud? También se cancelarán sus postulaciones y citas.")) accion(`/api/solicitudes/${id}/cancelar`, "POST", undefined, "Solicitud cancelada.");
      return;
    case "cita-cancelar":
      if (confirm("¿Cancelar esta cita?")) accion(`/api/citas/${id}`, "PATCH", { estado: "Cancelada" }, "Cita cancelada.");
      return;
  }
});

document.addEventListener("perfil-actualizado", () => cargarPerfil().catch(() => {}));

/* ---------- INICIO ---------- */
async function iniciar() {
  AREAS = (await cargar("/api/catalogos")).areas;
  llenarAreas();
  const resultados = await Promise.allSettled([cargarPerfil(), recargarTodo()]);
  if (resultados.some((r) => r.status === "rejected")) {
    mostrarAviso("Algunos datos no se pudieron cargar. Recarga la página.", true);
  }
}

iniciar().catch(() => mostrarAviso("No se pudo conectar con el servidor.", true));
