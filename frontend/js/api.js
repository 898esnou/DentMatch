/**
 * api.js
 * ---------------------------------------------------------------------
 * Funciones compartidas para comunicarse con el backend de FastAPI.
 * Tanto login.js como register.js importan este archivo.
 *
 * El frontend lo sirve el mismo backend, así que BASE_URL queda vacío
 * (mismo origen) y funciona en cualquier puerto. Si algún día el backend
 * se separa del frontend, aquí va su dirección (ej. "https://api.midominio.cl").
 * ---------------------------------------------------------------------
 */

const BASE_URL = "";

/**
 * Petición autenticada (agrega el token). Si el servidor responde 401
 * (token vencido o inválido) cierra la sesión y vuelve al login.
 * Requiere session.js cargado antes.
 */
async function apiFetch(ruta, opciones = {}) {
  const respuesta = await fetch(`${BASE_URL}${ruta}`, {
    ...opciones,
    headers: { ...(opciones.headers || {}), Authorization: `Bearer ${obtenerToken()}` },
  });
  if (respuesta.status === 401) cerrarSesion();
  return respuesta;
}

/**
 * Envía el formulario de registro al backend.
 * @param {FormData} datosFormulario - Los campos del formulario (nombre, rut, correo, etc.)
 * @returns {Promise<{ok: boolean, data: object}>} Resultado de la petición.
 */
async function registrarUsuario(datosFormulario) {
  const respuesta = await fetch(`${BASE_URL}/api/registro`, {
    method: "POST",
    body: datosFormulario, // FormData: no se pone Content-Type manual, el navegador lo arma solo
  });

  const data = await respuesta.json();
  return { ok: respuesta.ok, data };
}

/**
 * Envía las credenciales de login al backend.
 * @param {string} correo
 * @param {string} contrasena
 * @returns {Promise<{ok: boolean, data: object}>} Resultado de la petición.
 */
async function iniciarSesion(correo, contrasena) {
  const respuesta = await fetch(`${BASE_URL}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ correo, contrasena }),
  });

  const data = await respuesta.json();
  return { ok: respuesta.ok, data };
}
