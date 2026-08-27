import json
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger("SynthGraph.PDFParser")


def parse_pdf_for_vision(pdf_path: str, img_out_dir: str = "logs/extracted_images") -> str:
    """Extrait le texte structuré d'un PDF scientifique.

    Moteur principal : opendataloader-pdf (meilleur reading order + tables).
    Fallback : PyMuPDF si Java ou opendataloader indisponible.
    """
    path = Path(pdf_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"PDF introuvable : {pdf_path}")

    try:
        return _extract_with_opendataloader(path, img_out_dir)
    except Exception as e:
        logger.warning(f"opendataloader-pdf indisponible ({e}), fallback PyMuPDF")
        return _extract_with_pymupdf(path, img_out_dir)


# [V4.15.1] opendataloader (Java) s'est GELÉ 24 h sur un PDF (ball-milling,
# batch 2, 2026-07-17) : convert() est bloquant sans timeout → le fallback
# PyMuPDF n'était jamais atteint et le batch entier restait suspendu, modèle
# chargé en VRAM. L'appel vit désormais dans un sous-processus python tuable
# (taskkill /T emporte le java petit-fils). 240 s >> les ~5-30 s normaux.
ODL_TIMEOUT_S = 240


def _extract_with_opendataloader(path: Path, img_out_dir: str) -> str:
    """Extraction via opendataloader-pdf (Java, sous-processus avec timeout)."""
    import subprocess
    import sys

    out_dir = Path(tempfile.mkdtemp(prefix="odl_"))
    logger.info(f"Extraction opendataloader-pdf sur {path.name} (timeout {ODL_TIMEOUT_S}s)...")

    helper = (
        "import opendataloader_pdf; "
        f"opendataloader_pdf.convert(input_path=[{str(path)!r}], "
        f"output_dir={str(out_dir)!r}, format='markdown,json')"
    )
    # [V4.17.1] stdout/stderr CAPTURÉS : le traceback du helper (PDF corrompu,
    # rc=1 — cas géré par le fallback) partait dans le log du run et déclenchait
    # un faux CRASH au triage (constaté batch 3, PDF spray ZnO tronqué).
    proc = subprocess.Popen([sys.executable, "-c", helper],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    try:
        rc = proc.wait(timeout=ODL_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True)
        raise TimeoutError(
            f"opendataloader gelé (> {ODL_TIMEOUT_S}s) sur {path.name} — "
            f"arbre de processus tué, fallback PyMuPDF")
    if rc != 0:
        err_tail = ""
        try:
            err_tail = (proc.stderr.read() or "").strip().splitlines()[-1][:160]
        except Exception:
            pass
        raise RuntimeError(f"opendataloader rc={rc} sur {path.name} ({err_tail})")

    md_file = out_dir / f"{path.stem}.md"
    json_file = out_dir / f"{path.stem}.json"

    if not md_file.exists():
        raise FileNotFoundError(f"opendataloader n'a pas produit de Markdown pour {path.name}")

    md_text = md_file.read_text(encoding="utf-8")

    # Enrichir avec les tables extraites du JSON structuré
    tables_text = _extract_tables_from_json(json_file) if json_file.exists() else ""
    if tables_text:
        md_text = md_text + "\n\n" + tables_text
        logger.info(f"  [ODL] Tables structurées ajoutées ({len(tables_text)} chars)")

    # Copier les images extraites vers img_out_dir
    odl_img_dir = out_dir / f"{path.stem}_images"
    if odl_img_dir.exists():
        dest = Path(img_out_dir)
        dest.mkdir(parents=True, exist_ok=True)
        count = 0
        for img in odl_img_dir.iterdir():
            if img.suffix.lower() in (".png", ".jpg", ".jpeg"):
                import shutil
                shutil.copy2(img, dest / img.name)
                count += 1
        if count:
            logger.info(f"  [ODL] {count} images copiées vers {img_out_dir}")

    logger.info(f"opendataloader-pdf extrait avec succès : {len(md_text)} caractères.")
    return md_text


def _extract_tables_from_json(json_path: Path) -> str:
    """Extrait les tables du JSON opendataloader et les formate en texte tabulé."""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Impossible de lire le JSON ODL : {e}")
        return ""

    kids = data.get("kids", [])
    table_blocks = []

    for elem in kids:
        if elem.get("type") != "table":
            continue
        page = elem.get("page number", "?")
        content = elem.get("content", "")
        if not content:
            rows = elem.get("kids", [])
            if rows:
                content = _format_table_kids(rows)
        if content:
            table_blocks.append(f"[TABLE STRUCTURÉE page {page}]\n{content}")

    return "\n\n".join(table_blocks)


def _format_table_kids(rows: list) -> str:
    """Formate les enfants d'un élément table en texte lisible."""
    lines = []
    for row in rows:
        if row.get("type") == "table_row":
            cells = row.get("kids", [])
            cell_texts = [c.get("content", "").strip() for c in cells if c.get("content")]
            if cell_texts:
                lines.append(" | ".join(cell_texts))
        elif row.get("content"):
            lines.append(row["content"].strip())
    return "\n".join(lines)


def _extract_with_pymupdf(path: Path, img_out_dir: str) -> str:
    """Fallback : extraction via PyMuPDF (ancien comportement)."""
    import fitz

    out_dir = Path(img_out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Lancement du Parseur Multimodal PyMuPDF sur {path.name}...")

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        logger.error(f"Erreur d'ouverture du PDF avec PyMuPDF: {e}")
        raise

    full_text_blocks = []

    for page_num, page in enumerate(doc, start=1):
        tabs = page.find_tables()
        for tab_idx, tab in enumerate(tabs.tables, start=1):
            bbox = tab.bbox
            try:
                pix = page.get_pixmap(clip=bbox, dpi=200)
                img_name = f"tableau_p{page_num}_{tab_idx}.png"
                img_path = out_dir / img_name
                pix.save(str(img_path))
                full_text_blocks.append(f"\n\n[TABLEAU DÉTECTÉ : {img_path.as_posix()}]\n\n")
            except Exception as e:
                logger.warning(f"Impossible d'extraire le tableau p{page_num}_{tab_idx} : {e}")

        image_list = page.get_images()
        for img_idx, img_info in enumerate(image_list, start=1):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                img_ext = base_image["ext"]
                if img_ext in ["png", "jpeg", "jpg"]:
                    img_name = f"figure_p{page_num}_{img_idx}.{img_ext}"
                    img_path = out_dir / img_name
                    with open(img_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    full_text_blocks.append(f"\n\n[FIGURE DÉTECTÉE : {img_path.as_posix()}]\n\n")
            except Exception as e:
                logger.warning(f"Impossible d'extraire l'image xref {xref} p{page_num} : {e}")

        page_text = page.get_text()
        if page_text:
            full_text_blocks.append(page_text)

        full_text_blocks.append("\n\n---\n\n")

    doc.close()

    final_text = "".join(full_text_blocks)
    logger.info(f"Extraction terminée. Longueur totale : {len(final_text)} caractères.")
    return final_text
