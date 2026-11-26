"""
Comunas vecinas del Gran Santiago, para que el matching por ubicación premie la cercanía.

Cada comuna lista las comunas con las que limita. La tabla es una aproximación hecha a mano
(no usa mapas ni coordenadas) y se completa sola en ambos sentidos: basta con anotar cada
par una vez. Para agregar o corregir una comuna se edita `_LIMITES`.
"""
from typing import Dict, FrozenSet, Optional

from app.texto import normalizar as _norm

_LIMITES = {
    "Santiago": ["Estación Central", "Quinta Normal", "Independencia", "Recoleta", "Providencia", "Ñuñoa",
                 "San Joaquín", "San Miguel", "Pedro Aguirre Cerda"],
    "Estación Central": ["Quinta Normal", "Lo Prado", "Pudahuel", "Maipú", "Cerrillos", "Pedro Aguirre Cerda"],
    "Quinta Normal": ["Lo Prado", "Cerro Navia", "Renca", "Independencia"],
    "Lo Prado": ["Cerro Navia", "Pudahuel"],
    "Cerro Navia": ["Renca", "Pudahuel"],
    "Renca": ["Independencia", "Conchalí", "Quilicura", "Pudahuel"],
    "Independencia": ["Recoleta", "Conchalí"],
    "Conchalí": ["Recoleta", "Huechuraba", "Quilicura"],
    "Recoleta": ["Huechuraba", "Providencia", "Vitacura"],
    "Huechuraba": ["Quilicura", "Vitacura", "Lo Barnechea", "Colina"],
    "Quilicura": ["Pudahuel", "Lampa"],
    "Providencia": ["Ñuñoa", "Las Condes", "Vitacura"],
    "Las Condes": ["Vitacura", "Lo Barnechea", "La Reina", "Ñuñoa", "Peñalolén"],
    "Vitacura": ["Lo Barnechea"],
    "Ñuñoa": ["La Reina", "Peñalolén", "Macul", "San Joaquín"],
    "La Reina": ["Peñalolén"],
    "Peñalolén": ["Macul", "La Florida"],
    "Macul": ["La Florida", "San Joaquín"],
    "San Joaquín": ["San Miguel", "La Granja", "Pedro Aguirre Cerda"],
    "San Miguel": ["Pedro Aguirre Cerda", "La Cisterna"],
    "Pedro Aguirre Cerda": ["Lo Espejo", "Cerrillos"],
    "Lo Espejo": ["Cerrillos", "La Cisterna", "El Bosque"],
    "Cerrillos": ["Maipú"],
    "Maipú": ["Pudahuel", "Padre Hurtado"],
    "La Cisterna": ["El Bosque", "San Ramón", "La Granja"],
    "San Ramón": ["La Granja"],
    "La Granja": ["La Florida", "La Pintana"],
    "La Florida": ["La Pintana", "Puente Alto"],
    "La Pintana": ["El Bosque", "San Bernardo", "Puente Alto"],
    "El Bosque": ["San Bernardo"],
    "Puente Alto": ["Pirque", "San José de Maipo"],
    # Periferia del Gran Santiago y comunas cercanas fuera de la ciudad
    "Pirque": ["San José de Maipo", "Buin"],
    "San Bernardo": ["Calera de Tango", "Buin", "Paine"],
    "Calera de Tango": ["Padre Hurtado", "Talagante", "Buin"],
    "Padre Hurtado": ["Peñaflor", "Talagante", "Calera de Tango"],
    "Peñaflor": ["Talagante"],
    "Talagante": ["El Monte", "Isla de Maipo", "Calera de Tango"],
    "El Monte": ["Isla de Maipo", "Peñaflor"],
    "Buin": ["Paine"],
    "Pudahuel": ["Curacaví", "Lampa"],
    "Colina": ["Lampa", "Til Til"],
    "Lampa": ["Til Til"],
    "Curacaví": ["María Pinto", "Lampa"],
    "María Pinto": ["Melipilla", "Curacaví"],
    "Melipilla": ["Isla de Maipo", "Talagante"],
}


def _construir() -> Dict[str, FrozenSet[str]]:
    vecinas: Dict[str, set] = {}
    for comuna, lista in _LIMITES.items():
        for otra in lista:
            vecinas.setdefault(_norm(comuna), set()).add(_norm(otra))
            vecinas.setdefault(_norm(otra), set()).add(_norm(comuna))
    return {k: frozenset(v) for k, v in vecinas.items()}


VECINAS = _construir()


def saltos_entre(a: Optional[str], b: Optional[str], maximo: int = 6) -> Optional[int]:
    """Cuántas comunas hay que cruzar para ir de `a` a `b` (0 = la misma, 1 = vecinas...).

    Devuelve None si alguna de las dos no está en la tabla o si están a más de `maximo` saltos.
    """
    origen, destino = _norm(a), _norm(b)
    if origen == destino:
        return 0
    if origen not in VECINAS or destino not in VECINAS:
        return None
    visitadas, frontera = {origen}, {origen}
    for salto in range(1, maximo + 1):
        frontera = {v for c in frontera for v in VECINAS[c]} - visitadas
        if destino in frontera:
            return salto
        if not frontera:
            break
        visitadas |= frontera
    return None


def son_vecinas(a: Optional[str], b: Optional[str]) -> bool:
    """True si las dos comunas limitan entre sí (sin importar tildes ni mayúsculas)."""
    return _norm(b) in VECINAS.get(_norm(a), frozenset())
