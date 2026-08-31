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
    assert CATEGORIA_FUERO[Categoria.INTERNACIONAL] == Fuero.INTERNACIONAL


@pytest.mark.parametrize(
    ("titulo", "sumario"),
    [
        ("", "DECRETOS SECRETOS Y RESERVADOS"),
        ("", "HOMENAJES"),
        ("", "CONDECORACIONES"),
        ("", "HUESPEDES OFICIALES"),
        ("", "SUBSIDIO ESTATAL"),
        ("DESIGNACION - PRORROGA", ""),
        ("PROMOCIONES", ""),
        ("CESANTIA", ""),
        ("BECAS - OTORGANSE", ""),
        ("SALIDA DEL PAIS - AUTORIZASE", ""),
        ("LEY Nº 22.248 - SU PROMULGACION", ""),
    ],
)
def test_los_actos_individuales_son_ruido(titulo: str, sumario: str) -> None:
    kwargs = {"titulo_sumario": sumario} if sumario else {}
    assert classify(entry(titulo=titulo, **kwargs)) == Categoria.RUIDO


def test_el_sumario_curado_clasifica_cuando_el_titulo_no_dice_nada() -> None:
    assert classify(entry(titulo="", titulo_sumario="SEGURIDAD SOCIAL")) == Categoria.PREVISIONAL
    assert classify(entry(titulo="", titulo_sumario="JUSTICIA")) == Categoria.PROCESAL
    assert classify(entry(titulo="", titulo_sumario="FISCO NACIONAL")) == Categoria.TRIBUTARIO
    assert classify(entry(titulo="", titulo_sumario="TRATADOS INTERNACIONALES")) == (
        Categoria.INTERNACIONAL
    )
    assert classify(entry(titulo="", titulo_sumario="MINISTERIO DE DEFENSA")) == (
        Categoria.ADMINISTRATIVO
    )


def test_el_titulo_especifico_gana_sobre_el_sumario_generico() -> None:
    # El sumario dice el ministerio de origen; el titulo dice la materia.
    assert (
        classify(entry(titulo="Impuesto a las ganancias", titulo_sumario="MINISTERIO DE SALUD"))
        == Categoria.TRIBUTARIO
    )


def test_el_texto_resumido_salva_titulos_cripticos() -> None:
    assert (
        classify(
            entry(
                titulo="ESTABLECENSE",
                texto_resumido="ESTABLECESE UN REGIMEN DE JUBILACIONES Y PENSIONES.",
            )
        )
        == Categoria.PREVISIONAL
    )


def test_los_tratados_son_internacional() -> None:
    assert classify(entry(titulo="Tratado de libre comercio")) == Categoria.INTERNACIONAL


def test_las_normas_agotadas_son_ruido() -> None:
    # InfoLEG las marca en la bajada; el filtro de vigentes no las alcanza porque
    # nunca fueron derogadas formalmente.
    assert (
        classify(
            entry(
                titulo="",
                texto_resumido="OBJETO CUMPLIDO-DECLARA EXTRAORDINARIAS LAS SESIONES DE 1854",
            )
        )
        == Categoria.RUIDO
    )
