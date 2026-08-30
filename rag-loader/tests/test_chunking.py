"""Tests del chunker. Es la pieza que mas impacta la calidad del retrieval legal."""

from app.services.chunking import build_embedding_input, chunk_document
from app.services.extract import normalize_text

LEY_DE_PRUEBA = """LEY DE CONTRATO DE TRABAJO

TITULO I - Disposiciones generales

ARTICULO 1. - El contrato de trabajo y la relacion de trabajo se rigen por esta ley.

ARTICULO 2. - La vigencia de esta ley resultara aplicable a todas las relaciones
laborales, con las exclusiones que se establecen.

TITULO XII - De la extincion del contrato de trabajo

ARTICULO 245. - En los casos de despido dispuesto por el empleador sin justa causa el
empleador debera abonar al trabajador una indemnizacion equivalente a UN (1) mes de
sueldo por cada anio de servicio o fraccion mayor de TRES (3) meses.

ARTICULO 246. - Cuando el empleador despida al trabajador sin justa causa, este tendra
derecho a la indemnizacion prevista en el articulo 245.
"""


def test_parte_por_articulo_y_detecta_el_numero() -> None:
    chunks = chunk_document(LEY_DE_PRUEBA, max_chars=1800, min_chars=50, overlap=100)

    articulos = [chunk.articulo for chunk in chunks if chunk.articulo]
    assert "245" in articulos
    assert "246" in articulos


def test_arrastra_el_titulo_como_encabezado() -> None:
    chunks = chunk_document(LEY_DE_PRUEBA, max_chars=1800, min_chars=50, overlap=100)

    art_245 = next(chunk for chunk in chunks if chunk.articulo == "245")
    assert art_245.heading is not None
    assert "TITULO XII" in art_245.heading.upper()


def test_los_chunks_respetan_el_maximo() -> None:
    texto = "ARTICULO 1. - " + ("palabra " * 2000)
    chunks = chunk_document(texto, max_chars=800, min_chars=100, overlap=100)

    assert len(chunks) > 1
    # El prefijo de continuacion agrega unos pocos caracteres sobre el limite del cuerpo.
    assert all(len(chunk.content) <= 900 for chunk in chunks)


def test_un_articulo_partido_repite_la_referencia_en_las_continuaciones() -> None:
    texto = "ARTICULO 77. - " + ("texto extenso del articulo. " * 200)
    chunks = chunk_document(texto, max_chars=700, min_chars=100, overlap=80)

    assert len(chunks) > 1
    assert all(chunk.articulo == "77" for chunk in chunks)
    assert chunks[1].content.startswith("[Art. 77 (cont.")


def test_sin_estructura_de_articulos_parte_por_parrafo() -> None:
    fallo = "\n\n".join(f"Considerando {index}: fundamentos del tribunal." for index in range(12))
    chunks = chunk_document(fallo, max_chars=200, min_chars=50, overlap=40)

    assert len(chunks) > 1
    assert all(chunk.articulo is None for chunk in chunks)


def test_los_indices_son_consecutivos_desde_cero() -> None:
    chunks = chunk_document(LEY_DE_PRUEBA, max_chars=600, min_chars=50, overlap=80)

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_el_texto_embebido_lleva_titulo_y_referencia() -> None:
    chunks = chunk_document(LEY_DE_PRUEBA, max_chars=1800, min_chars=50, overlap=100)
    art_245 = next(chunk for chunk in chunks if chunk.articulo == "245")

    embedded = build_embedding_input(art_245, "Ley 20.744 de Contrato de Trabajo")

    assert embedded.startswith("Ley 20.744 de Contrato de Trabajo | ")
    assert "Art. 245" in embedded


def test_normalize_text_preserva_el_salto_antes_de_articulo() -> None:
    crudo = "El presente decreto entra en vigencia\nARTICULO 2. - Comuniquese."

    assert "\nARTICULO 2" in normalize_text(crudo)
