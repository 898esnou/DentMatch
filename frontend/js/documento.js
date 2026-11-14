/**
 * documento.js
 * ---------------------------------------------------------------------
 * Validación del documento de identidad en el navegador (misma lógica que
 * app/documentos.py). Es solo para avisar rápido: el backend siempre vuelve
 * a validar.
 *
 * - "rut":        RUT chileno, con dígito verificador (módulo 11)
 * - "extranjero": pasaporte u otro documento (5 a 16 letras/números)
 * ---------------------------------------------------------------------
 */

function calcularDvRut(cuerpo) {
  let suma = 0;
  let multiplicador = 2;
  for (const digito of cuerpo.split("").reverse()) {
    suma += Number(digito) * multiplicador;
    multiplicador = multiplicador === 7 ? 2 : multiplicador + 1;
  }
  const resto = 11 - (suma % 11);
  if (resto === 11) return "0";
  if (resto === 10) return "K";
  return String(resto);
}

/** Devuelve un texto de error, o null si el documento es válido. */
function validarDocumento(tipo, texto) {
  if (tipo === "extranjero") {
    const limpio = texto.replace(/[\s-]/g, "").toUpperCase();
    if (!/^[A-Z0-9]+$/.test(limpio)) return "El documento extranjero solo puede tener letras y números.";
    if (limpio.length < 5 || limpio.length > 16) return "El documento extranjero debe tener entre 5 y 16 caracteres.";
    return null;
  }
  const limpio = texto.replace(/[.\s-]/g, "").toUpperCase();
  if (!/^\d{7,8}[0-9K]$/.test(limpio)) return "El RUT no tiene un formato válido (ejemplo: 12.345.678-5).";
  if (calcularDvRut(limpio.slice(0, -1)) !== limpio.slice(-1)) return "El RUT no es válido: el dígito verificador no coincide.";
  return null;
}

/**
 * Da formato de RUT mientras se escribe: "123456785" -> "12.345.678-5".
 * Solo deja dígitos (y la K, únicamente al final) y corta en 9 caracteres.
 */
function formatearRutAlEscribir(texto) {
  let limpio = texto.replace(/[^0-9kK]/g, "").toUpperCase();
  limpio = limpio.replace(/K(?=.)/g, "").slice(0, 9); // la K solo puede ser el último carácter
  if (limpio.length <= 1) return limpio;
  const cuerpo = limpio.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${cuerpo}-${limpio.slice(-1)}`;
}

/** Conecta un <input> para que se formatee solo mientras la persona escribe el RUT. */
function activarFormatoRut(input, estaActivo = () => true) {
  input.addEventListener("input", () => {
    if (!estaActivo()) return;
    const cursor = input.selectionStart ?? input.value.length;
    const antes = input.value.slice(0, cursor).replace(/[^0-9kK]/g, "").length; // caracteres útiles antes del cursor
    input.value = formatearRutAlEscribir(input.value);
    let pos = 0, vistos = 0;
    while (pos < input.value.length && vistos < antes) {
      if (/[0-9K]/.test(input.value[pos])) vistos++;
      pos++;
    }
    input.setSelectionRange(pos, pos);
  });
}
