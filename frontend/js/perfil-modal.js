/**
 * perfil-modal.js
 * ---------------------------------------------------------------------
 * Formulario "Editar mi perfil" para estudiante y paciente.
 * - Cualquier elemento con data-accion="editar-perfil" lo abre.
 * - Al guardar dispara el evento "perfil-actualizado" en document, para
 *   que cada dashboard vuelva a dibujar sus datos.
 * Requiere session.js y api.js cargados antes.
 * ---------------------------------------------------------------------
 */

const CAMPOS_PERFIL = {
  estudiante: [
    { nombre: "universidad", etiqueta: "Universidad", tipo: "input", max: 150, ejemplo: "Universidad de Chile" },
    { nombre: "comuna_atencion", etiqueta: "Comuna de atención", tipo: "input", max: 100, ejemplo: "Recoleta" },
    { nombre: "disponibilidad", etiqueta: "Disponibilidad", tipo: "textarea", ejemplo: "Martes y jueves por la mañana" },
  ],
  paciente: [
    { nombre: "comuna", etiqueta: "Tu comuna", tipo: "input", max: 100, ejemplo: "Providencia" },
    { nombre: "tratamiento_requerido", etiqueta: "¿Qué tratamiento necesitas?", tipo: "input", max: 150, ejemplo: "Limpieza dental, endodoncia…" },
    { nombre: "descripcion", etiqueta: "Cuéntanos qué sientes o necesitas", tipo: "textarea", ejemplo: "Me duele una muela al masticar…" },
    { nombre: "disponibilidad", etiqueta: "Disponibilidad", tipo: "textarea", ejemplo: "Lunes a viernes después de las 17:00" },
  ],
};

function crearModalPerfil() {
  const dialogo = document.createElement("dialog");
  dialogo.className = "pm";
  dialogo.id = "modal-perfil"; // único: abrirFormulario() crea otros .pm y no deben confundirse
  dialogo.innerHTML = `
    <form class="pm__form" method="dialog" novalidate>
      <h2 class="pm__title">Editar mi perfil</h2>
      <p class="pm__lead">Esta información se usa para encontrar coincidencias entre estudiantes y pacientes.</p>
      <p class="pm__error" role="alert" hidden></p>
      <div class="pm__campos"></div>
      <div class="pm__actions">
        <button type="button" class="btn btn--ghost" data-pm="cancelar">Cancelar</button>
        <button type="submit" class="btn btn--primary" data-pm="guardar">Guardar cambios</button>
      </div>
    </form>`;
  document.body.appendChild(dialogo);
  dialogo.querySelector("[data-pm='cancelar']").addEventListener("click", () => dialogo.close());
  return dialogo;
}

function valorInicial(valor) {
  return valor && valor !== "Por definir" ? valor : "";
}

function dibujarCampos(contenedor, campos, datos) {
  contenedor.innerHTML = "";
  contenedor.style.cssText = "display:flex;flex-direction:column;gap:14px";
  for (const c of campos) {
    const campo = document.createElement("div");
    campo.className = "pm__field";

    const etiqueta = document.createElement("label");
    etiqueta.htmlFor = `pm-${c.nombre}`;
    etiqueta.textContent = c.etiqueta;

    const control = document.createElement(c.tipo);
    control.id = `pm-${c.nombre}`;
    control.name = c.nombre;
    control.placeholder = c.ejemplo;
    if (c.max) control.maxLength = c.max;
    control.value = valorInicial(datos[c.nombre]);

    campo.append(etiqueta, control);
    contenedor.appendChild(campo);
  }
}

async function abrirEditarPerfil() {
  const rol = obtenerRol();
  const campos = CAMPOS_PERFIL[rol];
  if (!campos) return;

  const dialogo = document.getElementById("modal-perfil") || crearModalPerfil();
  const formulario = dialogo.querySelector("form");
  const cajaError = dialogo.querySelector(".pm__error");
  const botonGuardar = dialogo.querySelector("[data-pm='guardar']");
  cajaError.hidden = true;

  const respuesta = await apiFetch("/api/perfil");
  if (!respuesta.ok) return;
  const datos = (await respuesta.json())[rol] || {};
  dibujarCampos(dialogo.querySelector(".pm__campos"), campos, datos);

  formulario.onsubmit = async (evento) => {
    evento.preventDefault();
    cajaError.hidden = true;
    botonGuardar.disabled = true;
    botonGuardar.textContent = "Guardando…";

    // Solo se envían los campos que tienen texto: un campo vacío no borra lo guardado.
    const cuerpo = {};
    for (const c of campos) {
      const texto = formulario.elements[c.nombre].value.trim();
      if (texto) cuerpo[c.nombre] = texto;
    }

    try {
      const guardado = await apiFetch(`/api/perfil/${rol}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo),
      });
      if (guardado.ok) {
        dialogo.close();
        document.dispatchEvent(new CustomEvent("perfil-actualizado", { detail: await guardado.json() }));
      } else {
        cajaError.textContent = "No se pudo guardar el perfil. Revisa los datos e inténtalo de nuevo.";
        cajaError.hidden = false;
      }
    } catch (error) {
      cajaError.textContent = "No se pudo conectar con el servidor.";
      cajaError.hidden = false;
    } finally {
      botonGuardar.disabled = false;
      botonGuardar.textContent = "Guardar cambios";
    }
  };

  dialogo.showModal();
}

document.addEventListener("click", (e) => {
  if (e.target.closest("[data-accion='editar-perfil']")) abrirEditarPerfil();
});
