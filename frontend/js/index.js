/* =========================================================================
   PÁGINA PRINCIPAL (landing)
   - Solo para visitantes: quien ya inició sesión va directo a su portal.
   - Marca en el menú la sección que se está viendo.
   ========================================================================= */

/* ---------- SESIÓN: el index es solo para visitantes ---------- */
// obtenerToken, obtenerRol y DESTINO_TRAS_LOGIN vienen de session.js.
if (obtenerToken() && DESTINO_TRAS_LOGIN[obtenerRol()]) {
  window.location.replace(DESTINO_TRAS_LOGIN[obtenerRol()]);
}

/* ---------- MENÚ: sección activa al desplazarse ---------- */
const SECCIONES = ["inicio", "solicitudes", "estudiantes", "chat", "nosotros"];
const enlacesMenu = new Map(
  [...document.querySelectorAll(".site-nav__link")].map((a) => [a.getAttribute("href").slice(1), a])
);

function marcarActiva(id) {
  enlacesMenu.forEach((enlace, clave) => {
    enlace.classList.toggle("site-nav__link--active", clave === id);
  });
}

function seccionVisible() {
  // la última sección cuyo borde superior ya llegó a la cabecera fija (con un margen)
  const linea = document.querySelector(".site-header").offsetHeight + 60;
  let actual = SECCIONES[0];
  for (const id of SECCIONES) {
    const el = document.getElementById(id);
    if (el && el.getBoundingClientRect().top <= linea) actual = id;
  }
  // al llegar al final de la página, la última sección queda activa aunque sea corta
  if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 4) {
    actual = SECCIONES[SECCIONES.length - 1];
  }
  return actual;
}

let esperando = false;
window.addEventListener("scroll", () => {
  if (esperando) return;
  esperando = true;
  requestAnimationFrame(() => {
    marcarActiva(seccionVisible());
    esperando = false;
  });
}, { passive: true });
marcarActiva(seccionVisible());
