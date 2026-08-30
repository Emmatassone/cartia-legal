"""El grafo compila y sus caminos de ruteo son los esperados.

Se testea el ruteo puro (funciones sincrónicas sobre el estado) porque es la lógica que
decide si se gasta una llamada al modelo grande, y no requiere red para verificarse.
"""

from app.graphs.legal_rag import build_graph, route_after_grade, route_after_guardrails


def test_el_grafo_compila_con_todos_los_nodos() -> None:
    graph = build_graph()
    nodes = set(graph.get_graph().nodes)

    assert {"guardrails", "reject", "rewrite", "retrieve", "grade", "broaden", "generate"} <= nodes


def test_el_guardrail_es_el_primer_nodo() -> None:
    edges = build_graph().get_graph().edges
    desde_start = {edge.target for edge in edges if edge.source == "__start__"}

    assert desde_start == {"guardrails"}


def test_una_consulta_rechazada_no_llega_al_retrieval() -> None:
    assert route_after_guardrails({"allowed": False}) == "reject"
    assert route_after_guardrails({}) == "reject"


def test_una_consulta_admitida_pasa_a_la_reescritura() -> None:
    assert route_after_guardrails({"allowed": True}) == "rewrite"


def test_contexto_suficiente_va_directo_a_generar() -> None:
    assert route_after_grade({"sufficient": True, "attempts": 1}) == "generate"


def test_contexto_insuficiente_reintenta_una_vez() -> None:
    assert route_after_grade({"sufficient": False, "attempts": 1}) == "broaden"


def test_el_reintento_no_es_infinito() -> None:
    # Con `retrieval_max_attempts=2`, el segundo intento fallido responde igual en lugar de
    # seguir buscando: es lo que impide un loop infinito en el grafo.
    assert route_after_grade({"sufficient": False, "attempts": 2}) == "generate"


def test_si_el_servicio_rag_esta_caido_no_se_reintenta() -> None:
    state = {"sufficient": False, "attempts": 1, "meta": {"rag_error": "connection refused"}}

    assert route_after_grade(state) == "generate"
