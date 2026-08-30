"""Construccion del SQL de la busqueda hibrida.

Importa porque el SQL se arma con `str.format` y con parametros numerados a mano: un error
ahi no falla en import, falla en la primera consulta real contra la base.
"""

import sqlparse
from cartia_shared import DocumentType, Fuero, Jurisdiction, SearchFilters

from app.services.retrieval import _QUERY_TEMPLATE, _build_filters


def render(filters: SearchFilters | None) -> tuple[str, dict]:
    fragment, params = _build_filters(filters)
    return _QUERY_TEMPLATE.format(filters=fragment), params


def test_sin_filtros_el_sql_queda_completo() -> None:
    sql, params = render(None)

    assert params == {}
    assert "{filters}" not in sql
    # Las dos ramas (semantica y lexica) y la fusion tienen que estar presentes.
    assert "hnsw" not in sql  # el hint de indice va aparte, no en la query
    assert "websearch_to_tsquery" in sql
    assert "FULL OUTER JOIN" in sql
    assert sql.count("CAST(:qvec AS vector)") == 2


def test_el_fragmento_de_filtros_se_inyecta_en_ambas_ramas() -> None:
    filters = SearchFilters(
        doc_types=[DocumentType.LEY, DocumentType.FALLO],
        jurisdictions=[Jurisdiction.NACIONAL],
        fueros=[Fuero.LABORAL],
        anio_desde=2015,
        anio_hasta=2024,
    )
    sql, params = render(filters)

    # Un CTE compartido lo materializaria Postgres y la rama semantica perderia el indice,
    # asi que el fragmento tiene que aparecer duplicado.
    assert sql.count("d.doc_type IN (:dt_0, :dt_1)") == 2
    assert sql.count("d.jurisdiction IN (:ju_0)") == 2
    assert sql.count("d.anio >= :anio_desde") == 2

    assert params == {
        "dt_0": "ley",
        "dt_1": "fallo",
        "ju_0": "nacional",
        "fu_0": "laboral",
        "anio_desde": 2015,
        "anio_hasta": 2024,
    }


def test_los_enums_se_serializan_al_valor_y_no_al_nombre() -> None:
    _, params = render(SearchFilters(doc_types=[DocumentType.CONVENIO_COLECTIVO]))

    assert params["dt_0"] == "convenio_colectivo"


def test_un_filtro_vacio_no_genera_clausula() -> None:
    sql, params = render(SearchFilters(doc_types=[], jurisdictions=None))

    assert params == {}
    assert " AND d." not in sql


def test_el_filtro_de_estado_deja_pasar_los_sin_dato() -> None:
    from cartia_shared import NormaEstado

    filters = SearchFilters(estados=[NormaEstado.VIGENTE, NormaEstado.PARCIALMENTE_VIGENTE])
    sql, params = render(filters)

    # NULL = cargado a mano sin dato de vigencia: excluirlo vaciaria el corpus manual.
    assert sql.count("(d.estado IS NULL OR d.estado IN (:es_0, :es_1))") == 2
    assert params == {"es_0": "vigente", "es_1": "parcialmente_vigente"}


def test_los_document_ids_se_castean_a_uuid() -> None:
    ids = ["3f2b1c4e-0000-4000-8000-000000000001"]
    sql, params = render(SearchFilters(document_ids=ids))  # type: ignore[arg-type]

    assert "CAST(:doc_0 AS uuid)" in sql
    assert params["doc_0"] == ids[0]


def test_el_sql_es_sintacticamente_valido() -> None:
    filters = SearchFilters(doc_types=[DocumentType.LEY], anio_desde=2020)
    sql, _ = render(filters)

    statements = sqlparse.parse(sql)

    assert len(statements) == 1
    assert statements[0].get_type() == "SELECT"
    # Sin placeholders sin resolver ni llaves sueltas que rompan el `format`.
    assert "{" not in sql and "}" not in sql
