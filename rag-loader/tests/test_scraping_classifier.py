"""Clasificacion por materia: normas conocidas, keywords y precedencia."""

import pytest
from cartia_shared import Fuero

from app.scraping.catalog import CatalogEntry
from app.scraping.classifier import CATEGORIA_FUERO, Categoria, classify


def entry(tipo: str = "Ley", numero: str = "", titulo: str = "", **kwargs) -> CatalogEntry:
    return CatalogEntry(
        id_norma=kwargs.pop("id_norma", 1),
        tipo_norma=tipo,
        numero_norma=numero,
        titulo_resumido=titulo,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("numero", "esperada"),
    [
        ("20744", Categoria.LABORAL),  # LCT
        ("24557", Categoria.LABORAL),  # Riesgos del trabajo
        ("24241", Categoria.PREVISIONAL),  # SIPA
        ("24240", Categoria.CONSUMO),  # Defensa del consumidor
        ("26994", Categoria.CIVIL_COMERCIAL),  # CCCyC
        ("17454", Categoria.PROCESAL),  # CPCCN
        ("19550", Categoria.SOCIETARIO),  # LGS
        ("24522", Categoria.COMERCIAL),  # Concursos
        ("11179", Categoria.PENAL),  # Codigo Penal
        ("25326", Categoria.DATOS_PERSONALES),
        ("25871", Categoria.MIGRATORIO),
        ("11723", Categoria.PROPIEDAD_INTELECTUAL),
    ],
)
def test_las_normas_conocidas_no_dependen_del_titulo(numero: str, esperada: Categoria) -> None:
    # Aunque el titulo del catalogo venga vacio o raro, el mapa curado manda.
    assert classify(entry(numero=numero, titulo="")) == esperada


def test_el_numero_con_puntos_matchea_igual() -> None:
    assert classify(entry(numero="20.744")) == Categoria.LABORAL


def test_keywords_sobre_el_titulo() -> None:
    assert classify(entry(titulo="Régimen de trabajo a distancia")) == Categoria.LABORAL
    assert classify(entry(titulo="Impuesto a las ganancias. Modificación")) == Categoria.TRIBUTARIO
    assert classify(entry(titulo="Presupuestos mínimos de protección ambiental")) == (
        Categoria.AMBIENTAL
    )


def test_procesal_gana_sobre_penal_en_codigos_procesales() -> None:
    assert classify(entry(titulo="Código Procesal Penal de la Nación")) == Categoria.PROCESAL


def test_consumo_gana_sobre_civil() -> None:
    assert classify(entry(titulo="Defensa del consumidor. Servicios financieros")) == (
        Categoria.CONSUMO
    )


def test_lo_desconocido_va_a_otros_y_no_se_pierde() -> None:
    assert classify(entry(titulo="Régimen de fomento pesquero")) == Categoria.OTROS


def test_toda_categoria_tiene_fuero_asignado() -> None:
    assert set(CATEGORIA_FUERO) == set(Categoria)
    assert CATEGORIA_FUERO[Categoria.PROCESAL] == Fuero.PROCESAL
    assert CATEGORIA_FUERO[Categoria.LABORAL] == Fuero.LABORAL
