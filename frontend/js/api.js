/**
 * api.js
 * ---------------------------------------------------------------------
 * Comunicación con el backend de FastAPI (todas las páginas la usan).
 * - apiFetch(ruta, opciones): petición con el token; cierra la sesión si vence
 * - apiJson(ruta, metodo, cuerpo): lo mismo con JSON -> { ok, status, data }
 * - obtenerJson(ruta): GET que devuelve los datos o lanza un Error con el motivo
 * - textoDeError(resultado): el "detail" de FastAPI convertido en un texto para mostrar
 * - registrarUsuario / iniciarSesion: las dos únicas llamadas sin token
 * Requiere session.js cargado antes.
 *
 * El frontend lo sirve el mismo backend, así que BASE_URL queda vacío
 * (mismo origen) y funciona en cualquier puerto. Si algún día el backend
 * se separa del frontend, aquí va su dirección (ej. "https://api.midominio.cl").
 * ---------------------------------------------------------------------
 */

const BASE_URL = "";

/**
 * Petición autenticada (agrega el token). Si el servidor responde 401
 * (token vencido o inválido) cierra la sesión y vuelve al inicio.
 */
async function apiFetch(ruta, opciones = {}) {
  const respuesta = await fetch(`${BASE_URL}${ruta}`, {
    ...opciones,
    headers: { ...(opciones.headers || {}), Authorization: `Bearer ${obtenerToken()}` },
  });
  if (respuesta.status === 401) cerrarSesion();
  if (respuesta.status === 403) {
    // Cuenta suspendida o baneada por la moderación: se explica y se cierra la sesión.
    try {
      const { detail } = await respuesta.clone().json();
      if (typeof detail === "string" && /suspendida/i.test(detail)) {
        mostrarCuentaSuspendida(detail, cerrarSesion);
      }
    } catch (e) { /* respuesta sin JSON */ }
  }
  return respuesta;
}

/** Llama a la API con JSON. Devuelve { ok, status, data } (data es null si no hay cuerpo, ej. 204). */
async function apiJson(ruta, metodo = "GET", cuerpo) {
  const opciones = { method: metodo };
  if (cuerpo !== undefined) {
    opciones.headers = { "Content-Type": "application/json" };
    opciones.body = JSON.stringify(cuerpo);
  }
  const respuesta = await apiFetch(ruta, opciones);
  let data = null;
  try { data = await respuesta.json(); } catch (e) { /* 204 sin cuerpo */ }
  return { ok: respuesta.ok, status: respuesta.status, data };
}

/** GET que devuelve directamente los datos; si falla, lanza un Error con el motivo del servidor. */
async function obtenerJson(ruta) {
  const r = await apiJson(ruta);
  if (!r.ok) throw new Error(textoDeError(r));
  return r.data;
}

/** Convierte el error de la API (detail de FastAPI) en un texto para mostrar. */
function textoDeError(resultado, porDefecto = "No se pudo completar la acción.") {
  const detalle = resultado && resultado.data && resultado.data.detail;
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle) && detalle.length) {   // errores de validación (422)
    const d = detalle[0];
    const campo = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
    return campo ? `${campo}: ${d.msg}` : d.msg;
  }
  return porDefecto;
}

/** Lee el JSON de una respuesta sin fallar si el servidor devolvió otra cosa (ej. un error 500 en HTML). */
async function leerJsonSeguro(respuesta) {
  try { return await respuesta.json(); } catch (e) { return {}; }
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
  return { ok: respuesta.ok, data: await leerJsonSeguro(respuesta) };
}

/**
 * Envía las credenciales de login al backend.
 * @returns {Promise<{ok: boolean, data: object}>} Resultado de la petición.
 */
async function iniciarSesion(correo, contrasena) {
  const respuesta = await fetch(`${BASE_URL}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ correo, contrasena }),
  });
  return { ok: respuesta.ok, data: await leerJsonSeguro(respuesta) };
}
