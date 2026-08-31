"""Seleccion de entradas y generacion del sidecar de metadata."""

from datetime import date

from cartia_shared import NormaEstado

from app.scraping.catalog import CatalogEntry
from app.scraping.classifier import Categoria
from app.scraping.pipeline import (
    _format_numero,
    _nombre_archivo,
    _resolver_nombres,
    build_sidecar,
    select_entries,
)
from app.services.metadata import DocumentMetadata


def entry(
    id_norma: int,
    tipo: str = "Ley",
    numero: str = "100",
    titulo: str = "Norma de prueba",
    observaciones: str | None = None,
    fecha: str = "2020-01-15",
) -> CatalogEntry:
    return CatalogEntry(
        id_norma=id_norma,
        tipo_norma=tipo,
        numero_norma=numero,
        titulo_resumido=titulo,
        organismo_origen="Honorable Congreso de la Nación",
        fecha_sancion=date.fromisoformat(fecha),
        numero_boletin=34000,
        fecha_boletin=date.fromisoformat(fecha),
        observaciones=observaciones,
        texto_actualizado=f"http://servicios.infoleg.gob.ar/x/{id_norma}/texact.htm",
    )


def test_el_sidecar_valida_contra_la_metadata_de_la_ingesta() -> None:
    sidecar = build_sidecar(
        entry(1, numero="20744", titulo="Contrato de trabajo"), Categoria.LABORAL
    )

    metadata = DocumentMetadata.model_validate(sidecar)

    assert metadata.doc_type.value == "ley"
    assert metadata.jurisdiction.value == "nacional"
    assert metadata.fuero.value == "laboral"
    assert metadata.estado == NormaEstado.VIGENTE
    assert metadata.numero == "20744"
    assert metadata.anio == 2020
    assert metadata.extra["infoleg_id"] == 1
    assert metadata.extra["materia"] == "laboral"
    assert metadata.extra["url_texto"].endswith("texact.htm")


def test_el_sidecar_marca_la_derogacion() -> None:
    sidecar = build_sidecar(entry(2, observaciones="Derogada por Ley 27.500"), Categoria.OTROS)

    assert sidecar["estado"] == "derogada"


def test_la_cita_usa_el_numero_con_puntos() -> None:
    sidecar = build_sidecar(entry(3, numero="20744"), Categoria.LABORAL)

    assert sidecar["citation"].startswith("Ley 20.744")


def test_format_numero() -> None:
    assert _format_numero("20744") == "20.744"
    assert _format_numero("123") == "123"
    assert _format_numero("S/N") == "S/N"


def test_el_nombre_de_archivo_conserva_el_esquema_para_numeros_digitales() -> None:
    # Compatibilidad con lo ya descargado y su manifiesto.
    assert _nombre_archivo(entry(1, numero="20744", titulo="Contrato de trabajo")) == (
        "ley-20744-contrato-de-trabajo"
    )


def test_el_nombre_de_archivo_tolera_numeros_con_barra() -> None:
    # "S/N" crudo rompe el path ('/' es separador de directorios en Windows).
    nombre = _nombre_archivo(entry(183290, numero="S/N", titulo="Hacienda"))
    assert "/" not in nombre and "\\" not in nombre
    assert "id183290" in nombre  # el id desempata las muchas "Ley S/N" distintas


def test_el_nombre_de_archivo_sin_numero_usa_el_id() -> None:
    assert _nombre_archivo(entry(42, numero="", titulo="")).startswith("ley-id42")


def test_las_colisiones_de_nombre_se_desambiguam_con_el_id() -> None:
    # El numero se repite entre presidencias y el slug no incluye el ano.
    colisiona_1 = entry(23651, tipo="Decreto", numero="7", titulo="Ministro - Designacion")
    colisiona_2 = entry(61400, tipo="Decreto", numero="7", titulo="Ministro - Designacion")
    sin_colision = entry(1, numero="20744", titulo="")

    nombres = _resolver_nombres(
        [
            (colisiona_1, Categoria.ADMINISTRATIVO),
            (colisiona_2, Categoria.ADMINISTRATIVO),
            (sin_colision, Categoria.LABORAL),
        ]
    )

    assert nombres[23651] != nombres[61400]
    assert "id23651" in nombres[23651]
    assert "id61400" in nombres[61400]
    # La que no colisiona conserva el esquema original (compatibilidad con el manifiesto).
    assert nombres[1] == "ley-20744"


def test_select_entries_filtra_por_tipo_materia_anio_y_estado() -> None:
    entradas = [
        entry(1, numero="20744", titulo=""),  # laboral, vigente
        entry(2, tipo="Resolucion", titulo="Procedimiento interno"),  # tipo fuera de default
        entry(3, numero="24240", titulo="", observaciones="Derogada por Ley 1"),  # derogada
        entry(4, numero="26994", titulo="", fecha="2014-10-01"),  # civil-comercial
        entry(5, titulo="Régimen laboral especial", fecha="1990-06-01"),  # vieja
    ]

    seleccion = select_entries(entradas)

    assert [e.id_norma for e, _ in seleccion] == [1, 3, 4, 5]

    solo_laboral = select_entries(entradas, materias={"laboral"})
    assert [e.id_norma for e, _ in solo_laboral] == [1, 5]

    vigentes = select_entries(entradas, solo_vigentes=True)
    assert [e.id_norma for e, _ in vigentes] == [1, 4, 5]

    recientes = select_entries(entradas, anio_desde=2000)
    assert [e.id_norma for e, _ in recientes] == [1, 3, 4]


def test_select_entries_es_determinista() -> None:
    entradas = [entry(3), entry(1), entry(2)]

    seleccion = select_entries(entradas)

    assert [e.id_norma for e, _ in seleccion] == [1, 2, 3]


def test_select_entries_saltea_el_ruido_por_default() -> None:
    entradas = [
        entry(1, numero="20744", titulo=""),  # laboral
        entry(2, tipo="Decreto", titulo="DESIGNACION - PRORROGA"),  # ruido
        entry(3, tipo="Decreto", titulo="", observaciones=None),  # otros
    ]

    seleccion = select_entries(entradas)
    assert [e.id_norma for e, _ in seleccion] == [1, 3]

    con_ruido = select_entries(entradas, incluir_ruido=True)
    assert [e.id_norma for e, _ in con_ruido] == [1, 2, 3]

    # Pedir la materia explicitamente tambien la habilita.
    solo_ruido = select_entries(entradas, materias={"ruido"})
    assert [e.id_norma for e, _ in solo_ruido] == [2]
