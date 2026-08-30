"""Parsing del catalogo oficial y del estado de vigencia."""

import csv
from pathlib import Path

import pytest
from cartia_shared import NormaEstado

from app.scraping.catalog import (
    CatalogEntry,
    find_catalog_url,
    load_catalog,
    parse_estado,
)


def test_sin_observaciones_se_asume_vigente() -> None:
    assert parse_estado(None) == NormaEstado.VIGENTE
    assert parse_estado("") == NormaEstado.VIGENTE


def test_derogada_y_abrogada_se_mapean_a_derogada() -> None:
    assert parse_estado("Derogada por Ley 27.500") == NormaEstado.DEROGADA
    assert parse_estado("ABROGADA por Decreto 123/2020") == NormaEstado.DEROGADA
    # Con acentos y variantes de genero/numero.
    assert parse_estado("Fue derogado por art. 5 de la Ley 27.001") == NormaEstado.DEROGADA


def test_derogacion_parcial_en_ambos_ordenes() -> None:
    assert parse_estado("Parcialmente derogada por Ley 26.000") == NormaEstado.PARCIALMENTE_VIGENTE
    assert (
        parse_estado("Derogada parcialmente por Decreto 10/2019")
        == NormaEstado.PARCIALMENTE_VIGENTE
    )


def test_observaciones_sin_derogacion_no_cambian_el_estado() -> None:
    assert parse_estado("Fe de erratas publicada el 10/01/2020") == NormaEstado.VIGENTE
    assert parse_estado("Modificada por Ley 27.401") == NormaEstado.VIGENTE


def _escribir_catalogo(tmp_path: Path, filas: list[dict]) -> Path:
    columnas = [
        "id_norma",
        "tipo_norma",
        "numero_norma",
        "clase_norma",
        "organismo_origen",
        "fecha_sancion",
        "numero_boletin",
        "fecha_boletin",
        "pagina_boletin",
        "titulo_resumido",
        "titulo_sumario",
        "texto_resumido",
        "observaciones",
        "texto_original",
        "texto_actualizado",
        "modificada_por",
        "modifica_a",
    ]
    path = tmp_path / "catalogo.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(filas)
    return path


def test_load_catalog_parsea_fechas_y_urls(tmp_path: Path) -> None:
    path = _escribir_catalogo(
        tmp_path,
        [
            {
                "id_norma": "12345",
                "tipo_norma": "Ley",
                "numero_norma": "20.744",
                "organismo_origen": "Honorable Congreso de la Nación",
                "fecha_sancion": "13/05/1974",
                "fecha_boletin": "1974-05-21",
                "titulo_resumido": "Ley de Contrato de Trabajo",
                "texto_original": "http://servicios.infoleg.gob.ar/x/norma.htm",
                "texto_actualizado": "http://servicios.infoleg.gob.ar/x/texact.htm",
            }
        ],
    )

    (entrada,) = load_catalog(path)

    assert entrada.id_norma == 12345
    assert entrada.fecha_sancion.isoformat() == "1974-05-13"
    assert entrada.fecha_boletin.isoformat() == "1974-05-21"
    assert entrada.best_url == "http://servicios.infoleg.gob.ar/x/texact.htm"
    assert entrada.numero_normalizado == "20744"


def test_best_url_cae_al_texto_original_si_no_hay_actualizado() -> None:
    entrada = CatalogEntry(
        id_norma=1,
        tipo_norma="Ley",
        texto_original="http://example.com/norma.htm",
    )

    assert entrada.best_url == "http://example.com/norma.htm"


def test_find_catalog_url_descubre_el_zip_en_el_html() -> None:
    html = (
        '<a href="/dataset/base-de-datos-legislativos-infoleg/resource/abc-123/download/'
        'base-infoleg-normativa-nacional.zip">Descargar</a>'
    )

    url = find_catalog_url(html)

    assert url == (
        "https://datos.jus.gob.ar/dataset/base-de-datos-legislativos-infoleg"
        "/resource/abc-123/download/base-infoleg-normativa-nacional.zip"
    )


def test_find_catalog_url_falla_con_mensaje_claro_si_no_esta() -> None:
    with pytest.raises(ValueError, match="no se encontro el link"):
        find_catalog_url("<html><body>sin recursos</body></html>")
