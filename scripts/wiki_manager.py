#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wiki_manager.py - Layer 1 KB builder for notebooklm-wiki-framework

Commands:
    python scripts/wiki_manager.py all                      # ingest all new PDFs in raw/
    python scripts/wiki_manager.py ingest raw/paper.pdf     # ingest a single PDF
    python scripts/wiki_manager.py query "search terms"     # search the KB
    python scripts/wiki_manager.py index                    # rebuild wiki/index.md

Backend config (set here or override with env vars PDF_BACKEND / LLM_BACKEND):
    PDF_BACKEND: gemini | pymupdf | mistral
    LLM_BACKEND: gemini | groq | anthropic | ollama
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# -- Config -------------------------------------------------------------------

PDF_BACKEND = os.environ.get("PDF_BACKEND", "pymupdf")  # pymupdf | gemini | mistral
LLM_BACKEND = os.environ.get("LLM_BACKEND", "gemini")   # gemini | groq | anthropic | ollama

# Gemini free tier: 15 requests/min. Sleep 4s between calls to stay safe.
GEMINI_RATE_LIMIT_SLEEP = int(os.environ.get("GEMINI_SLEEP", "4"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR      = PROJECT_ROOT / "raw"
WIKI_DIR     = PROJECT_ROOT / "wiki"
LOG_DIR      = PROJECT_ROOT / "log"
VECTORS_PATH = WIKI_DIR / ".vectors.json"
INDEX_PATH   = WIKI_DIR / "index.md"

# Domain taxonomy - edit to match your research
TAXONOMY = {
    "ML Potentials":       ["mace", "nequip", "chgnet", "schnet", "ace", "equivariant", "interatomic potential", "force field"],
    "Method Acceleration": ["dft", "active learning", "uncertainty quantification", "surrogate", "on-the-fly"],
    "Generative Models":   ["diffusion", "flow matching", "vae", "inverse design", "generative model"],
    "Drug Discovery":      ["protein", "ligand", "binding affinity", "admet", "drug discovery"],
    "Crystals & Alloys":   ["crystal", "alloy", "high-entropy", "hea", "defect", "perovskite", "lattice"],
    "Molecules":           ["molecular dynamics", "smiles", "conformer", "torsion", "molecular simulation"],
    "2D Materials":        ["mxene", "graphene", "monolayer", "heterostructure", "2d material"],
    "Proteins":            ["peptide", "enzyme", "residue", "protein folding", "alphafold"],
}


# -- PDF extraction -----------------------------------------------------------

def extract_text_gemini(pdf_path: Path) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("  FAIL google-genai not installed. Run: pip install google-genai", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=_require_env("GEMINI_API_KEY"))

    print("  Uploading PDF to Gemini...")
    uploaded = client.files.upload(
        file=str(pdf_path),
        config=types.UploadFileConfig(mime_type="application/pdf"),
    )

    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            types.Part.from_uri(file_uri=uploaded.uri, mime_type="application/pdf"),
            "Extract all text from this PDF exactly as written. "
            "Include title, authors, abstract, all sections, equations (as text), and references. "
            "Output plain text only - no markdown formatting.",
        ],
    )
    return resp.text


def extract_text_pymupdf(pdf_path: Path) -> str:
    try:
        import fitz
    except ImportError:
        print("  FAIL pymupdf not installed. Run: pip install pymupdf", file=sys.stderr)
        sys.exit(1)

    doc = fitz.open(str(pdf_path))
    return "\n\n".join(page.get_text() for page in doc)


def extract_text_mistral(pdf_path: Path) -> str:
    try:
        from mistralai import Mistral
    except ImportError:
        print("  FAIL mistralai not installed. Run: pip install mistralai", file=sys.stderr)
        sys.exit(1)

    client = Mistral(api_key=_require_env("MISTRAL_API_KEY"))

    # Upload file first — more reliable than inline base64 for large PDFs
    pdf_bytes = pdf_path.read_bytes()
    uploaded = client.files.upload(
        file={"file_name": pdf_path.name, "content": pdf_bytes},
        purpose="ocr",
    )
    try:
        signed = client.files.get_signed_url(file_id=uploaded.id)
        resp = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "document_url", "document_url": signed.url},
            include_image_base64=True,
        )
    finally:
        client.files.delete(file_id=uploaded.id)

    # Save extracted figures to wiki/assets/<stem>/
    import base64 as _b64
    assets_dir = WIKI_DIR / "assets" / pdf_path.stem
    page_texts = []
    for page in resp.pages:
        md = page.markdown
        if page.images:
            assets_dir.mkdir(parents=True, exist_ok=True)
            for img in page.images:
                img_data = _b64.b64decode(img.image_base64.split(",", 1)[-1])
                img_file = assets_dir / img.id
                img_file.write_bytes(img_data)
                # Rewrite markdown reference to local path
                md = md.replace(f"]({img.id})", f"](assets/{pdf_path.stem}/{img.id})")
        page_texts.append(md)

    return "\n\n".join(page_texts)


def extract_text(pdf_path: Path) -> str:
    backends = {
        "gemini":  extract_text_gemini,
        "pymupdf": extract_text_pymupdf,
        "mistral": extract_text_mistral,
    }
    fn = backends.get(PDF_BACKEND)
    if not fn:
        raise ValueError(f"Unknown PDF_BACKEND '{PDF_BACKEND}'. Choose: gemini | pymupdf | mistral")
    print(f"  Extracting text [{PDF_BACKEND}]...")
    return fn(pdf_path)


# -- LLM structuring ----------------------------------------------------------

STRUCTURE_PROMPT = """\
You are a research knowledge base builder for a materials science / ML researcher.
Given raw text from a research paper, produce a structured Obsidian wiki page.

Output EXACTLY this format - no preamble, no extra text outside this structure:

---
title: [Full paper title]
authors: [Lastname1 et al. or Lastname1, Lastname2, Lastname3]
year: [4-digit year, or "unknown"]
venue: [Journal or conference abbreviation, e.g. NeurIPS 2024, Nature, arXiv]
type: paper
tags: [#tag1 #tag2 - use lowercase hyphenated tags]
---

# [Full paper title]

## Abstract
[2-3 sentence summary of the paper's core contribution and significance]

## Key Findings
- [Specific finding with numbers/metrics where available]
- [Second finding]
- [Third finding]

## Methods
- [Main method, model, or architecture]
- [Key dataset or benchmark used]
- [Important technical detail]

## Results
- [Best reported metric vs. baseline]
- [Key comparison result]

## Limitations
- [Stated limitation or identified gap]

## Relevance
[1-2 sentences on relevance to ML potentials / materials science / generative models]

## Citation
[Authors] ([year]). [Title]. [Venue].
"""


def structure_with_llm(raw_text: str, pdf_name: str) -> str:
    truncated = raw_text[:14000]
    user_msg = f"Paper filename: {pdf_name}\n\nRaw extracted text:\n{truncated}"

    llm_map = {
        "gemini":    _llm_gemini,
        "groq":      _llm_groq,
        "anthropic": _llm_anthropic,
        "ollama":    _llm_ollama,
    }
    fn = llm_map.get(LLM_BACKEND)
    if not fn:
        raise ValueError(f"Unknown LLM_BACKEND '{LLM_BACKEND}'. Choose: gemini | groq | anthropic | ollama")

    print(f"  Structuring into wiki page [{LLM_BACKEND}]...")
    return fn(STRUCTURE_PROMPT, user_msg)


def _llm_gemini(system: str, user: str) -> str:
    from google import genai
    client = genai.Client(api_key=_require_env("GEMINI_API_KEY"))

    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user,
                config={"system_instruction": system, "max_output_tokens": 2000},
            )
            time.sleep(GEMINI_RATE_LIMIT_SLEEP)
            return resp.text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 60 * (attempt + 1)
                print(f"  Rate limited - waiting {wait}s before retry {attempt + 1}/3...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Gemini rate limit exceeded after 3 retries.")


def _llm_groq(system: str, user: str) -> str:
    try:
        from groq import Groq
    except ImportError:
        print("  FAIL groq not installed. Run: pip install groq", file=sys.stderr)
        sys.exit(1)
    client = Groq(api_key=_require_env("GROQ_API_KEY"))
    resp = client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=2000,
    )
    return resp.choices[0].message.content


def _llm_anthropic(system: str, user: str) -> str:
    try:
        import anthropic
    except ImportError:
        print("  FAIL anthropic not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)
    client = anthropic.Anthropic(api_key=_require_env("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _llm_ollama(system: str, user: str) -> str:
    import requests
    model = os.environ.get("OLLAMA_MODEL", "llama3")
    resp = requests.post("http://localhost:11434/api/generate", json={
        "model": model,
        "system": system,
        "prompt": user,
        "stream": False,
    }, timeout=120)
    return resp.json()["response"]


# -- Wiki page writing --------------------------------------------------------

def _auto_tags(text: str) -> list:
    text_lower = text.lower()
    tags = []
    for domain, keywords in TAXONOMY.items():
        if any(kw in text_lower for kw in keywords):
            slug = domain.lower().replace(" & ", "-and-").replace(" ", "-")
            tags.append(f"#{slug}")
    return tags or ["#uncategorized"]


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.lower()).strip("-")[:60]


def write_wiki_page(structured: str, pdf_path: Path) -> Path:
    WIKI_DIR.mkdir(exist_ok=True)

    title_m = re.search(r"^title:\s*(.+)$", structured, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else pdf_path.stem
    page_path = WIKI_DIR / f"{_slug(title)}.md"

    # Merge auto-detected tags into frontmatter
    auto_tags = _auto_tags(structured)
    if re.search(r"^tags:\s*(.+)$", structured, re.MULTILINE):
        def _merge(m):
            existing = set(m.group(2).split())
            return m.group(1) + " ".join(sorted(existing | set(auto_tags)))
        structured = re.sub(r"(tags:\s*)(.+)", _merge, structured)
    else:
        structured = structured.replace("type: paper", f"type: paper\ntags: {' '.join(auto_tags)}", 1)

    structured += f"\n\n---\n*Ingested: {datetime.now().strftime('%Y-%m-%d')} | Source: `{pdf_path.name}`*\n"
    page_path.write_text(structured, encoding="utf-8")
    return page_path


# -- Vectors index (keyword-based, for Dao agent search) ---------------------

def update_vectors(page_path: Path, structured: str) -> None:
    vectors = {}
    if VECTORS_PATH.exists():
        try:
            vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    def _field(pattern):
        m = re.search(pattern, structured, re.MULTILINE)
        return m.group(1).strip() if m else ""

    findings = re.findall(r"^- (.+)$", structured, re.MULTILINE)

    vectors[page_path.stem] = {
        "title":    _field(r"^title:\s*(.+)$"),
        "year":     _field(r"^year:\s*(.+)$"),
        "authors":  _field(r"^authors:\s*(.+)$"),
        "venue":    _field(r"^venue:\s*(.+)$"),
        "tags":     _field(r"^tags:\s*(.+)$"),
        "keywords": " ".join(findings[:6]),
        "page":     page_path.name,
    }

    VECTORS_PATH.write_text(json.dumps(vectors, indent=2, ensure_ascii=False), encoding="utf-8")


# -- Index rebuild ------------------------------------------------------------

def rebuild_index() -> None:
    pages = sorted(WIKI_DIR.glob("*.md"), key=lambda p: p.stem)
    lines = [
        "# Wiki Index\n\n",
        f"*Updated: {datetime.now().strftime('%Y-%m-%d')} - {len(pages) - 1} pages*\n\n",
    ]

    tagged = {}
    for page in pages:
        if page.name == "index.md":
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        tags_m  = re.search(r"^tags:\s*(.+)$",  text, re.MULTILINE)
        year_m  = re.search(r"^year:\s*(.+)$",   text, re.MULTILINE)
        title_m = re.search(r"^title:\s*(.+)$",  text, re.MULTILINE)

        first_tag = tags_m.group(1).split()[0]  if tags_m  else "#uncategorized"
        year      = year_m.group(1).strip()     if year_m  else ""
        title     = title_m.group(1).strip()    if title_m else page.stem

        tagged.setdefault(first_tag, []).append((year, title, page.stem))

    for tag, entries in sorted(tagged.items()):
        lines.append(f"## {tag}\n\n")
        for year, title, slug in sorted(entries, key=lambda x: x[0], reverse=True):
            lines.append(f"- [[{slug}|{title}]] ({year})\n")
        lines.append("\n")

    INDEX_PATH.write_text("".join(lines), encoding="utf-8")
    print(f"  Index rebuilt: {len(pages) - 1} pages in {len(tagged)} topic(s).")


# -- Query --------------------------------------------------------------------

def query_kb(search: str) -> None:
    if not VECTORS_PATH.exists():
        print("No index found. Run 'all' first to ingest papers.")
        return

    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    terms = search.lower().split()
    results = []

    for slug, meta in vectors.items():
        haystack = f"{meta['title']} {meta['tags']} {meta['keywords']} {meta['authors']}".lower()
        score = sum(1 for t in terms if t in haystack)
        if score > 0:
            results.append((score, meta["title"], meta.get("year", ""), meta.get("venue", ""), slug))

    results.sort(reverse=True)
    if not results:
        print("No matches found.")
        return

    print(f"\nResults for: '{search}'\n" + "-" * 56)
    for score, title, year, venue, slug in results[:10]:
        print(f"  [{score}]  {title} ({year})")
        if venue:
            print(f"        {venue}")
        print(f"        wiki/{slug}.md\n")


# -- Ingest pipeline ----------------------------------------------------------

def ingest_pdf(pdf_path: Path) -> None:
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        print(f"FAIL File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n>> {pdf_path.name}")
    LOG_DIR.mkdir(exist_ok=True)

    log_path = LOG_DIR / (pdf_path.stem + ".txt")
    if log_path.exists():
        print("  Using cached extraction from log/")
        raw_text = log_path.read_text(encoding="utf-8")
    else:
        raw_text = extract_text(pdf_path)
        log_path.write_text(raw_text, encoding="utf-8")
        print(f"  Cached to log/{log_path.name}")

    structured = structure_with_llm(raw_text, pdf_path.name)
    page_path  = write_wiki_page(structured, pdf_path)
    update_vectors(page_path, structured)
    print(f"  OK  wiki/{page_path.name}")


def ingest_all() -> None:
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {RAW_DIR}/")
        print("Drop your paper PDFs into the raw/ folder and run again.")
        return

    existing_slugs = {p.stem for p in WIKI_DIR.glob("*.md")} if WIKI_DIR.exists() else set()
    new_pdfs = [p for p in pdfs if _slug(p.stem) not in existing_slugs]

    if not new_pdfs:
        print(f"All {len(pdfs)} PDF(s) already ingested. Drop new papers into raw/ and try again.")
        return

    print(f"Found {len(new_pdfs)} new PDF(s) to ingest (skipping {len(pdfs) - len(new_pdfs)} already done)...")
    failed = 0
    for pdf in new_pdfs:
        try:
            ingest_pdf(pdf)
        except Exception as e:
            print(f"  FAIL  {pdf.name} - {e}", file=sys.stderr)
            failed += 1

    rebuild_index()
    total = len(list(WIKI_DIR.glob("*.md"))) - 1
    print(f"\nDone. {len(new_pdfs) - failed} ingested, {failed} failed. Wiki: {total} pages total.")


# -- Helpers ------------------------------------------------------------------

def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"FAIL  {name} not set.", file=sys.stderr)
        print(f"      Set it with:  $env:{name} = \"your-key-here\"", file=sys.stderr)
        sys.exit(1)
    return val


# -- CLI ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wiki KB builder - notebooklm-wiki-framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/wiki_manager.py all\n"
            "  python scripts/wiki_manager.py ingest raw/mace-paper.pdf\n"
            "  python scripts/wiki_manager.py query 'equivariant ML potentials'\n"
            "  python scripts/wiki_manager.py index\n\n"
            "Backends (set env vars to override defaults):\n"
            "  PDF_BACKEND=gemini|pymupdf|mistral   (default: gemini)\n"
            "  LLM_BACKEND=gemini|groq|anthropic|ollama  (default: gemini)\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("all",   help="Ingest all new PDFs from raw/")
    sub.add_parser("index", help="Rebuild wiki/index.md from existing pages")

    p_ingest = sub.add_parser("ingest", help="Ingest a single PDF file")
    p_ingest.add_argument("pdf", help="Path to the PDF file")

    p_query = sub.add_parser("query", help="Keyword search across the KB")
    p_query.add_argument("search", help="Search terms (quoted string)")

    args = parser.parse_args()

    if args.command == "all":
        ingest_all()
    elif args.command == "ingest":
        ingest_pdf(Path(args.pdf))
        rebuild_index()
    elif args.command == "query":
        query_kb(args.search)
    elif args.command == "index":
        rebuild_index()


if __name__ == "__main__":
    main()
