/* =========================================================================
   PÁGINA PRINCIPAL - dibuja los casos clínicos de ejemplo
   Los datos son de muestra; más adelante vendrán del backend con fetch.
   Requiere utils.js (función esc) cargado antes en el HTML.
   ========================================================================= */

/* ---------- SESIÓN: el index es solo para visitantes ---------- */
// obtenerToken, obtenerRol y DESTINO_TRAS_LOGIN vienen de session.js.
if (obtenerToken() && DESTINO_TRAS_LOGIN[obtenerRol()]) {
  window.location.replace(DESTINO_TRAS_LOGIN[obtenerRol()]);
}

/* ---------- CASOS CLÍNICOS ---------- */
const CASOS = [
  {
    estado: "espera", hace: "Hace 2 hrs",
    etiquetas: [{ texto: "Endodoncia" }, { texto: "Dolor activo", tipo: "danger" }],
    titulo: "Dolor agudo en molar #19",
    detalles: [["Paciente:", "M. González (42 años)"], ["Comuna:", "Providencia, RM"], ["Complejidad:", "Molar multirradicular"]],
    ficha: "#EM-9102",
  },
  {
    estado: "evaluacion", hace: "Ayer",
    etiquetas: [{ texto: "Periodoncia" }, { texto: "Cátedra Periodoncia II", tipo: "muted" }],
    titulo: "Sangrado gingival y limpieza profunda",
    detalles: [["Paciente:", "J. Morales (35 años)"], ["Comuna:", "Santiago Centro, RM"], ["Requerimiento:", "Destartraje subgingival"]],
    ficha: "#PE-4481",
  },
  {
    estado: "espera", hace: "Hace 1 día",
    etiquetas: [{ texto: "Operatoria Dental" }, { texto: "Dientes anteriores", tipo: "muted" }],
    titulo: "Restauración estética y caries oclusal",
    detalles: [["Paciente:", "C. Retamal (28 años)"], ["Comuna:", "San Miguel, RM"], ["Procedimiento:", "Composite estratificado"]],
    ficha: "#OP-7729",
  },
  {
    estado: "espera", hace: "Hace 3 días",
    etiquetas: [{ texto: "Prótesis Removible" }, { texto: "Rehabilitación Oral", tipo: "muted" }],
    titulo: "Evaluación y confección de prótesis parcial",
    detalles: [["Paciente:", "H. Fuentes (61 años)"], ["Comuna:", "Ñuñoa, RM"], ["Alcance:", "PPR Superior acrílica"]],
    ficha: "#PR-3320",
  },
  {
    estado: "espera", hace: "Hace 4 hrs",
    etiquetas: [{ texto: "Cirugía Bucal Menor" }, { texto: "Rx Panorámica adjunta", tipo: "green" }],
    titulo: "Exodoncia de terceros molares incluidos",
    detalles: [["Paciente:", "D. Araya (23 años)"], ["Comuna:", "Recoleta, RM"], ["Diagnóstico:", "Piezas #38 y #48 mesioanguladas"]],
    ficha: "#CB-1194",
  },
  {
    estado: "espera", hace: "Hace 5 hrs",
    etiquetas: [{ texto: "Odontopediatría" }, { texto: "Prevención Integral", tipo: "muted" }],
    titulo: "Sellantes y control preventivo infantil",
    detalles: [["Paciente:", "F. Silva (9 años)"], ["Comuna:", "La Florida, RM"], ["Consentimiento:", "Acompañante legal validado"]],
    ficha: "#OP-5026",
  },
];

const ETIQUETAS_ESTADO = {
  espera: { texto: "En espera", clase: "status" },
  evaluacion: { texto: "En evaluación", clase: "status status--eval" },
};

function tarjetaCaso(c) {
  const estado = ETIQUETAS_ESTADO[c.estado];
  const etiquetas = c.etiquetas
    .map((t) => `<span class="tag${t.tipo ? " tag--" + t.tipo : ""}">${esc(t.texto)}</span>`)
    .join("");
  const detalles = c.detalles
    .map(([etiqueta, valor]) => `<div><dt>${esc(etiqueta)}</dt><dd>${esc(valor)}</dd></div>`)
    .join("");

  return `
    <article class="card case">
      <div class="case__top">
        <span class="${estado.clase}"><span class="dot"></span> ${estado.texto}</span>
        <span class="case__time">${esc(c.hace)}</span>
      </div>
      <div class="case__tags">${etiquetas}</div>
      <h3>${esc(c.titulo)}</h3>
      <dl class="case__details">${detalles}</dl>
      <div class="case__foot">
        <span>Ficha ${esc(c.ficha)}</span>
        <a href="/registro?rol=estudiante">Revisar y postular <span class="material-symbols-rounded">arrow_forward</span></a>
      </div>
    </article>`;
}

document.getElementById("lista-casos").innerHTML = CASOS.map(tarjetaCaso).join("");
document.getElementById("leyenda-espera").textContent = CASOS.filter((c) => c.estado === "espera").length;
document.getElementById("leyenda-evaluacion").textContent = CASOS.filter((c) => c.estado === "evaluacion").length;
