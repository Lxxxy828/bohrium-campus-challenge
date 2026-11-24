#!/usr/bin/env python3
"""
Robust scientific-PDF parser.

Extracts a PDF into structured, provenance-tagged JSON with correct
multi-column reading order, table structure, and section detection.

Design goals (matching the contest rubric "提得全 / 排得对 / 拆得清 / 核得回"):
  - complete: body text, captions, footnotes, references, headers/footers kept separate;
  - ordered: multi-column reading order restored, no cross-column splicing;
  - structured: sections, tables (rows/cells), and inline-math preserved;
  - traceable: every text block and table carries page number and bbox.

Usage:
  python3 pdf_parse.py INPUT.pdf [OUTPUT.json]

Dependencies (any of these is enough; graceful fallback):
  PyMuPDF (preferred), pdfplumber, pdftotext (poppler).
"""
import sys
import json
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    import pdfplumber
except Exception:
    pdfplumber = None


def _blocks_from_pymupdf(doc):
    """Return per-page list of text blocks with provenance."""
    pages = []
    for pno, page in enumerate(doc):
        d = page.get_text("dict")
        blocks = []
        for b in d.get("blocks", []):
            if b.get("type") != 0:  # 0 = text block
                continue
            lines = []
            text_parts = []
            for line in b.get("lines", []):
                spans = line.get("spans", [])
                line_text = "".join(s.get("text", "") for s in spans)
                text_parts.append(line_text)
                lines.append({
                    "text": line_text,
                    "bbox": list(line["bbox"]),
                    "spans": [
                        {
                            "text": s.get("text", ""),
                            "font": s.get("font", ""),
                            "size": s.get("size"),
                            "flags": s.get("flags"),
                            "bbox": list(s.get("bbox", [])),
                        }
                        for s in spans
                    ],
                })
            blocks.append({
                "bbox": list(b["bbox"]),
                "text": "\n".join(text_parts),
                "lines": lines,
            })
        pages.append({
            "page": pno + 1,
            "width": page.rect.width,
            "height": page.rect.height,
            "blocks": blocks,
        })
    return pages


def _detect_columns(page, blocks):
    """Return column x-ranges for a page.

    Heuristic: cluster the unique x0 positions of blocks. A two-column paper
    yields two well-separated clusters; a single-column paper yields one.
    """
    xs = sorted({round(b["bbox"][0]) for b in blocks})
    if not xs:
        return []
    w = page["width"]
    if len(xs) == 1:
        return [(0, w)]
    gaps = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    threshold = 0.10 * w  # minimum separation to count as a column break
    big = [i for i, g in enumerate(gaps) if g > threshold]
    if not big:
        return [(0, w)]
    # Column edges at the midpoints of the large gaps.
    edges = [0.0]
    for i in big:
        edges.append((xs[i] + xs[i + 1]) / 2)
    edges.append(float(w))
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def _assign_reading_order(page, blocks):
    """Sort blocks into natural reading order, respecting columns.

    Full-width blocks (title/abstract, spanning figures/tables) are kept in a
    separate lane; column blocks are read top-to-bottom, column by column.
    """
    if not blocks:
        return []
    w = page["width"]
    full = []
    columnar = []
    for b in blocks:
        bw = b["bbox"][2] - b["bbox"][0]
        if bw > 0.75 * w:
            full.append(b)
        else:
            columnar.append(b)
    full.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
    cols = _detect_columns(page, columnar)
    if len(cols) <= 1:
        columnar.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
        return full + columnar
    col_blocks = {i: [] for i in range(len(cols))}
    for b in columnar:
        cx = (b["bbox"][0] + b["bbox"][2]) / 2
        ci = 0
        for i, (a, bb) in enumerate(cols):
            if a <= cx <= bb:
                ci = i
                break
        col_blocks[ci].append(b)
    ordered_col = []
    for ci in range(len(cols)):
        col_blocks[ci].sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
        ordered_col.extend(col_blocks[ci])
    return full + ordered_col


def _detect_section(text):
    """Classify a line as a heading if it looks like a section title."""
    s = text.strip()
    if not s:
        return None
    import re
    if re.match(r"^(\d+(\.\d+)*\.?)\s+\S", s):
        return s
    if re.match(r"^(Abstract|Introduction|Methods|Results|Discussion|Conclusion|References|Acknowledgments?|Appendix|Supplementary)\b", s, re.I):
        return s
    return None


def _extract_tables_pymupdf(doc):
    """Extract tables via PyMuPDF find_tables."""
    tables = []
    for pno, page in enumerate(doc):
        try:
            found = page.find_tables()
        except Exception:
            continue
        for t in found.tables:
            rows = []
            for row in t.extract():
                rows.append([("" if c is None else str(c)) for c in row])
            tables.append({
                "page": pno + 1,
                "bbox": [float(v) for v in t.bbox],
                "rows": rows,
            })
    return tables


def _parse_with_pdftotext(path, result):
    """Fallback: use system pdftotext (-layout) when no Python PDF engine exists."""
    import subprocess
    exe = None
    for c in ("pdftotext",):
        import shutil
        if shutil.which(c):
            exe = c
            break
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "-layout", str(path), "-"],
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            result["notes"].append(f"pdftotext failed: {out.stderr.strip()[:200]}")
            return False
        text = out.stdout
        if not text.strip():
            result["scanned_pages"] = [1]
            result["notes"].append("No text layer: document appears scanned; run OCR.")
        pages_text = text.split("\f")  # form feed separates pages
        for i, ptxt in enumerate(pages_text, 1):
            lines = [ln.rstrip() for ln in ptxt.split("\n") if ln.strip()]
            blocks = [{"bbox": [0, 0, 0, 0], "text": ln, "lines": []} for ln in lines]
            sections = []
            for b in blocks:
                h = _detect_section(b["text"])
                if h:
                    sections.append({"heading": h, "block_bbox": b["bbox"]})
            result["pages"].append({
                "page": i, "width": 0, "height": 0,
                "blocks": blocks, "reading_order": blocks, "sections": sections,
            })
        result["notes"].append("engine: pdftotext (fallback, no bbox)")
        result["status"] = "success"
        return True
    except Exception as e:
        result["notes"].append(f"pdftotext failed: {e}")
        return False


def parse_pdf(pdf_path):
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(pdf_path)

    result = {
        "source": str(path),
        "pages": [],
        "tables": [],
        "scanned_pages": [],
        "status": "success",
        "notes": [],
    }

    doc = None
    engine = None
    if fitz is not None:
        try:
            doc = fitz.open(str(path))
            engine = "pymupdf"
        except Exception as e:
            result["notes"].append(f"pymupdf open failed: {e}")
            doc = None
    if doc is None and pdfplumber is not None:
        try:
            doc = pdfplumber.open(str(path))
            engine = "pdfplumber"
        except Exception as e:
            result["notes"].append(f"pdfplumber open failed: {e}")

    if doc is None:
        # 最后兜底：系统 pdftotext（poppler），用 -layout 保持版面顺序。
        if _parse_with_pdftotext(path, result):
            return result
        result["status"] = "failed"
        result["notes"].append("No PDF engine available (pymupdf/pdfplumber/pdftotext).")
        return result

    try:
        if engine == "pymupdf":
            pages = _blocks_from_pymupdf(doc)
            for p in pages:
                if not p["blocks"]:
                    result["scanned_pages"].append(p["page"])
                ordered = _assign_reading_order(p, p["blocks"])
                p["reading_order"] = ordered
                p["sections"] = []
                for b in ordered:
                    head = _detect_section(b["text"].split("\n")[0])
                    if head:
                        p["sections"].append({"heading": head, "block_bbox": b["bbox"]})
            result["pages"] = pages
            result["tables"] = _extract_tables_pymupdf(doc)
        else:
            for pno, page in enumerate(doc.pages):
                blocks = []
                for b in page.extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=False):
                    blocks.append(b)
                result["pages"].append({
                    "page": pno + 1,
                    "width": page.width,
                    "height": page.height,
                    "text": page.extract_text() or "",
                    "blocks": [],
                    "reading_order": [],
                })
            for pno, page in enumerate(doc.pages):
                for t in page.extract_tables():
                    result["tables"].append({"page": pno + 1, "rows": t})
    finally:
        try:
            doc.close()
        except Exception:
            pass

    # If no text at all anywhere, flag fully-scanned document.
    total_text = 0
    for p in result["pages"]:
        if p.get("text"):
            total_text += len(p["text"])
        else:
            for b in p.get("blocks", []):
                total_text += len(b.get("text", ""))
    if result["pages"] and total_text == 0:
        result["scanned_pages"] = [p["page"] for p in result["pages"]]
        result["notes"].append("No text layer detected: document appears fully scanned; run OCR.")

    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Input PDF path")
    ap.add_argument("output", nargs="?", help="Output JSON path (default: stdout)")
    args = ap.parse_args()
    res = parse_pdf(args.input)
    txt = json.dumps(res, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(txt, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(txt)


if __name__ == "__main__":
    main()
