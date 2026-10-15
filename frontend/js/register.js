/**
 * register.js
 * ---------------------------------------------------------------------
 * Lógica de la página de registro (register.html).
 *
 * Este archivo se encarga de 3 cosas, separadas en secciones:
 * 1. Toggle de rol (Soy estudiante / Soy paciente)
 * 2. Validaciones en el navegador (antes de llamar al backend)
 * 3. Envío del formulario y manejo de la respuesta del servidor
 * ---------------------------------------------------------------------
 */

// --- Referencias a elementos del DOM que vamos a usar varias veces ---
const botonRolEstudiante = document.getElementById("boton-rol-estudiante");
const botonRolPaciente = document.getElementById("boton-rol-paciente");
const inputRolElegido = document.getElementById("rol-elegido");
const seccionEstudiante = document.getElementById("seccion-estudiante");
const campoUniversidad = document.getElementById("universidad");
const campoAnoCarrera = document.getElementById("ano_carrera");

const formulario = document.getElementById("form-registro");
const botonEnviar = document.getElementById("boton-enviar");
const cajaMensajeError = document.getElementById("mensaje-error");

/* =========================================================================
    1. TOGGLE DE ROL
    Cuando el usuario hace click en "Soy estudiante" o "Soy paciente":
    - Se marca visualmente el botón elegido (aria-pressed="true")
    - Se guarda el rol en el input escondido
    - Se muestra u oculta la sección de campos de estudiante
========================================================================= */

function elegirRol(rol) {
  inputRolElegido.value = rol;

  const esEstudiante = rol === "estudiante";

  // Tema de la página y paso 2 (formulario)
  document.body.dataset.rol = rol;
  document.getElementById("enlace-login").href = `/login?rol=${rol}`;
  document.getElementById("icono-rol").textContent = esEstudiante ? "school" : "favorite";
  document.getElementById("texto-rol").textContent = esEstudiante ? "Cuenta de estudiante" : "Cuenta de paciente";
  document.getElementById("paso-rol").classList.add("oculto");
  document.getElementById("paso-formulario").classList.remove("oculto");

  // Mostrar/ocultar campos de estudiante
  seccionEstudiante.classList.toggle("oculto", !esEstudiante);

  // Si NO es estudiante, esos campos no deben ser obligatorios ni enviarse
  campoUniversidad.required = esEstudiante;
  campoAnoCarrera.required = esEstudiante;
}

botonRolEstudiante.addEventListener("click", () => elegirRol("estudiante"));
botonRolPaciente.addEventListener("click", () => elegirRol("paciente"));

// Volver al paso 1 para cambiar de tipo de cuenta
document.getElementById("boton-cambiar-rol").addEventListener("click", () => {
  inputRolElegido.value = "";
  document.getElementById("paso-formulario").classList.add("oculto");
  document.getElementById("paso-rol").classList.remove("oculto");
  ocultarError();
});

// Si ya hay sesión iniciada, no tiene sentido registrarse: ir al index
if (obtenerToken() && DESTINO_TRAS_LOGIN[obtenerRol()]) window.location.replace(DESTINO_TRAS_LOGIN[obtenerRol()]);

// Si viene de login con ?rol=..., saltamos directo al formulario
const rolUrl = new URLSearchParams(location.search).get("rol");
if (rolUrl === "estudiante" || rolUrl === "paciente") elegirRol(rolUrl);

/* =========================================================================
    2. VALIDACIONES EN EL NAVEGADOR
    Estas validaciones son solo para dar una respuesta rápida al usuario.
    El backend SIEMPRE vuelve a validar todo (nunca hay que confiar
    únicamente en el frontend, porque se puede saltar fácilmente).
========================================================================= */

function validarFormulario() {
  const rol = inputRolElegido.value;
  const contrasena = document.getElementById("contrasena").value;
  const confirmarContrasena = document.getElementById("confirmar_contrasena").value;
  const anoCarrera = campoAnoCarrera.value;

  if (!rol) {
    return "Selecciona si eres estudiante o paciente para continuar.";
  }

  if (contrasena !== confirmarContrasena) {
    return "Las contraseñas no coinciden.";
  }

  if (contrasena.length < 6) {
    return "La contraseña debe tener al menos 6 caracteres.";
  }

  if (rol === "estudiante" && Number(anoCarrera) < 4) {
    return "Los estudiantes deben estar cursando 4to año o superior.";
  }

  return null; // null significa "sin errores"
}

function mostrarError(mensaje) {
  cajaMensajeError.textContent = mensaje;
  cajaMensajeError.classList.remove("oculto");
}

function ocultarError() {
  cajaMensajeError.classList.add("oculto");
}

/* =========================================================================
    3. ENVÍO DEL FORMULARIO
========================================================================= */

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault(); // Evita que la página se recargue
  ocultarError();

  const errorDeValidacion = validarFormulario();
  if (errorDeValidacion) {
    mostrarError(errorDeValidacion);
    return;
  }

  // Arma los datos a enviar. Usamos FormData porque el backend espera
  // "multipart/form-data" (definido así en main.py con Form(...)).
  const datosFormulario = new FormData(formulario);

  // El campo "confirmar_contrasena" no tiene "name", así que no viaja
  // al backend (es solo para la validación en el navegador).

  botonEnviar.disabled = true;
  botonEnviar.textContent = "Creando cuenta...";

  try {
    const resultado = await registrarUsuario(datosFormulario);

    if (resultado.ok) {
      alert("¡Cuenta creada exitosamente! Ahora puedes iniciar sesión.");
      window.location.href = `/login?rol=${inputRolElegido.value}`;
    } else {
      // El backend devuelve el error en la propiedad "detail"
      mostrarError(resultado.data.detail || "Ocurrió un error al crear la cuenta.");
    }
  } catch (error) {
    mostrarError("No se pudo conectar con el servidor. ¿Está corriendo el backend?");
  } finally {
    botonEnviar.disabled = false;
    botonEnviar.textContent = "Crear cuenta";
  }
});
