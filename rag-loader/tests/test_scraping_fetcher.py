"""Limpieza del HTML de InfoLEG."""

from app.scraping.fetcher import html_to_text


def test_saca_la_navegacion_y_conserva_los_articulos() -> None:
    html = """
    <html><head><style>body { color: red; }</style></head>
    <body>
      <nav><a href="/">Inicio</a> | <a href="/buscar">Buscar</a></nav>
      <div id="content">
        <p>LEY 20.744</p>
        <p>ARTICULO 1.- Ambito de aplicacion.</p>
        <p>ARTICULO 2.- La presente ley rige en todo el territorio.</p>
      </div>
      <footer>Ministerio de Justicia</footer>
      <script>track();</script>
    </body></html>
    """

    texto = html_to_text(html)

    assert "ARTICULO 1" in texto
    assert "ARTICULO 2" in texto
    assert "Inicio" not in texto
    assert "track();" not in texto
    assert "color: red" not in texto


def test_los_br_se_convierten_en_saltos_de_linea() -> None:
    html = "<html><body><p>ARTICULO 5.- Plazo.<br>El plazo es de 2 anios.</p></body></html>"

    texto = html_to_text(html)

    assert "Plazo" in texto
    assert "2 anios" in texto


def test_sin_contenedor_conocido_usa_el_body() -> None:
    html = "<html><body>ARTICULO 9.- Texto plano sin estructura.</body></html>"

    assert "ARTICULO 9" in html_to_text(html)


def test_las_paginas_viejas_en_latin1_no_pierden_los_acentos() -> None:
    # InfoLEG sirve las normas viejas en Latin-1 y sin header charset: decodificar
    # como UTF-8 (default de httpx) convierte "Artículo" en "Art�culo".
    html = "<html><body><p>ARTÍCULO 1°.- Creación de juzgados.</p></body></html>"

    texto = html_to_text(html.encode("latin-1"))

    assert "ARTÍCULO" in texto
    assert "Creación" in texto
    assert "�" not in texto
