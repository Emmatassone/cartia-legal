"""Clasificacion de normas por materia: define la carpeta destino y el fuero.

Precedencia:
  1. mapa curado de normas conocidas (LCT, CCCyC, codigos procesales, etc.): las
     normas mas consultadas no pueden depender de que un keyword aparezca en el titulo.
  2. `ruido`: actos administrativos individuales (designaciones, condecoraciones,
     decretos secretos de personal, promulgaciones). No aportan a un RAG juridico y
     el pipeline los saltea por default (`--incluir-ruido` los recupera).
  3. reglas por keywords sobre titulo_resumido + titulo_sumario + organismo.
  4. mapa del titulo_sumario: el topico generico que InfoLEG asigna a mano; es mas
     grosero que el titulo (dice el ministerio, no la materia), por eso va despues.
  5. reglas por keywords sobre texto_resumido (la bajada descriptiva del catalogo;
     salva normas historicas con titulos cripticos tipo "ESTABLECENSE").
  6. `otros`: queda en su propia carpeta para revision, nunca se descarta.
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
    INTERNACIONAL = "internacional"
    RUIDO = "ruido"
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
    Categoria.INTERNACIONAL: Fuero.INTERNACIONAL,
    Categoria.RUIDO: Fuero.OTRO,
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

# Sumarios (topico generico curado por InfoLEG) que son actos individuales sin valor
# para un corpus de consulta: personal, protocolo y beneficios a particulares.
# Van normalizados (sin acentos, minuscula) y se comparan por igualdad.
_SUMARIOS_RUIDO = {
    "decretos secretos y reservados",
    "condecoraciones",
    "homenajes",
    "huespedes oficiales",
    "subsidio estatal",
    "ferias internacionales",
    "exencion de gravamenes",
}

# Titulos que delatan un acto individual aunque el sumario venga vacio. Se buscan
# al inicio del titulo normalizado: son formulas fijas del Boletin Oficial.
_REGEX_RUIDO_TITULO = re.compile(
    r"^(designacion|promociones?|cesantia|nombramiento|renuncia|becas?|subsidio|"
    r"indulto|conmutacion|naturalizacion|homenaje|condecoracion|huesped|"
    r"salida del pais|pension graciable|ley n.{0,12}su promulgacion)\b"
)

# InfoLEG marca las normas agotadas en la bajada ("OBJETO CUMPLIDO-..."): cumplieron
# su finalidad sin ser derogadas, asi que el filtro de vigentes no las alcanza.
_REGEX_RUIDO_RESUMEN = re.compile(r"^(objeto cumplido|ambito temporal cumplido)\b")

# Mapa del titulo_sumario a materia. Se aplica DESPUES de las reglas por keywords:
# el sumario suele nombrar el organismo ("MINISTERIO DE ECONOMIA"), no la materia,
# asi que solo decide cuando el titulo no dijo nada util.
_REGLAS_SUMARIO: list[tuple[Categoria, str]] = [
    (
        Categoria.INTERNACIONAL,
        r"tratados internacionales|^acuerdos$|^convenios$|servicio exterior|relaciones exteriores",
    ),
    (Categoria.LABORAL, r"trabajo|empleo"),
    (Categoria.PREVISIONAL, r"seguridad social|beneficios previsionales"),
    (Categoria.TRIBUTARIO, r"fisco|impuestos|aduana"),
    (Categoria.PROCESAL, r"^justicia$|ministerio publico|poder judicial|magistratura"),
    (Categoria.MIGRATORIO, r"migraciones"),
    (Categoria.SALUD, r"salud"),
    (Categoria.AMBIENTAL, r"ambiente|recursos naturales"),
    (
        Categoria.ADMINISTRATIVO,
        r"ministerio|jefatura de gabinete|presidencia|poder ejecutivo|estado nacional|"
        r"administracion publica|secretaria|personal militar|policia|banco central|"
        r"bienes del estado|inmuebles|contratos|presupuesto|servicios publicos|"
        r"transporte|hidrocarburos|radiodifusion|procedimientos administrativos|"
        r"educacion|defensa|seguridad|interior|agricultura|cultura|planificacion",
    ),
]

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
    # "convenio" solo no alcanza: los convenios colectivos son laborales.
    (Categoria.INTERNACIONAL, r"tratado|acuerdo internacional|convenio internacional"),
    (Categoria.ADMINISTRATIVO, r"administrativ|funcion publica|contrataciones|expropiaci"),
    (Categoria.CIVIL_COMERCIAL, r"civil|comercial|codigo civil|obligaciones|contratos"),
]


def _normalize(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    )


def _match_reglas(texto: str, reglas: list[tuple[Categoria, str]]) -> Categoria | None:
    for categoria, pattern in reglas:
        if re.search(pattern, texto):
            return categoria
    return None


def classify(entry: CatalogEntry) -> Categoria:
    tipo = _normalize(entry.tipo_norma)
    numero = entry.numero_normalizado
    if numero and (tipo, numero) in _NORMAS_CONOCIDAS:
        return _NORMAS_CONOCIDAS[(tipo, numero)]

    titulo = _normalize(entry.titulo_resumido)
    sumario = _normalize(entry.titulo_sumario or "").strip()

    if (
        sumario in _SUMARIOS_RUIDO
        or _REGEX_RUIDO_TITULO.search(titulo)
        or (entry.texto_resumido and _REGEX_RUIDO_RESUMEN.search(_normalize(entry.texto_resumido)))
    ):
        return Categoria.RUIDO

    haystack = " ".join(
        part
        for part in [
            titulo,
            sumario,
            _normalize(entry.organismo_origen or ""),
            _normalize(entry.clase_norma or ""),
        ]
        if part
    )
    if categoria := _match_reglas(haystack, _REGLAS):
        return categoria

    if sumario and (categoria := _match_reglas(sumario, _REGLAS_SUMARIO)):
        return categoria

    if entry.texto_resumido and (
        categoria := _match_reglas(_normalize(entry.texto_resumido), _REGLAS)
    ):
        return categoria

    return Categoria.OTROS
