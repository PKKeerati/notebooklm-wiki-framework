#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mistral_ocr_client.py — Standalone Mistral OCR for research PDFs (base64 inline)

Usage:
    python scripts/mistral_ocr_client.py raw/paper.pdf
    python scripts/mistral_ocr_client.py raw/
    python scripts/mistral_ocr_client.py raw/ --save-images
    python scripts/mistral_ocr_client.py raw/ --output-dir log/ --format json

Requirements:
    pip install mistralai
    MISTRAL_API_KEY env var set
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"FAIL  {name} not set.", file=sys.stderr)
        print(f"      Set it with:  $env:{name} = \"your-key-here\"", file=sys.stderr)
        sys.exit(1)
    return val


def ocr_pdf(pdf_path: Path, client, save_images: bool, output_dir: Path) -> dict:
    """OCR a single PDF using base64 inline. Returns dict with keys: path, pages, num_pages, num_images."""
    print(f"  Encoding {pdf_path.name} ({pdf_path.stat().st_size // 1024} KB)...")
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode()

    print(f"  Running OCR...")
    resp = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{pdf_b64}",
        },
        include_image_base64=save_images,
    )

    pages = []
    total_images = 0
    images_dir = output_dir / "images" / pdf_path.stem

    for i, page in enumerate(resp.pages):
        md = page.markdown
        page_images = []

        if save_images and page.images:
            images_dir.mkdir(parents=True, exist_ok=True)
            for img in page.images:
                raw = base64.b64decode(img.image_base64.split(",", 1)[-1])
                img_file = images_dir / img.id
                img_file.write_bytes(raw)
                page_images.append(str(img_file))
                md = md.replace(f"]({img.id})", f"](images/{pdf_path.stem}/{img.id})")
                total_images += 1

        pages.append({"page": i + 1, "markdown": md, "images": page_images})

    return {
        "source": pdf_path.name,
        "num_pages": len(pages),
        "num_images": total_images,
        "pages": pages,
    }


def save_output(result: dict, output_dir: Path, fmt: str) -> Path:
    stem = Path(result["source"]).stem
    if fmt == "json":
        out_path = output_dir / f"{stem}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        out_path = output_dir / f"{stem}.md"
        lines = [f"# {result['source']}\n\n"]
        for page in result["pages"]:
            lines.append(f"---\n*Page {page['page']}*\n\n")
            lines.append(page["markdown"])
            lines.append("\n\n")
        out_path.write_text("".join(lines), encoding="utf-8")
    return out_path


def run(pdf_targets: list, save_images: bool, output_dir: Path, fmt: str) -> None:
    try:
        from mistralai import Mistral
    except ImportError:
        print("FAIL  mistralai not installed. Run: pip install mistralai", file=sys.stderr)
        sys.exit(1)

    client = Mistral(api_key=_require_env("MISTRAL_API_KEY"))
    output_dir.mkdir(parents=True, exist_ok=True)

    ok = failed = 0
    for idx, pdf_path in enumerate(pdf_targets, 1):
        print(f"\n[{idx}/{len(pdf_targets)}] {pdf_path.name}")
        try:
            result = ocr_pdf(pdf_path, client, save_images, output_dir)
            out_path = save_output(result, output_dir, fmt)
            img_note = f", {result['num_images']} images" if result["num_images"] else ""
            print(f"  OK  {result['num_pages']} pages{img_note} → {out_path}")
            ok += 1
        except Exception as e:
            print(f"  FAIL  {e}", file=sys.stderr)
            failed += 1

    print(f"\nDone. {ok} succeeded, {failed} failed. Output: {output_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mistral OCR — extract text (and figures) from research PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/mistral_ocr_client.py raw/paper.pdf\n"
            "  python scripts/mistral_ocr_client.py raw/\n"
            "  python scripts/mistral_ocr_client.py raw/ --save-images\n"
            "  python scripts/mistral_ocr_client.py raw/ --output-dir log/ --format json\n"
        ),
    )
    parser.add_argument("target", help="PDF file or directory of PDFs")
    parser.add_argument("--save-images", action="store_true", help="Extract and save figures")
    parser.add_argument("--output-dir", default="log", help="Output directory (default: log/)")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown",
                        help="Output format (default: markdown)")
    args = parser.parse_args()

    target = Path(args.target)
    if target.is_dir():
        pdfs = sorted(target.glob("*.pdf"))
        if not pdfs:
            print(f"No PDFs found in {target}/", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(pdfs)} PDF(s) in {target}/")
    elif target.is_file() and target.suffix.lower() == ".pdf":
        pdfs = [target]
    else:
        print(f"FAIL  '{target}' is not a PDF file or directory.", file=sys.stderr)
        sys.exit(1)

    run(pdfs, args.save_images, Path(args.output_dir), args.format)


if __name__ == "__main__":
    main()
