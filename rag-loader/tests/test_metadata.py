from pathlib import Path

from cartia_shared import DocumentType, Fuero, Jurisdiction

from app.services.metadata import infer_metadata


def test_infiere_ley_laboral_nacional() -> None:
    texto = (
        "LEY 20.744 - REGIMEN DE CONTRATO DE TRABAJO\n"
        "Sancionada el 20 de septiembre de 1974.\n"
        "El Senado y Camara de Diputados de la Nacion Argentina sancionan con fuerza de Ley."
    )

    metadata = infer_metadata(Path("ley-20744-contrato-de-trabajo.pdf"), texto)

    assert metadata.doc_type is DocumentType.LEY
    assert metadata.numero == "20744"
    assert metadata.fuero is Fuero.LABORAL
    assert metadata.anio == 1974
    assert metadata.citation


def test_infiere_fallo_de_la_csjn() -> None:
    texto = (
        "CORTE SUPREMA DE JUSTICIA DE LA NACION\n"
        "Buenos Aires, 10 de marzo de 2017.\n"
        "Vistos los autos: recurso extraordinario federal en materia penal."
    )

    metadata = infer_metadata(Path("csjn-fallo-2017.pdf"), texto)

    assert metadata.doc_type is DocumentType.FALLO
    assert metadata.organo == "CSJN"
    assert metadata.fecha is not None
    assert metadata.fecha.year == 2017


def test_los_overrides_ganan_a_la_inferencia() -> None:
    metadata = infer_metadata(
        Path("documento-sin-datos.txt"),
        "Texto sin ninguna senal de tipo ni jurisdiccion, suficientemente largo.",
        overrides={"doc_type": "contrato", "jurisdiction": "cordoba", "title": "Contrato marco"},
    )

    assert metadata.doc_type is DocumentType.CONTRATO
    assert metadata.jurisdiction is Jurisdiction.CORDOBA
    assert metadata.title == "Contrato marco"


def test_el_titulo_por_defecto_sale_del_nombre_de_archivo() -> None:
    metadata = infer_metadata(
        Path("convenio_colectivo_marco_2024.docx"),
        "Convenio colectivo de trabajo celebrado entre las partes signatarias del acuerdo.",
    )

    assert metadata.title == "convenio colectivo marco 2024"
