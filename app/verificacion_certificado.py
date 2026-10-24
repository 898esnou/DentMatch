"""
Verificación AUTOMÁTICA del certificado de alumno regular (lectura del QR).

Certificados de la Universidad Andrés Bello (UNAB). El QR trae una URL del tipo
    https://certificados.unab.cl/qr.php?f=<folio>&i=<id alumno>
que muestra una página oficial con RUT, nombre, carrera, período, estado
("ES ALUMNO") y la fecha hasta la que el certificado es válido.

Resultado de verificar_automaticamente:
- None: no se pudo decidir (sin QR legible, QR de otro emisor, página de la UNAB
  caída o con otro formato, nombre distinto). El certificado queda "En
  Verificación" y lo resuelve un administrador a mano.
- ResultadoVerificacion(aprobada=True): el RUT coincide con la cuenta, la UNAB
  confirma que es alumno regular de Odontología y el certificado es del semestre
  en curso (la vigencia es SEMESTRAL, ver app/vigencia.py; no se usa el "Válido
  hasta" de la UNAB, que dura unos 60 días).
- ResultadoVerificacion(aprobada=False, motivo): la UNAB respondió y los datos
  no sirven (otro RUT, no es alumno, no es Odontología, certificado de un semestre
  anterior).

Seguridad (SSRF): el servidor NUNCA visita la URL tal cual viene en el QR. Solo
se rescatan el folio y el id (solo dígitos) y se arma la URL con el dominio
oficial fijo; las redirecciones solo se siguen dentro de ese mismo dominio.
"""
import html
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Optional

from app.vigencia import fin_de_semestre

DOMINIO_OFICIAL = "certificados.unab.cl"
URL_VERIFICACION = f"https://{DOMINIO_OFICIAL}/qr.php"
TIMEOUT_SEGUNDOS = 10
MAX_BYTES_PAGINA = 500_000
MAX_REDIRECCIONES = 3
CARRERA_PERMITIDA = "ODONTOLOG"  # ODONTOLOGÍA, sin depender de la tilde


@dataclass
class ResultadoVerificacion:
    aprobada: bool
    motivo: Optional[str] = None  # explicación si no se aprobó
    fecha_emision: Optional[date] = None  # emisión según la UNAB (define el semestre)


def _sin_acentos(texto: str) -> str:
    base = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in base if unicodedata.category(c) != "Mn").upper()


def _palabras(texto: str):
    return set(re.findall(r"[A-Z]+", _sin_acentos(texto)))


def _limpiar_rut(texto: str) -> str:
    return re.sub(r"[^0-9K]", "", _sin_acentos(texto))


def _leer_qr(contenido: bytes, tipo_contenido: str) -> Optional[str]:
    """Devuelve el texto del primer QR legible, o None."""
    try:
        import cv2
        import numpy as np

        if tipo_contenido == "application/pdf":
            import pymupdf

            with pymupdf.open(stream=contenido, filetype="pdf") as pdf:
                imagenes = []
                for pagina in list(pdf)[:3]:
                    pix = pagina.get_pixmap(dpi=250)
                    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
                    imagenes.append(cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR))
        else:
            img = cv2.imdecode(np.frombuffer(contenido, np.uint8), cv2.IMREAD_COLOR)
            imagenes = [img] if img is not None else []

        detector = cv2.QRCodeDetector()
        for img in imagenes:
            texto, _, _ = detector.detectAndDecode(img)
            if texto:
                return texto
    except Exception:
        return None
    return None


def _url_oficial(texto_qr: str) -> Optional[str]:
    """Reconstruye la URL de verificación solo si el QR es del dominio oficial."""
    try:
        partes = urllib.parse.urlsplit(texto_qr.strip())
        if partes.scheme not in ("http", "https") or (partes.hostname or "").lower() != DOMINIO_OFICIAL:
            return None
        consulta = urllib.parse.parse_qs(partes.query)
        folio = (consulta.get("f") or [""])[0]
        alumno = (consulta.get("i") or [""])[0]
    except ValueError:
        return None
    if not (folio.isdigit() and alumno.isdigit() and len(folio) <= 12 and len(alumno) <= 12):
        return None
    return f"{URL_VERIFICACION}?{urllib.parse.urlencode({'f': folio, 'i': alumno})}"


class _RedireccionSoloOficial(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destino = urllib.parse.urljoin(req.full_url, newurl)
        partes = urllib.parse.urlsplit(destino)
        if partes.scheme != "https" or (partes.hostname or "").lower() != DOMINIO_OFICIAL:
            raise urllib.error.URLError("redirección fuera del dominio oficial")
        return super().redirect_request(req, fp, code, msg, headers, destino)


def _descargar_pagina(url: str) -> Optional[str]:
    opener = urllib.request.build_opener(_RedireccionSoloOficial())
    opener.addheaders = [("User-Agent", "DentMatch-verificacion/1.0")]
    # urllib sigue hasta 10 redirecciones; con el dominio fijo no es un riesgo.
    try:
        with opener.open(url, timeout=TIMEOUT_SEGUNDOS) as respuesta:
            if (urllib.parse.urlsplit(respuesta.geturl()).hostname or "").lower() != DOMINIO_OFICIAL:
                return None
            crudo = respuesta.read(MAX_BYTES_PAGINA)
        return crudo.decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _extraer_datos(pagina: str) -> Dict[str, str]:
    """Lee los pares <dt>Campo:</dt><dd>Valor</dd> de 'Datos del certificado'."""
    datos = {}
    for campo, valor in re.findall(r"<dt>\s*(.*?)\s*</dt>\s*<dd>\s*(.*?)\s*</dd>", pagina, re.S | re.I):
        campo = _sin_acentos(html.unescape(re.sub(r"<[^>]+>", "", campo))).strip(" :")
        datos[campo] = html.unescape(re.sub(r"<[^>]+>", "", valor)).strip()
    return datos


def evaluar_datos(datos: Dict[str, str], nombre_completo: str, documento: str, hoy: Optional[date] = None):
    """Decide con los datos de la página de la UNAB. Función pura (testeable)."""
    hoy = hoy or date.today()
    rut_cert = _limpiar_rut(datos.get("RUT", ""))
    estado = _sin_acentos(datos.get("ESTADO", ""))
    if not rut_cert or not estado:
        return None  # la página no tiene el formato esperado: que lo vea un admin

    if rut_cert != _limpiar_rut(documento):
        return ResultadoVerificacion(False, "El RUT del certificado no coincide con el de tu cuenta")
    if estado != "ES ALUMNO":
        return ResultadoVerificacion(False, "La universidad indica que no eres alumno regular")
    if CARRERA_PERMITIDA not in _sin_acentos(datos.get("CARRERA", "")):
        return ResultadoVerificacion(False, "El certificado no corresponde a la carrera de Odontología")

    try:
        emision = datetime.strptime(datos.get("FECHA EMISION", ""), "%d-%m-%Y").date()
    except ValueError:
        return None  # sin fecha de emisión legible: revisión manual
    if emision > hoy:
        return None  # fecha futura: algo raro, que lo vea un admin
    if fin_de_semestre(emision) < hoy:
        return ResultadoVerificacion(False, "El certificado es de un semestre anterior: sube uno emitido este semestre")

    # El RUT ya coincide; el nombre solo se usa para detectar cuentas con otro nombre.
    nombre_cert = _palabras(f"{datos.get('NOMBRE', '')} {datos.get('APELLIDOS', '')}")
    if not _palabras(nombre_completo) or not _palabras(nombre_completo) <= nombre_cert:
        return None  # puede ser un apodo o un orden distinto: lo decide un admin

    return ResultadoVerificacion(True, fecha_emision=emision)


def verificar_automaticamente(
    contenido: bytes, tipo_contenido: str, nombre_completo: str, documento: str
) -> Optional[ResultadoVerificacion]:
    """None = no hay verificación automática posible: revisión manual."""
    texto_qr = _leer_qr(contenido, tipo_contenido)
    if not texto_qr:
        return None
    url = _url_oficial(texto_qr)
    if not url:
        return None
    pagina = _descargar_pagina(url)
    if not pagina:
        return None
    return evaluar_datos(_extraer_datos(pagina), nombre_completo, documento)
