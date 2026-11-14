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
const campoCertificado = document.getElementById("certificado"); // sin "name": se sube aparte, tras crear la cuenta
const TAMANO_MAXIMO_CERTIFICADO = 5 * 1024 * 1024;

const selectTipoDocumento = document.getElementById("tipo_documento");
const campoDocumento = document.getElementById("rut");

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
  campoCertificado.required = esEstudiante;
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

  const errorDocumento = validarDocumento(selectTipoDocumento.value, campoDocumento.value);
  if (errorDocumento) {
    return errorDocumento;
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

  if (rol === "estudiante") {
    const archivo = campoCertificado.files[0];
    if (!archivo) return "Adjunta tu certificado de alumno regular (PDF, JPG o PNG).";
    if (!/\.(pdf|jpe?g|png)$/i.test(archivo.name)) return "Formato no permitido: sube un PDF, JPG o PNG.";
    if (archivo.size > TAMANO_MAXIMO_CERTIFICADO) return "El certificado supera los 5 MB.";
    if (archivo.size === 0) return "El archivo del certificado está vacío.";
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

// El RUT se va escribiendo con formato (12.345.678-5); el documento extranjero se deja tal cual.
activarFormatoRut(campoDocumento, () => selectTipoDocumento.value === "rut");

// Cambia las etiquetas según el tipo de documento elegido.
selectTipoDocumento.addEventListener("change", () => {
  const esExtranjero = selectTipoDocumento.value === "extranjero";
  document.getElementById("etiqueta-documento").textContent = esExtranjero ? "Número de documento" : "RUT";
  document.getElementById("ayuda-documento").textContent = esExtranjero
    ? "Pasaporte u otro documento: letras y números, entre 5 y 16 caracteres."
    : "Escribe solo números y el dígito verificador; los puntos y el guion se agregan solos.";
  campoDocumento.maxLength = esExtranjero ? 20 : 12;
  campoDocumento.placeholder = esExtranjero ? "AB123456" : "12.345.678-5";
  campoDocumento.value = esExtranjero ? campoDocumento.value : formatearRutAlEscribir(campoDocumento.value);
});

/**
 * Sube el certificado recién adjuntado: entra con la cuenta nueva, lo envía y no deja la sesión abierta.
 * Si algo falla la cuenta igual queda creada y el certificado se sube después desde el portal.
 * @returns {Promise<string>} Texto para agregar al aviso final.
 */
async function enviarCertificadoDelRegistro(correo, contrasena) {
  const pendiente = " Sube tu certificado desde tu portal para que un administrador verifique tu perfil.";
  try {
    const sesion = await iniciarSesion(correo, contrasena);
    if (!sesion.ok) return pendiente;
    const datos = new FormData();
    datos.append("archivo", campoCertificado.files[0]);
    const respuesta = await fetch(`${BASE_URL}/api/verificacion/certificado`, {
      method: "POST",
      headers: { Authorization: `Bearer ${sesion.data.access_token}` },
      body: datos,
    });
    return respuesta.ok
      ? " Tu certificado quedó enviado y un administrador lo revisará."
      : " No pudimos enviar tu certificado." + pendiente;
  } catch (e) {
    return " No pudimos enviar tu certificado." + pendiente;
  }
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
      let aviso = "¡Cuenta creada exitosamente! Ahora puedes iniciar sesión.";
      if (inputRolElegido.value === "estudiante") {
        botonEnviar.textContent = "Enviando certificado...";
        aviso += await enviarCertificadoDelRegistro(datosFormulario.get("correo"), datosFormulario.get("contrasena"));
      }
      alert(aviso);
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
