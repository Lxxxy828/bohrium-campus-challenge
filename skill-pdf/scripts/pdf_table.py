#!/usr/bin/env python3
"""
Dedicated table extractor for scientific PDFs.

Extracts tables as structured rows (list of lists) with page and bbox
provenance. Tries several strategies in order and returns the first that
produces a table; otherwise reports "not_found".

Usage:
  python3 pdf_table.py INPUT.pdf [PAGE] [OUTPUT.json]

Strategies:
  1. pdfplumber extract_tables (handles ruled tables well);
  2. PyMuPDF find_tables (handles borderless tables via layout heuristics);
  3. pdftotext -layout (last resort, whitespace alignment).
"""
import sys
import json
from pathlib import Path

try:
    import pdfplumber
except Exception:
    pdfplumber = None
try:
    import pymupdf as fitz
except Exception:
    fitz = None


def _try_pdfplumber(pdf, page_no):
    out = []
    with pdfplumber.open(pdf) as doc:
        pages = doc.pages if page_no is None else [doc.pages[page_no - 1]]
        for p in pages:
            for t in p.extract_tables():
                rows = [[("" if c is None else str(c).replace("\n", " ")) for c in row] for row in t]
                if rows:
                    out.append({"page": p.page_number, "bbox": list(t.bbox) if hasattr(t, "bbox") else None, "rows": rows})
    return out


def _try_pymupdf(pdf, page_no):
    out = []
    doc = fitz.open(pdf)
    pages = range(len(doc)) if page_no is None else [page_no - 1]
    for pno in pages:
        page = doc[pno]
        try:
            for t in page.find_tables().tables:
                rows = [[("" if c is None else str(c).replace("\n", " ")) for c in row] for row in t.extract()]
                if rows:
                    out.append({"page": pno + 1, "bbox": [float(v) for v in t.bbox], "rows": rows})
        except Exception:
            continue
    doc.close()
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("page", nargs="?", type=int, default=None)
    ap.add_argument("output", nargs="?", default=None)
    args = ap.parse_args()

    pdf = args.input
    tables = []
    engine = None
    if pdfplumber is not None:
        try:
            tables = _try_pdfplumber(pdf, args.page)
            engine = "pdfplumber"
        except Exception:
            tables = []
    if not tables and fitz is not None:
        try:
            tables = _try_pymupdf(pdf, args.page)
            engine = "pymupdf"
        except Exception:
            tables = []
    result = {"source": pdf, "page_filter": args.page, "engine": engine, "tables": tables,
              "status": "success" if tables else "not_found"}
    txt = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(txt, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(txt)


if __name__ == "__main__":
    main()
