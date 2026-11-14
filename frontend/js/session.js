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
  admin: "/admin",
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

/**
 * Cuadro de diálogo para una cuenta suspendida o baneada por la moderación.
 * texto: lo que explica el servidor. alCerrar: qué hacer al pulsar "Entendido"
 * (en un portal, cerrar la sesión; en el login, solo cerrar el cuadro).
 */
function mostrarCuentaSuspendida(texto, alCerrar) {
  if (document.getElementById("cuenta-suspendida")) return;   // ya está a la vista
  const dialogo = document.createElement("dialog");
  dialogo.id = "cuenta-suspendida";
  dialogo.className = "suspension";
  dialogo.innerHTML = `
    <div class="suspension__icono"><span class="material-symbols-rounded">shield_person</span></div>
    <h2 class="suspension__titulo">Cuenta suspendida</h2>
    <p class="suspension__texto"></p>
    <p class="suspension__nota">Cuidar el trato respetuoso entre estudiantes y pacientes es parte
      fundamental de DentMatch. Si crees que se trata de un error, un administrador podrá revisarlo.</p>
    <button type="button" class="btn btn--primary suspension__boton">Entendido</button>`;
  dialogo.querySelector(".suspension__texto").textContent = texto;
  const cerrar = () => { dialogo.close(); dialogo.remove(); if (alCerrar) alCerrar(); };
  dialogo.querySelector(".suspension__boton").addEventListener("click", cerrar);
  dialogo.addEventListener("cancel", (e) => { e.preventDefault(); cerrar(); });  // tecla Esc
  document.body.appendChild(dialogo);
  dialogo.showModal();
}

// 'monserrat canales oportus' -> 'Monserrat Canales Oportus' (de/del/la/y quedan en minúscula).
const PARTICULAS_NOMBRE = new Set(["de", "del", "la", "las", "los", "y"]);
function nombrePropio(texto) {
  return texto.trim().split(/\s+/).map((palabra, i) => {
    const minuscula = palabra.toLowerCase();
    if (i > 0 && PARTICULAS_NOMBRE.has(minuscula)) return minuscula;
    return minuscula.charAt(0).toUpperCase() + minuscula.slice(1);
  }).join(" ");
}

document.addEventListener("DOMContentLoaded", () => {
  const guardado = localStorage.getItem("dentmatch_nombre");
  if (!guardado) return;
  const nombre = nombrePropio(guardado);
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
