/* =========================================================================
   UTILIDADES COMPARTIDAS - funciones pequeñas que usan varias páginas
   ========================================================================= */

// Evita que texto con símbolos como < > rompa el HTML (importante cuando
// los datos vengan de la base de datos).
function esc(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}
