/**
 * avisos.js
 * ---------------------------------------------------------------------
 * Avisos importantes para el usuario (ej. "tu postulación fue cancelada porque la otra
 * persona ya no está disponible"). Se consultan al entrar y cada minuto; el servidor
 * entrega cada aviso una sola vez y se muestran hasta que la persona los cierra.
 * Requiere session.js, api.js, utils.js (esc) y formulario-modal.js (apiJson).
 * ---------------------------------------------------------------------
 */
(function () {
  const REFRESCO_MS = 60000;

  let caja = document.getElementById("avisos-persistentes");
  if (!caja) {
    caja = document.createElement("div");
    caja.id = "avisos-persistentes";
    caja.className = "avisos-persistentes";
    caja.setAttribute("aria-live", "polite");
    document.body.appendChild(caja);
  }

  caja.addEventListener("click", (e) => {
    const item = e.target.closest("[data-cerrar-aviso]");
    if (item) item.closest(".avisos-persistentes__item").remove();
  });

  async function consultar() {
    if (document.hidden) return;
    const r = await apiJson("/api/avisos");
    if (!r.ok || !Array.isArray(r.data)) return;
    r.data.forEach((a) => {
      const item = document.createElement("div");
      item.className = "avisos-persistentes__item";
      item.innerHTML = `<span>${esc(a.texto)}</span>
        <button type="button" data-cerrar-aviso aria-label="Cerrar aviso">×</button>`;
      caja.appendChild(item);
    });
  }

  consultar().catch(() => {});
  setInterval(() => consultar().catch(() => {}), REFRESCO_MS);
})();
