"""El filtro de vigencia por defecto en el nodo de retrieval.

Las normas derogadas no deberian citarse como si rigieran, pero el usuario tiene que
poder pedirlas explicitamente ("¿qué decía la ley derogada?").
"""

import pytest
from cartia_shared import Fuero, NormaEstado, SearchFilters, SearchResponse

from app.core.settings import Settings
from app.graphs import legal_rag
from app.services import rag_client


def test_sin_filtros_del_usuario_se_excluyen_las_derogadas() -> None:
    filters = legal_rag._with_estado_default(None)

    assert filters is not None
    assert filters.estados == [NormaEstado.VIGENTE, NormaEstado.PARCIALMENTE_VIGENTE]


def test_el_default_conserva_los_filtros_del_usuario() -> None:
    usuario = SearchFilters(fueros=[Fuero.LABORAL], anio_desde=2000)

    filters = legal_rag._with_estado_default(usuario)

    assert filters is not None
    assert filters.fueros == [Fuero.LABORAL]
    assert filters.anio_desde == 2000
    assert filters.estados == [NormaEstado.VIGENTE, NormaEstado.PARCIALMENTE_VIGENTE]


def test_un_pedido_explicito_de_estado_pisa_al_default() -> None:
    usuario = SearchFilters(estados=[NormaEstado.DEROGADA])

    filters = legal_rag._with_estado_default(usuario)

    assert filters is not None
    assert filters.estados == [NormaEstado.DEROGADA]


def test_el_default_se_puede_apagar_por_configuracion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        legal_rag, "get_settings", lambda: Settings(retrieval_excluir_derogadas=False)
    )

    assert legal_rag._with_estado_default(None) is None


async def test_el_reintento_sin_filtros_mantiene_la_exclusion_de_derogadas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """broaden suelta los filtros del usuario, no los de sistema."""
    capturados: list[SearchFilters | None] = []

    async def fake_search(query: str, *, top_k: int, filters: SearchFilters | None = None):
        capturados.append(filters)
        return SearchResponse(query=query, chunks=[], took_ms=1)

    monkeypatch.setattr(rag_client, "search", fake_search)

    await legal_rag.retrieve_node(
        {"question": "¿plazo de preaviso?", "search_queries": ["plazo de preaviso"], "attempts": 1}
    )

    assert len(capturados) == 1
    assert capturados[0] is not None
    assert capturados[0].estados == [NormaEstado.VIGENTE, NormaEstado.PARCIALMENTE_VIGENTE]
