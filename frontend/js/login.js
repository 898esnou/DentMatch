/**
 * login.js
 * ---------------------------------------------------------------------
 * Lógica de la página de login (login.html).
 *
 * 1. Toggle de rol (solo visual, no afecta la petición al backend)
 * 2. Envío de credenciales y manejo de la respuesta
 * ---------------------------------------------------------------------
 */

const botonRolEstudiante = document.getElementById("boton-rol-estudiante");
const botonRolPaciente = document.getElementById("boton-rol-paciente");

const formulario = document.getElementById("form-login");
const botonEnviar = document.getElementById("boton-enviar");
const cajaMensajeError = document.getElementById("mensaje-error");

/* =========================================================================
    1. SELECTOR DE ROL
    Cambia el tema de la página (body[data-rol]) y los textos. El rol no
    viaja al backend: el servidor lo identifica por el correo, pero lo
    comparamos al recibir la respuesta para avisar si eligió el equivocado.
========================================================================= */
const TEXTOS = {
  estudiante: "Entra a tu portal para gestionar tus requerimientos y pacientes.",
  paciente: "Entra para encontrar y agendar atención dental supervisada.",
};
// DESTINO_TRAS_LOGIN (rol -> página) vive en session.js
let rolElegido = "estudiante";

function elegirRolVisual(rol) {
  rolElegido = rol;
  document.body.dataset.rol = rol;
  botonRolEstudiante.setAttribute("aria-pressed", String(rol === "estudiante"));
  botonRolPaciente.setAttribute("aria-pressed", String(rol === "paciente"));
  document.getElementById("subtitulo-login").textContent = TEXTOS[rol];
  document.getElementById("enlace-registro").href = `/registro?rol=${rol}`;
  ocultarError();
}

botonRolEstudiante.addEventListener("click", () => elegirRolVisual("estudiante"));
botonRolPaciente.addEventListener("click", () => elegirRolVisual("paciente"));

/* =========================================================================
    2. ENVÍO DE CREDENCIALES
========================================================================= */
function mostrarError(mensaje) {
  cajaMensajeError.textContent = mensaje;
  cajaMensajeError.classList.remove("oculto");
}

function ocultarError() {
  cajaMensajeError.classList.add("oculto");
}

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  ocultarError();

  const correo = document.getElementById("correo").value;
  const contrasena = document.getElementById("contrasena").value;

  botonEnviar.disabled = true;
  botonEnviar.textContent = "Ingresando...";

  try {
    const resultado = await iniciarSesion(correo, contrasena);

    if (resultado.ok && resultado.data.rol !== rolElegido && DESTINO_TRAS_LOGIN[resultado.data.rol]) {
      const real = resultado.data.rol === "estudiante" ? "estudiante" : "paciente";
      mostrarError(`Esta cuenta está registrada como ${real}. Cambia la opción de arriba e inténtalo de nuevo.`);
    } else if (resultado.ok) {
      guardarSesion(resultado.data);

      const destino = DESTINO_TRAS_LOGIN[resultado.data.rol];
      if (destino) window.location.href = destino;
      else mostrarError("Este tipo de cuenta aún no tiene acceso disponible.");
    } else {
      mostrarError(resultado.data.detail || "No se pudo iniciar sesión.");
    }
  } catch (error) {
    mostrarError("No se pudo conectar con el servidor. ¿Está corriendo el backend?");
  } finally {
    botonEnviar.disabled = false;
    botonEnviar.textContent = "Iniciar sesión";
  }
});

/* Si ya hay una sesión iniciada, saltar directo al index */
if (obtenerToken() && DESTINO_TRAS_LOGIN[obtenerRol()]) {
  window.location.replace(DESTINO_TRAS_LOGIN[obtenerRol()]);
}

/* Rol inicial: ?rol=paciente en la URL o el último usado */
const rolInicial = new URLSearchParams(location.search).get("rol") || localStorage.getItem("dentmatch_rol");
elegirRolVisual(rolInicial === "paciente" ? "paciente" : "estudiante");
