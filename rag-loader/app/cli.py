"""CLI del rag-loader. Es la via principal, porque los documentos viven en la maquina local.

Ejemplos:
    # Reindex completo de todo el corpus
    uv run cartia-loader reindex

    # Ingesta de un solo documento (sin tocar el resto del indice)
    uv run cartia-loader ingest "leyes/ley-20744-lct.pdf"

    # Ingesta de una carpeta forzando metadata
    uv run cartia-loader ingest fallos/csjn --doc-type fallo --jurisdiction nacional --organo CSJN

    # Ver que hay cargado
    uv run cartia-loader status
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from .core.db import get_engine
from .core.settings import get_settings
from .scraping import download_catalog, load_catalog
from .scraping import scrape as run_scrape
from .scraping.catalog import CATALOG_CSV_NAME
from .scraping.pipeline import select_entries
from .services.chunking import chunk_document
from .services.extract import extract_text
from .services.ingest import (
    delete_document,
    discover_documents,
    ensure_schema,
    resolve_path,
    run_ingestion,
)
from .services.metadata import infer_metadata

app = typer.Typer(help="Ingesta de documentos juridicos al indice vectorial de CartIA Legal.")
console = Console()


def _configure_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def _collect_overrides(
    doc_type: str | None,
    jurisdiction: str | None,
    fuero: str | None,
    organo: str | None,
    numero: str | None,
    anio: int | None,
    title: str | None,
) -> dict[str, Any]:
    candidates = {
        "doc_type": doc_type,
        "jurisdiction": jurisdiction,
        "fuero": fuero,
        "organo": organo,
        "numero": numero,
        "anio": anio,
        "title": title,
    }
    return {key: value for key, value in candidates.items() if value is not None}


def _print_result(result: Any) -> None:
    console.print()
    console.print(
        f"[bold green]{result.documents_ingested}[/] ingestados  "
        f"[bold yellow]{result.documents_skipped}[/] sin cambios  "
        f"[bold red]{result.documents_failed}[/] con error  "
        f"[bold]{result.chunks_written}[/] chunks  "
        f"({result.took_ms} ms)"
    )
    for error in result.errors:
        console.print(f"  [red]x[/] {error}")
    if result.documents_failed:
        raise typer.Exit(code=1)


@app.command()
def ingest(
    path: Annotated[str, typer.Argument(help="Archivo o carpeta, relativo a DOCUMENTS_DIR")],
    force: Annotated[
        bool, typer.Option(help="Reprocesa aunque el contenido no haya cambiado")
    ] = False,  # noqa: E501
    doc_type: Annotated[str | None, typer.Option(help="Override del tipo de documento")] = None,
    jurisdiction: Annotated[str | None, typer.Option(help="Override de jurisdiccion")] = None,
    fuero: Annotated[str | None, typer.Option(help="Override de fuero")] = None,
    organo: Annotated[str | None, typer.Option(help="Organo emisor / tribunal")] = None,
    numero: Annotated[str | None, typer.Option(help="Numero de norma")] = None,
    anio: Annotated[int | None, typer.Option(help="Anio de sancion")] = None,
    title: Annotated[str | None, typer.Option(help="Titulo del documento")] = None,
) -> None:
    """Ingesta incremental de un documento o carpeta. No borra nada del resto del indice."""
    _configure_logging()
    result = run_ingestion(
        path,
        reindex=False,
        force=force,
        overrides=_collect_overrides(doc_type, jurisdiction, fuero, organo, numero, anio, title),
        on_progress=lambda message: console.print(f"  {message}"),
    )
    _print_result(result)


@app.command()
def reindex(
    path: Annotated[
        str | None, typer.Argument(help="Raiz del corpus (default: DOCUMENTS_DIR)")
    ] = None,  # noqa: E501
    yes: Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmacion")] = False,
) -> None:
    """Recrea el indice desde cero y vuelve a ingestar todo el corpus."""
    _configure_logging()
    if not yes:
        typer.confirm(
            "Esto BORRA todo el indice vectorial y lo reconstruye. Continuar?", abort=True
        )
    result = run_ingestion(
        path,
        reindex=True,
        on_progress=lambda message: console.print(f"  {message}"),
    )
    _print_result(result)


@app.command("init-schema")
def init_schema() -> None:
    """Crea las extensiones, tablas e indices si no existen. Idempotente."""
    _configure_logging()
    ensure_schema()
    console.print("[green]esquema del indice listo[/]")


@app.command()
def delete(
    source_path: Annotated[str, typer.Argument(help="source_path exacto del documento")],
) -> None:  # noqa: E501
    """Elimina un documento y sus chunks del indice."""
    _configure_logging()
    if delete_document(source_path):
        console.print(f"[green]eliminado[/] {source_path}")
    else:
        console.print(f"[yellow]no estaba en el indice[/] {source_path}")
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Resumen del corpus indexado."""
    _configure_logging()
    with get_engine().connect() as connection:
        if not connection.execute(
            text("SELECT to_regclass('public.rag_documents') IS NOT NULL")
        ).scalar_one():
            console.print("[yellow]el indice todavia no existe. Corre `init-schema`.[/]")
            raise typer.Exit(code=1)

        totals = (
            connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM rag_documents) AS docs, "
                    "(SELECT count(*) FROM rag_chunks) AS chunks"
                )
            )
            .mappings()
            .one()
        )
        rows = (
            connection.execute(
                text(
                    "SELECT doc_type, jurisdiction, count(*) AS docs, sum(n_chunks) AS chunks "
                    "FROM rag_documents GROUP BY doc_type, jurisdiction ORDER BY docs DESC"
                )
            )
            .mappings()
            .all()
        )

    table = Table(title=f"Corpus: {totals['docs']} documentos / {totals['chunks']} chunks")
    table.add_column("Tipo")
    table.add_column("Jurisdiccion")
    table.add_column("Docs", justify="right")
    table.add_column("Chunks", justify="right")
    for row in rows:
        table.add_row(
            row["doc_type"], row["jurisdiction"], str(row["docs"]), str(row["chunks"] or 0)
        )
    console.print(table)


@app.command()
def inspect(
    path: Annotated[str, typer.Argument(help="Archivo a analizar")],
    show_chunks: Annotated[int, typer.Option(help="Cuantos chunks mostrar")] = 3,
) -> None:
    """Dry-run: muestra metadata inferida y chunks SIN escribir en la base ni llamar a la API.

    Es la forma barata de calibrar el chunking contra un documento nuevo.
    """
    _configure_logging()
    settings = get_settings()
    resolved = resolve_path(path)
    candidates = discover_documents(resolved)
    if not candidates:
        console.print(f"[red]no hay documentos soportados en {resolved}[/]")
        raise typer.Exit(code=1)

    target = candidates[0]
    body = extract_text(target)
    metadata = infer_metadata(target, body)
    chunks = chunk_document(
        body,
        max_chars=settings.max_chunk_chars,
        min_chars=settings.min_chunk_chars,
        overlap=settings.chunk_overlap_chars,
    )

    console.print(f"[bold]{target.name}[/]  {len(body)} caracteres  {len(chunks)} chunks")
    console.print(metadata.model_dump())
    con_articulo = sum(1 for chunk in chunks if chunk.articulo)
    console.print(f"chunks con articulo detectado: {con_articulo}/{len(chunks)}")
    for chunk in chunks[:show_chunks]:
        console.rule(f"chunk {chunk.chunk_index} | art {chunk.articulo} | {chunk.heading}")
        console.print(chunk.content[:800])


def _materias_arg(materia: list[str]) -> set[str] | None:
    return {m.strip().lower() for m in materia if m.strip()} or None


@app.command("scrape-catalog")
def scrape_catalog(
    catalog_url: Annotated[
        str | None, typer.Option(help="URL directa del zip; si no, se descubre del portal")
    ] = None,
) -> None:
    """Baja el catalogo oficial de normas (datos.jus.gob.ar, base InfoLEG)."""
    _configure_logging()
    path = download_catalog(catalog_url)
    entries = load_catalog(path)
    console.print(f"[green]catalogo listo[/] {path} ({len(entries)} normas)")


@app.command("scrape-list")
def scrape_list(
    materia: Annotated[
        list[str], typer.Option(help="Materias a incluir (repetible). Vacio = todas")
    ] = [],  # noqa: B006  (idioma de Typer para opciones repetibles; no se muta)
    tipos: Annotated[
        str | None,
        typer.Option(help="Tipos de norma separados por coma (default: leyes y decretos)"),
    ] = None,
    anio_desde: Annotated[
        int | None, typer.Option(help="Solo normas sancionadas desde este anio")
    ] = None,
    incluir_derogadas: Annotated[
        bool, typer.Option(help="Incluir normas derogadas en la seleccion")
    ] = False,
    incluir_ruido: Annotated[
        bool, typer.Option(help="Incluir actos individuales (designaciones, homenajes, etc.)")
    ] = False,
) -> None:
    """Preview: cuantas normas caerian en cada carpeta, sin descargar nada."""
    _configure_logging()
    settings = get_settings()
    catalog_path = settings.resolved_catalog_dir / CATALOG_CSV_NAME
    if not catalog_path.is_file():
        console.print("[yellow]no hay catalogo; corre `scrape-catalog` primero[/]")
        raise typer.Exit(code=1)

    seleccion = select_entries(
        load_catalog(catalog_path),
        materias=_materias_arg(materia),
        tipos={t.strip() for t in tipos.split(",")} if tipos else None,
        anio_desde=anio_desde,
        solo_vigentes=not incluir_derogadas,
        incluir_ruido=True,
    )
    ruido = sum(1 for _, categoria in seleccion if categoria.value == "ruido")
    if not incluir_ruido:
        seleccion = [(e, c) for e, c in seleccion if c.value != "ruido"]

    table = Table(title=f"{len(seleccion)} normas seleccionadas")
    table.add_column("Carpeta")
    table.add_column("Normas", justify="right")
    counts: dict[str, int] = {}
    for _, categoria in seleccion:
        counts[categoria.value] = counts.get(categoria.value, 0) + 1
    for categoria, cantidad in sorted(counts.items(), key=lambda item: -item[1]):
        table.add_row(categoria, str(cantidad))
    console.print(table)
    if ruido and not incluir_ruido:
        console.print(
            f"[dim]{ruido} actos individuales (designaciones, homenajes, decretos "
            f"secretos de personal, etc.) quedan fuera; --incluir-ruido los suma[/]"
        )


@app.command()
def scrape(
    materia: Annotated[
        list[str], typer.Option(help="Materias a descargar (repetible). Vacio = todas")
    ] = [],  # noqa: B006  (idioma de Typer para opciones repetibles; no se muta)
    tipos: Annotated[
        str | None,
        typer.Option(help="Tipos de norma separados por coma (default: leyes y decretos)"),
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Maximo de normas a descargar")] = None,
    anio_desde: Annotated[
        int | None, typer.Option(help="Solo normas sancionadas desde este anio")
    ] = None,
    incluir_derogadas: Annotated[
        bool, typer.Option(help="Tambien descargar normas derogadas (quedan marcadas)")
    ] = False,
    incluir_ruido: Annotated[
        bool, typer.Option(help="Tambien descargar actos individuales (designaciones, etc.)")
    ] = False,
    force: Annotated[
        bool, typer.Option(help="Re-descargar aunque ya esten en el manifiesto")
    ] = False,
    dry_run: Annotated[bool, typer.Option(help="Solo mostrar la seleccion, sin descargar")] = False,
) -> None:
    """Descarga normas de InfoLEG a documents/<materia>/ con su metadata completa.

    Despues de scrapear, `ingest` o `reindex` las suben al indice como cualquier
    otro documento: el sidecar .meta.json ya trae norma, tipo, jurisdiccion, materia
    y estado de vigencia.
    """
    _configure_logging()
    result = run_scrape(
        materias=_materias_arg(materia),
        tipos={t.strip() for t in tipos.split(",")} if tipos else None,
        limit=limit,
        anio_desde=anio_desde,
        solo_vigentes=not incluir_derogadas,
        incluir_ruido=incluir_ruido,
        force=force,
        dry_run=dry_run,
        on_progress=lambda message: console.print(f"  {message}"),
    )

    console.print()
    console.print(
        f"[bold green]{result.descargadas}[/] descargadas  "
        f"[bold yellow]{result.salteadas}[/] ya estaban  "
        f"[bold red]{result.fallidas}[/] con error  "
        f"[bold]{result.sin_texto}[/] sin URL de texto"
    )
    for categoria, cantidad in sorted(result.por_categoria.items()):
        console.print(f"  {categoria}: {cantidad}")
    for error in result.errors[:20]:
        console.print(f"  [red]x[/] {error}")
    if result.fallidas:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
