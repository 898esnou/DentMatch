/**
 * verificacion.js
 * ---------------------------------------------------------------------
 * Verificación del perfil del estudiante en su portal:
 * - Banner de estado arriba (No verificado / En revisión / Rechazado)
 * - Botón "Verificar tu perfil" -> modal para subir el certificado de alumno regular
 * - estaVerificado(): lo usa portal-estudiante.js para bloquear acciones
 *
 * Mientras no esté verificado el estudiante puede ver los casos, pero no postular,
 * agendar ni publicar requerimientos (el backend lo exige; esto solo lo explica).
 * Dispara "verificacion-actualizada" en document cada vez que cambia el estado.
 * Requiere session.js, api.js, utils.js (esc) y formulario-modal.js cargados antes.
 * ---------------------------------------------------------------------
 */

const TAMANO_MAXIMO_CERTIFICADO = 5 * 1024 * 1024; // 5 MB, igual que el backend
const EXTENSIONES_CERTIFICADO = [".pdf", ".jpg", ".jpeg", ".png"];

let estadoVerificacion = null; // última respuesta de GET /api/verificacion
let avisoVerificadoMostrado = false; // la última carga ya avisó "verificado exitosamente"

function estaVerificado() {
  return estadoVerificacion !== null && estadoVerificacion.estado === "Activo";
}

/** Lo que muestra cada estado: icono, estilo, título y texto del banner. */
function textosVerificacion(v) {
  switch (v.estado) {
    case "En Verificación":
      return {
        clase: "verif--revision", icono: "hourglass_top", boton: "",
        titulo: "Estamos revisando tu certificado",
        texto: "Te avisaremos apenas esté listo. Mientras tanto puedes explorar los casos disponibles.",
      };
    case "Rechazado":
      return {
        clase: "verif--rechazado", icono: "error", boton: "Volver a subir certificado",
        titulo: "No pudimos verificar tu certificado",
        texto: v.motivo ? `Motivo: ${v.motivo}` : "Revisa que el documento sea legible y vigente, y súbelo de nuevo.",
      };
    default: // No verificado
      return {
        clase: "verif--pendiente", icono: "verified_user", boton: "Verificar tu perfil",
        titulo: "Verifica tu perfil para empezar",
        texto: "Sube tu certificado de alumno regular. Mientras no lo hagas puedes ver los casos de pacientes, pero no postular, agendar citas ni publicar requerimientos.",
      };
  }
}

function dibujarBanner() {
  const banner = document.getElementById("banner-verificacion");
  if (!banner || !estadoVerificacion) return;
  if (estaVerificado() && estadoVerificacion.en_gracia) {
    // El semestre del certificado terminó: sigue con acceso unos días para renovarlo.
    banner.className = "verif verif--rechazado";
    banner.hidden = false;
    banner.innerHTML = `
      <span class="verif__icono material-symbols-rounded">schedule</span>
      <div class="verif__texto">
        <strong>Renueva tu certificado</strong>
        <p>${esc(estadoVerificacion.mensaje)}</p>
      </div>
      <button type="button" class="btn btn--primary" data-accion="verificar-perfil">Subir certificado nuevo</button>`;
    return;
  }
  if (estaVerificado()) {
    banner.hidden = true;
    return;
  }
  const t = textosVerificacion(estadoVerificacion);
  banner.className = `verif ${t.clase}`;
  banner.hidden = false;
  banner.innerHTML = `
    <span class="verif__icono material-symbols-rounded">${t.icono}</span>
    <div class="verif__texto">
      <strong>${esc(t.titulo)}</strong>
      <p>${esc(t.texto)}</p>
    </div>
    ${t.boton ? `<button type="button" class="btn btn--primary" data-accion="verificar-perfil">${esc(t.boton)}</button>` : ""}`;
}

/** El botón del perfil cambia de texto según el estado. */
function dibujarBotonPerfil() {
  const boton = document.getElementById("boton-verificar");
  if (!boton || !estadoVerificacion) return;
  const etiquetas = {
    "No verificado": "Verificar tu perfil",
    "En Verificación": "Certificado en revisión",
    "Rechazado": "Volver a subir certificado",
    "Activo": "Renovar certificado",
  };
  const texto = etiquetas[estadoVerificacion.estado] || "Verificar tu perfil";
  boton.querySelector("span:last-child").textContent = texto;
  boton.disabled = !estadoVerificacion.puede_subir;
}

/**
 * Avisa una sola vez cuando el estudiante pasa a "Activo": ya sea al instante (QR validado)
 * o más tarde (un admin lo aprobó). Se compara con el último estado que vio en este navegador;
 * si no había ninguno (primera visita) no se avisa.
 */
function avisarSiFueVerificado(estado) {
  const clave = `dentmatch_verif_visto_${localStorage.getItem("dentmatch_nombre") || ""}`;
  let anterior = null;
  try {
    anterior = localStorage.getItem(clave);
    localStorage.setItem(clave, estado);
  } catch (e) { /* sin almacenamiento: no se avisa */ }
  if (anterior && anterior !== "Activo" && estado === "Activo") {
    mostrarAviso("¡Tu perfil fue verificado exitosamente!");
    return true;
  }
  return false;
}

async function cargarVerificacion(avisar = true) {
  const r = await apiJson("/api/verificacion");
  if (!r.ok) throw new Error(textoDeError(r));
  estadoVerificacion = r.data;
  avisoVerificadoMostrado = avisarSiFueVerificado(r.data.estado);
  document.body.classList.toggle("no-verificado", !estaVerificado());
  dibujarBanner();
  dibujarBotonPerfil();
  if (avisar) document.dispatchEvent(new CustomEvent("verificacion-actualizada"));
}

/* ---------- Modal para subir el certificado ---------- */
function crearModalVerificacion() {
  const dialogo = document.createElement("dialog");
  dialogo.className = "pm";
  dialogo.id = "modal-verificacion";
  dialogo.innerHTML = `
    <form class="pm__form" novalidate>
      <h2 class="pm__title">Verifica tu perfil</h2>
      <p class="pm__lead">Sube tu certificado de alumno regular. Solo lo ve el equipo de DentMatch y se guarda de forma privada.</p>
      <p class="pm__error" role="alert" hidden></p>
      <div class="pm__field">
        <label for="archivo-certificado">Certificado (PDF, JPG o PNG, máximo 5 MB)</label>
        <input type="file" id="archivo-certificado" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/png,image/jpeg" />
        <span class="pm__hint">Usa el certificado original con su código QR visible: así podremos validarlo.</span>
      </div>
      <div class="pm__actions">
        <button type="button" class="btn btn--ghost" data-pm="cancelar">Cancelar</button>
        <button type="submit" class="btn btn--primary" data-pm="enviar">Enviar certificado</button>
      </div>
    </form>`;
  document.body.appendChild(dialogo);
  dialogo.querySelector("[data-pm='cancelar']").addEventListener("click", () => dialogo.close());
  dialogo.querySelector("form").addEventListener("submit", enviarCertificado);
  return dialogo;
}

/** Devuelve un texto de error si el archivo no sirve, o null si está bien. */
function validarArchivoCertificado(archivo) {
  if (!archivo) return "Elige el archivo de tu certificado.";
  const nombre = archivo.name.toLowerCase();
  if (!EXTENSIONES_CERTIFICADO.some((ext) => nombre.endsWith(ext))) return "Formato no permitido: sube un PDF, JPG o PNG.";
  if (archivo.size > TAMANO_MAXIMO_CERTIFICADO) return "El archivo supera los 5 MB.";
  if (archivo.size === 0) return "El archivo está vacío.";
  return null;
}

async function enviarCertificado(evento) {
  evento.preventDefault();
  const dialogo = document.getElementById("modal-verificacion");
  const cajaError = dialogo.querySelector(".pm__error");
  const boton = dialogo.querySelector("[data-pm='enviar']");
  const archivo = dialogo.querySelector("#archivo-certificado").files[0];

  const error = validarArchivoCertificado(archivo);
  cajaError.hidden = !error;
  if (error) {
    cajaError.textContent = error;
    return;
  }

  boton.disabled = true;
  boton.textContent = "Enviando…";
  try {
    const datos = new FormData();
    datos.append("archivo", archivo);
    // FormData: el navegador arma solo el Content-Type (no se pone a mano).
    const respuesta = await apiFetch("/api/verificacion/certificado", { method: "POST", body: datos });
    let cuerpo = null;
    try { cuerpo = await respuesta.json(); } catch (e) { /* sin cuerpo */ }
    if (!respuesta.ok) {
      cajaError.textContent = textoDeError({ data: cuerpo }, "No se pudo enviar el certificado.");
      cajaError.hidden = false;
      return;
    }
    dialogo.close();
    await cargarVerificacion();
    // Si el QR se validó solo, ya salió el aviso de "verificado": no se pisa con otro.
    if (!avisoVerificadoMostrado) mostrarAviso("Certificado enviado. Lo estamos revisando.");
  } catch (e) {
    cajaError.textContent = "No se pudo conectar con el servidor.";
    cajaError.hidden = false;
  } finally {
    boton.disabled = false;
    boton.textContent = "Enviar certificado";
  }
}

function abrirVerificacion() {
  if (estadoVerificacion && !estadoVerificacion.puede_subir) {
    return mostrarAviso("Tu certificado ya se está revisando.", true);
  }
  const dialogo = document.getElementById("modal-verificacion") || crearModalVerificacion();
  dialogo.querySelector("form").reset();
  dialogo.querySelector(".pm__error").hidden = true;
  dialogo.showModal();
}

/** Para las acciones bloqueadas: explica por qué y ofrece verificar. */
function pedirVerificacion() {
  mostrarAviso("Verifica tu perfil para poder hacer esto.", true);
  if (estadoVerificacion && estadoVerificacion.puede_subir) abrirVerificacion();
}

document.addEventListener("click", (e) => {
  if (e.target.closest("[data-accion='verificar-perfil']")) abrirVerificacion();
});
