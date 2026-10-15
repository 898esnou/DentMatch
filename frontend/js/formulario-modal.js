/**
 * formulario-modal.js
 * ---------------------------------------------------------------------
 * Utilidades compartidas por los portales:
 * - abrirFormulario({...}): modal con campos y envío (usa estilos .pm)
 * - mostrarAviso(texto, esError): mensaje flotante breve
 * - apiJson(ruta, metodo, cuerpo): llamada a la API con JSON
 * Requiere session.js y api.js cargados antes, y utils.js (esc).
 * ---------------------------------------------------------------------
 */

function mostrarAviso(texto, esError = false) {
  const aviso = document.createElement("div");
  aviso.className = "aviso" + (esError ? " aviso--error" : "");
  aviso.setAttribute("role", "status");
  aviso.textContent = texto;
  document.body.appendChild(aviso);
  setTimeout(() => aviso.remove(), 3500);
}

/** Llama a la API con JSON. Devuelve { ok, status, data } (data puede ser null). */
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

/** Convierte el error de la API (detail de FastAPI) en un texto para mostrar. */
function textoDeError(resultado, porDefecto = "No se pudo completar la acción.") {
  const detalle = resultado && resultado.data && resultado.data.detail;
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle) && detalle.length) {
    const d = detalle[0];
    const campo = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
    return campo ? `${campo}: ${d.msg}` : d.msg;
  }
  return porDefecto;
}

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
      <div class="pm__campos" style="display:flex;flex-direction:column;gap:14px"></div>
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
