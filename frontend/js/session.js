/**
 * session.js
 * ---------------------------------------------------------------------
 * Manejo de sesión compartido por todas las páginas:
 * - DESTINO_TRAS_LOGIN: a qué portal va cada rol después de iniciar sesión
 * - protegerPagina(rol): en un portal, manda al login si no hay sesión
 *   o al portal correcto si el rol no corresponde
 * - cerrarSesion(): borra el token y vuelve al index
 * - Rellena el nombre del usuario en cualquier elemento con data-usuario
 *   ("nombre", "primer-nombre" o "iniciales")
 *
 * La seguridad real la hace el backend (token + require_rol); esto solo
 * evita mostrar pantallas que el usuario no debería ver.
 * ---------------------------------------------------------------------
 */

const DESTINO_TRAS_LOGIN = {
  estudiante: "/estudiante",
  paciente: "/paciente",
};

function guardarSesion(data) {
  localStorage.setItem("dentmatch_token", data.access_token);
  localStorage.setItem("dentmatch_rol", data.rol);
  localStorage.setItem("dentmatch_nombre", data.nombre_completo);
}

function obtenerToken() {
  return localStorage.getItem("dentmatch_token");
}

function obtenerRol() {
  return localStorage.getItem("dentmatch_rol");
}

function cerrarSesion() {
  localStorage.removeItem("dentmatch_token");
  localStorage.removeItem("dentmatch_rol");
  localStorage.removeItem("dentmatch_nombre");
  window.location.href = "/";
}

function protegerPagina(rolRequerido) {
  const rol = obtenerRol();
  if (!obtenerToken() || !rol) {
    window.location.replace("/login");
    return false;
  }
  if (rol !== rolRequerido) {
    window.location.replace(DESTINO_TRAS_LOGIN[rol] || "/login");
    return false;
  }
  return true;
}

document.addEventListener("DOMContentLoaded", () => {
  const nombre = localStorage.getItem("dentmatch_nombre");
  if (!nombre) return;
  const partes = nombre.trim().split(/\s+/);
  const valores = {
    nombre,
    "primer-nombre": partes[0],
    iniciales: (partes[0][0] + (partes[1] ? partes[1][0] : "")).toUpperCase(),
  };
  document.querySelectorAll("[data-usuario]").forEach((el) => {
    el.textContent = valores[el.dataset.usuario] ?? el.textContent;
  });
});

/* Botones con data-accion="cerrar-sesion" cierran la sesión */
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-accion='cerrar-sesion']")) cerrarSesion();
});
