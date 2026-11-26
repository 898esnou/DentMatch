/* =========================================================================
   UTILIDADES COMPARTIDAS - funciones pequeñas que usan los portales y el panel
   - esc(texto): escapa texto antes de meterlo en innerHTML
   - mostrarAviso(texto, esError): mensaje flotante breve
   - poner(id, texto), iniciales(nombre)
   - conVerMas(...): lista con botón "Mostrar más / menos"
   - claseEstado(estado): color del chip según el estado
   No depende de ningún otro archivo.
   ========================================================================= */

// Evita que texto con símbolos como < > rompa el HTML (o inyecte código): todo
// dato que venga de la API o del usuario pasa por aquí antes de ir a innerHTML.
function esc(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}

/** Mensaje flotante que desaparece solo. */
function mostrarAviso(texto, esError = false) {
  const aviso = document.createElement("div");
  aviso.className = "aviso" + (esError ? " aviso--error" : "");
  aviso.setAttribute("role", "status");
  aviso.textContent = texto;
  document.body.appendChild(aviso);
  setTimeout(() => aviso.remove(), 3500);
}

/** Escribe texto plano dentro del elemento con ese id. */
function poner(id, texto) {
  document.getElementById(id).textContent = texto;
}

/** "Matías Rojas V." -> "MR" (para los avatares). */
function iniciales(nombre) {
  return (nombre || "").trim().split(/\s+/).slice(0, 2).map((p) => p[0] || "").join("").toUpperCase();
}

/**
 * HTML de los primeros `limite` elementos y, si sobran, un botón "Mostrar más / menos".
 * El botón lleva data-accion="ver-mas" y data-lista=clave: cada portal decide cómo repintar.
 * @param {string} clave       nombre de la lista (ej. "casos")
 * @param {Array} items        todos los elementos
 * @param {number} limite      cuántos se ven sin expandir
 * @param {Function} fila      elemento -> HTML
 * @param {boolean} expandida  si la lista está desplegada completa
 */
function conVerMas(clave, items, limite, fila, expandida) {
  const visibles = expandida ? items : items.slice(0, limite);
  const boton = items.length <= limite ? "" :
    `<button type="button" class="ver-mas" data-accion="ver-mas" data-lista="${clave}">
      ${expandida ? "Mostrar menos" : `Mostrar más (${items.length - limite})`}</button>`;
  return visibles.map(fila).join("") + boton;
}

// Estados que se pintan en verde o en rojo; cualquier otro (pendiente, en revisión...) va en ámbar.
const ESTADOS_POSITIVOS = ["Aceptada", "Asignada", "Completado", "Completada", "Realizada", "Activo"];
const ESTADOS_NEGATIVOS = ["Rechazada", "Rechazado", "Cancelada", "Cancelado"];

/** Clase CSS del chip de un estado (verde, rojo o ámbar). */
function claseEstado(estado) {
  if (ESTADOS_POSITIVOS.includes(estado)) return "chip-tag chip-tag--green";
  if (ESTADOS_NEGATIVOS.includes(estado)) return "chip-tag chip-tag--danger";
  return "chip-tag chip-tag--warn";
}
