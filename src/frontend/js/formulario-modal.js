/**
 * formulario-modal.js
 * ---------------------------------------------------------------------
 * abrirFormulario({...}): cuadro de diálogo con campos y envío (estilos .pm).
 * Lo usan los portales y el panel de administración para crear, editar y confirmar.
 * Requiere session.js, api.js y utils.js cargados antes.
 * ---------------------------------------------------------------------
 */

/**
 * abrirFormulario({
 *   titulo, descripcion, textoBoton,
 *   campos: [{ nombre, etiqueta, tipo, requerido, opciones, valor, placeholder, min, max, ayuda }],
 *   onEnviar: async (valores) => ({ ok: true }) | ({ ok: false, error: "mensaje" })
 * })
 * tipo: text | textarea | select | number | date | datetime-local | checkbox
 * Los campos vacíos no se incluyen en `valores`; los number llegan como número.
 */
function abrirFormulario(config) {
  const dialogo = document.createElement("dialog");
  dialogo.className = "pm";
  dialogo.innerHTML = `
    <form class="pm__form" novalidate>
      <h2 class="pm__title"></h2>
      <p class="pm__lead" hidden></p>
      <p class="pm__error" role="alert" hidden></p>
      <div class="pm__campos"></div>
      <div class="pm__actions">
        <button type="button" class="btn btn--ghost" data-pm="cancelar">Cancelar</button>
        <button type="submit" class="btn btn--primary" data-pm="guardar"></button>
      </div>
    </form>`;
  const formulario = dialogo.querySelector("form");
  const cajaError = dialogo.querySelector(".pm__error");
  const botonGuardar = dialogo.querySelector("[data-pm='guardar']");
  const textoBoton = config.textoBoton || "Guardar";
  dialogo.querySelector(".pm__title").textContent = config.titulo;
  botonGuardar.textContent = textoBoton;
  if (config.descripcion) {
    const lead = dialogo.querySelector(".pm__lead");
    lead.textContent = config.descripcion;
    lead.hidden = false;
  }

  const contenedor = dialogo.querySelector(".pm__campos");
  for (const c of config.campos) {
    const campo = document.createElement("div");
    campo.className = "pm__field" + (c.tipo === "checkbox" ? " pm__check" : "");
    const etiqueta = document.createElement("label");
    etiqueta.htmlFor = `f-${c.nombre}`;
    etiqueta.textContent = c.etiqueta + (c.requerido ? " *" : "");

    let control;
    if (c.tipo === "textarea") {
      control = document.createElement("textarea");
    } else if (c.tipo === "select") {
      control = document.createElement("select");
      for (const o of c.opciones || []) {
        const opcion = document.createElement("option");
        opcion.value = o.valor;
        opcion.textContent = o.texto;
        control.appendChild(opcion);
      }
    } else {
      control = document.createElement("input");
      control.type = c.tipo || "text";
      if (c.min !== undefined) control.min = c.min;
      if (c.max !== undefined) control.max = c.max;
    }
    control.id = `f-${c.nombre}`;
    control.name = c.nombre;
    if (c.maxlength && ["text", "textarea", undefined].includes(c.tipo)) control.maxLength = c.maxlength;
    if (c.placeholder) control.placeholder = c.placeholder;
    if (c.tipo === "checkbox") control.checked = Boolean(c.valor);
    else if (c.valor !== undefined && c.valor !== null) control.value = c.valor;

    if (c.tipo === "checkbox") campo.append(control, etiqueta);
    else campo.append(etiqueta, control);
    if (c.ayuda) {
      const ayuda = document.createElement("span");
      ayuda.className = "pm__hint";
      ayuda.textContent = c.ayuda;
      campo.appendChild(ayuda);
    }
    contenedor.appendChild(campo);
  }

  // Se cierra Y se quita del DOM explícitamente: no basta con escuchar el evento "close",
  // que algunos navegadores no disparan, y los modales viejos duplicarían los id de los campos.
  const cerrar = () => {
    if (dialogo.open) dialogo.close();
    dialogo.remove();
  };
  dialogo.querySelector("[data-pm='cancelar']").addEventListener("click", cerrar);
  dialogo.addEventListener("close", cerrar);
  dialogo.addEventListener("cancel", () => setTimeout(cerrar)); // tecla Esc

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    cajaError.hidden = true;

    const valores = {};
    for (const c of config.campos) {
      const control = formulario.elements[c.nombre];
      if (c.tipo === "checkbox") { valores[c.nombre] = control.checked; continue; }
      const texto = control.value.trim();
      if (!texto) {
        if (c.requerido) {
          cajaError.textContent = `Completa el campo "${c.etiqueta}".`;
          cajaError.hidden = false;
          control.focus();
          return;
        }
        continue;
      }
      valores[c.nombre] = c.tipo === "number" ? Number(texto) : texto;
    }

    botonGuardar.disabled = true;
    botonGuardar.textContent = "Guardando…";
    try {
      const resultado = await config.onEnviar(valores);
      if (resultado && resultado.ok) cerrar();
      else {
        cajaError.textContent = (resultado && resultado.error) || "No se pudo guardar.";
        cajaError.hidden = false;
      }
    } catch (error) {
      cajaError.textContent = "No se pudo conectar con el servidor.";
      cajaError.hidden = false;
    } finally {
      botonGuardar.disabled = false;
      botonGuardar.textContent = textoBoton;
    }
  });

  document.body.appendChild(dialogo);
  dialogo.showModal();
  return dialogo;
}
