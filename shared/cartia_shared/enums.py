from enum import StrEnum


class DocumentType(StrEnum):
    """Tipo de documento legal argentino."""

    LEY = "ley"
    DECRETO = "decreto"
    RESOLUCION = "resolucion"
    CODIGO = "codigo"
    CONSTITUCION = "constitucion"
    FALLO = "fallo"
    DICTAMEN = "dictamen"
    DOCTRINA = "doctrina"
    CONTRATO = "contrato"
    ESCRITO = "escrito"
    CONVENIO_COLECTIVO = "convenio_colectivo"
    OTRO = "otro"


class Jurisdiction(StrEnum):
    """Jurisdicción de la norma o del tribunal."""

    NACIONAL = "nacional"
    FEDERAL = "federal"
    CABA = "caba"
    BUENOS_AIRES = "buenos_aires"
    CATAMARCA = "catamarca"
    CHACO = "chaco"
    CHUBUT = "chubut"
    CORDOBA = "cordoba"
    CORRIENTES = "corrientes"
    ENTRE_RIOS = "entre_rios"
    FORMOSA = "formosa"
    JUJUY = "jujuy"
    LA_PAMPA = "la_pampa"
    LA_RIOJA = "la_rioja"
    MENDOZA = "mendoza"
    MISIONES = "misiones"
    NEUQUEN = "neuquen"
    RIO_NEGRO = "rio_negro"
    SALTA = "salta"
    SAN_JUAN = "san_juan"
    SAN_LUIS = "san_luis"
    SANTA_CRUZ = "santa_cruz"
    SANTA_FE = "santa_fe"
    SANTIAGO_DEL_ESTERO = "santiago_del_estero"
    TIERRA_DEL_FUEGO = "tierra_del_fuego"
    TUCUMAN = "tucuman"
    DESCONOCIDA = "desconocida"


class Fuero(StrEnum):
    """Fuero o materia principal del documento."""

    CIVIL = "civil"
    COMERCIAL = "comercial"
    LABORAL = "laboral"
    PENAL = "penal"
    FAMILIA = "familia"
    ADMINISTRATIVO = "administrativo"
    TRIBUTARIO = "tributario"
    CONSTITUCIONAL = "constitucional"
    PREVISIONAL = "previsional"
    CONSUMIDOR = "consumidor"
    SOCIETARIO = "societario"
    AMBIENTAL = "ambiental"
    MIGRATORIO = "migratorio"
    PROPIEDAD_INTELECTUAL = "propiedad_intelectual"
    DATOS_PERSONALES = "datos_personales"
    PROCESAL = "procesal"
    OTRO = "otro"


class NormaEstado(StrEnum):
    """Vigencia de una norma. `None` en la base significa "sin dato" (documentos
    cargados a mano), no "vigente"."""

    VIGENTE = "vigente"
    PARCIALMENTE_VIGENTE = "parcialmente_vigente"
    DEROGADA = "derogada"
