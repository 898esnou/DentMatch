/**
 * portal-nav.js
 * ---------------------------------------------------------------------
 * Marca en el menú del portal la sección que se está viendo (scroll-spy).
 * Los enlaces "#seccion" se activan cuando su sección cruza la parte alta
 * de la pantalla; si no se ha pasado ninguna, queda activo "Inicio".
 * Sirve a los dos portales: solo necesita .portal-nav con enlaces a #ids.
 * ---------------------------------------------------------------------
 */
(function () {
  const enlaces = [...document.querySelectorAll(".portal-nav__link")];
  const inicio = enlaces.find((a) => !a.getAttribute("href").includes("#"));
  const secciones = enlaces
    .filter((a) => a.getAttribute("href").startsWith("#"))
    .map((a) => ({ enlace: a, el: document.querySelector(a.getAttribute("href")) }))
    .filter((s) => s.el);
  const MARGEN = 150; // un poco más que la altura del encabezado fijo

  function marcar(activo) {
    enlaces.forEach((a) => a.classList.toggle("portal-nav__link--active", a === activo));
  }

  function actualizar() {
    const alFinal = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
    let activo = inicio;
    for (const s of secciones) {
      if (s.el.getBoundingClientRect().top <= MARGEN) activo = s.enlace;
    }
    // Al llegar al fondo, la última sección gana aunque sea corta.
    if (alFinal && secciones.length) activo = secciones[secciones.length - 1].enlace;
    marcar(activo);
  }

  // Al pulsar un enlace, manda lo que eligió el usuario (hay secciones al final de la
  // página que nunca llegan arriba); el scroll manual vuelve a calcular la sección.
  let elegido = false;
  enlaces.forEach((a) => a.addEventListener("click", () => { elegido = true; marcar(a); }));
  ["wheel", "touchstart", "keydown"].forEach((ev) =>
    window.addEventListener(ev, () => { elegido = false; }, { passive: true }));

  window.addEventListener("scroll", () => { if (!elegido) actualizar(); }, { passive: true });
  window.addEventListener("resize", actualizar);
  window.addEventListener("load", actualizar);
  actualizar();
})();
