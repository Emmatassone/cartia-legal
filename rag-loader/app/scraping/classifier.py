"""Clasificacion de normas por materia: define la carpeta destino y el fuero.

Precedencia:
  1. mapa curado de normas conocidas (LCT, CCCyC, codigos procesales, etc.): las
     normas mas consultadas no pueden depender de que un keyword aparezca en el titulo.
  2. reglas por keywords sobre titulo_resumido + titulo_sumario + organismo.
  3. `otros`: queda en su propia carpeta para revision, nunca se descarta.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum

from cartia_shared import Fuero

from .catalog import CatalogEntry


class Categoria(StrEnum):
    """Carpeta destino dentro de DOCUMENTS_DIR."""

    LABORAL = "laboral"
    CIVIL_COMERCIAL = "civil-comercial"
    CONSUMO = "consumo"
    PROCESAL = "procesal"
    PENAL = "penal"
    TRIBUTARIO = "tributario"
    PREVISIONAL = "previsional"
    ADMINISTRATIVO = "administrativo"
    CONSTITUCIONAL = "constitucional"
    SOCIETARIO = "societario"
    COMERCIAL = "comercial"
    FAMILIA = "familia"
    AMBIENTAL = "ambiental"
    SALUD = "salud"
    MIGRATORIO = "migratorio"
    DATOS_PERSONALES = "datos-personales"
    PROPIEDAD_INTELECTUAL = "propiedad-intelectual"
    OTROS = "otros"


CATEGORIA_FUERO: dict[Categoria, Fuero] = {
    Categoria.LABORAL: Fuero.LABORAL,
    Categoria.CIVIL_COMERCIAL: Fuero.CIVIL,
    Categoria.CONSUMO: Fuero.CONSUMIDOR,
    Categoria.PROCESAL: Fuero.PROCESAL,
    Categoria.PENAL: Fuero.PENAL,
    Categoria.TRIBUTARIO: Fuero.TRIBUTARIO,
    Categoria.PREVISIONAL: Fuero.PREVISIONAL,
    Categoria.ADMINISTRATIVO: Fuero.ADMINISTRATIVO,
    Categoria.CONSTITUCIONAL: Fuero.CONSTITUCIONAL,
    Categoria.SOCIETARIO: Fuero.SOCIETARIO,
    Categoria.COMERCIAL: Fuero.COMERCIAL,
    Categoria.FAMILIA: Fuero.FAMILIA,
    Categoria.AMBIENTAL: Fuero.AMBIENTAL,
    Categoria.SALUD: Fuero.OTRO,
    Categoria.MIGRATORIO: Fuero.MIGRATORIO,
    Categoria.DATOS_PERSONALES: Fuero.DATOS_PERSONALES,
    Categoria.PROPIEDAD_INTELECTUAL: Fuero.PROPIEDAD_INTELECTUAL,
    Categoria.OTROS: Fuero.OTRO,
}

# (tipo de norma normalizado, numero) -> categoria. Los numeros van sin puntos.
_NORMAS_CONOCIDAS: dict[tuple[str, str], Categoria] = {
    ("ley", "20744"): Categoria.LABORAL,  # Ley de Contrato de Trabajo
    ("ley", "24557"): Categoria.LABORAL,  # Riesgos del Trabajo
    ("ley", "24013"): Categoria.LABORAL,  # Empleo (registracion, multas)
    ("ley", "23551"): Categoria.LABORAL,  # Asociaciones Sindicales
    ("ley", "25877"): Categoria.LABORAL,  # Reforma laboral 2004
    ("ley", "27555"): Categoria.LABORAL,  # Teletrabajo
    ("ley", "14250"): Categoria.LABORAL,  # Convenios colectivos (historica)
    ("ley", "24241"): Categoria.PREVISIONAL,  # SIPA
    ("ley", "24240"): Categoria.CONSUMO,  # Defensa del Consumidor
    ("ley", "26994"): Categoria.CIVIL_COMERCIAL,  # Codigo Civil y Comercial
    ("ley", "26862"): Categoria.CIVIL_COMERCIAL,  # Identidad de genero
    ("ley", "17454"): Categoria.PROCESAL,  # CPCCN
    ("ley", "19550"): Categoria.SOCIETARIO,  # Ley General de Sociedades
    ("ley", "24522"): Categoria.COMERCIAL,  # Concursos y Quiebras
    ("ley", "25156"): Categoria.COMERCIAL,  # Defensa de la Competencia
    ("ley", "26831"): Categoria.COMERCIAL,  # Mercado de Capitales
    ("ley", "11179"): Categoria.PENAL,  # Codigo Penal (t.o.)
    ("ley", "23737"): Categoria.PENAL,  # Estupefacientes
    ("ley", "26388"): Categoria.PENAL,  # Delitos informaticos
    ("ley", "27401"): Categoria.PENAL,  # Responsabilidad penal personas juridicas
    ("ley", "11683"): Categoria.TRIBUTARIO,  # Procedimiento tributario (t.o.)
    ("ley", "20628"): Categoria.TRIBUTARIO,  # Impuesto a las Ganancias (t.o.)
    ("ley", "20631"): Categoria.TRIBUTARIO,  # IVA (t.o.)
    ("ley", "22415"): Categoria.TRIBUTARIO,  # Codigo Aduanero
    ("ley", "19549"): Categoria.ADMINISTRATIVO,  # Procedimientos administrativos
    ("ley", "25326"): Categoria.DATOS_PERSONALES,
    ("ley", "25871"): Categoria.MIGRATORIO,
    ("ley", "25675"): Categoria.AMBIENTAL,  # Presupuestos minimos ambiente
    ("ley", "26331"): Categoria.AMBIENTAL,  # Bosques nativos
    ("ley", "26639"): Categoria.AMBIENTAL,  # Glaciares
    ("ley", "26657"): Categoria.SALUD,  # Salud mental
    ("ley", "23660"): Categoria.SALUD,  # Obras sociales
    ("ley", "27610"): Categoria.SALUD,  # IVE
    ("ley", "11723"): Categoria.PROPIEDAD_INTELECTUAL,
    ("ley", "24417"): Categoria.FAMILIA,  # Violencia familiar
    ("ley", "26485"): Categoria.FAMILIA,  # Proteccion integral a las mujeres
    ("ley", "26061"): Categoria.FAMILIA,  # Proteccion integral NNyA
}

# Orden importa: la primera regla que matchea gana. Las materias mas especificas van
# antes que las generales (consumo antes que civil, procesal antes que administrativo).
_REGLAS: list[tuple[Categoria, str]] = [
    (Categoria.CONSUMO, r"consumidor|defensa del consumidor|relacion de consumo"),
    (Categoria.PROCESAL, r"codigo procesal|procesal|procedimiento judicial|competencia"),
    (Categoria.LABORAL, r"laboral|trabajo|trabajador|empleador|sindic|gremial|despido"),
    (Categoria.PREVISIONAL, r"previsional|jubilaci|pension|anses|\bsipa\b"),
    (Categoria.PENAL, r"penal|delito|criminal|estupefaciente|narcotrafico"),
    (
        Categoria.TRIBUTARIO,
        r"tributari|impositiv|impuesto|fiscal|aduan|\bafip\b|\barca\b|\biva\b|ganancias",
    ),
    (Categoria.DATOS_PERSONALES, r"datos personales|habeas data|privacidad"),
    (Categoria.MIGRATORIO, r"migraci|migratori|extranjer|residencia"),
    (Categoria.AMBIENTAL, r"ambient|bosque|glaciar|residuo|contaminaci|humedal"),
    (Categoria.SALUD, r"salud|sanitari|medic|hospital|vacuna|discapacidad"),
    (Categoria.PROPIEDAD_INTELECTUAL, r"propiedad intelectual|marca|patente|derecho de autor"),
    (Categoria.FAMILIA, r"familia|alimentos|divorcio|adopcion|filacion|matrimonio|violencia"),
    (Categoria.SOCIETARIO, r"sociedad|societari|\bs\.?a\.?\b|\bsrl\b|\bsas\b"),
    (Categoria.COMERCIAL, r"comercial|concurso|quiebra|cheque|fideicomiso|mercado de capitales"),
    (Categoria.CONSTITUCIONAL, r"constitucional|amparo|habeas corpus|derechos humanos"),
    (Categoria.ADMINISTRATIVO, r"administrativ|funcion publica|contrataciones|expropiaci"),
    (Categoria.CIVIL_COMERCIAL, r"civil|comercial|codigo civil|obligaciones|contratos"),
]


def _normalize(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    )


def classify(entry: CatalogEntry) -> Categoria:
    tipo = _normalize(entry.tipo_norma)
    numero = entry.numero_normalizado
    if numero and (tipo, numero) in _NORMAS_CONOCIDAS:
        return _NORMAS_CONOCIDAS[(tipo, numero)]

    haystack = _normalize(
        " ".join(
            part
            for part in [
                entry.titulo_resumido,
                entry.titulo_sumario or "",
                entry.organismo_origen or "",
                entry.clase_norma or "",
            ]
            if part
        )
    )
    for categoria, pattern in _REGLAS:
        if re.search(pattern, haystack):
            return categoria
    return Categoria.OTROS
