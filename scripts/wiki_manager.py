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
    LLM_BACKEND: gemini | groq | anthropic | ollama | mistral
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
LLM_BACKEND = os.environ.get("LLM_BACKEND", "gemini")   # gemini | groq | anthropic | ollama | mistral

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
    "ML Potentials":          ["mace", "nequip", "chgnet", "schnet", "ace", "equivariant", "interatomic potential", "force field", "gaussian approximation potential", "gap potential", "atomic cluster expansion"],
    "Method Acceleration":    ["dft", "active learning", "uncertainty quantification", "surrogate", "on-the-fly", "ab initio", "first principles", "density functional"],
    "Generative Models":      ["diffusion", "flow matching", "vae", "inverse design", "generative model"],
    "Drug Discovery":         ["ligand", "binding affinity", "admet", "drug discovery"],
    "Crystals & Alloys":      ["crystal", "alloy", "high-entropy", "hea", "defect", "lattice", "bcc", "fcc", "solid solution"],
    "Molecules":              ["molecular dynamics", "smiles", "conformer", "torsion", "molecular simulation", "charge transfer", "organic semiconductor", "electron coupling"],
    "2D Materials":           ["mxene", "graphene", "monolayer", "heterostructure", "2d material"],
    "Proteins":               ["peptide", "enzyme", "residue", "protein folding", "alphafold"],
    "Phonons & Anharmonicity": ["phonon", "phonopy", "anharmonic", "anharmonicity", "thermal conductivity", "force constant", "brillouin", "phono3py", "lattice dynamics", "heat transport"],
    "Perovskites":            ["perovskite", "halide", "solar cell", "photovoltaic", "thermoelectric", "methylammonium", "cesium lead", "lead iodide", "optoelectronic"],
    "Electrochemistry":       ["battery", "oxygen reduction", "superoxide", "electrocatalyst", "orr", "oer", "metal-air", "li-air", "electrode", "potassium-oxygen", "overpotential"],
    "Quantum Theory":         ["angular momentum", "wigner", "clebsch-gordan", "hamiltonian", "quantum field", "wave function", "spin", "commutator", "hilbert space", "quantum mechanics"],
    "Gaussian Processes":     ["gaussian process", "gp regression", "kernel matrix", "bayesian optim", "acquisition function", "covariance function", "radial basis", "posterior mean"],
    "Personal":               ["booking confirmation", "statement of registration", "tourist visa", "schengen", "seattle plan", "research proposal confirmation", "late stage review"],
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
    import base64
    try:
        from mistralai import Mistral
    except ImportError:
        print("  FAIL mistralai not installed. Run: pip install mistralai", file=sys.stderr)
        sys.exit(1)

    client = Mistral(api_key=_require_env("MISTRAL_API_KEY"))
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode()
    resp = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{pdf_b64}",
        },
        include_image_base64=False,
    )
    return "\n\n".join(page.markdown for page in resp.pages)


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
You are a research knowledge base builder for a materials science / ML potentials researcher.
Given raw text from a research paper, produce a dense, accurate Obsidian wiki page.

Rules:
- Extract only facts present in the text. Do not hallucinate or invent details.
- NEVER write placeholder text like "[See full text...]" — if a section has no content, write N/A.
- Be specific: include numbers, metrics, model names, dataset names exactly as stated.
- Tags must be chosen only from these domains (use lowercase-hyphenated form):
  #ml-potentials | #method-acceleration | #generative-models | #drug-discovery
  #crystals-and-alloys | #molecules | #2d-materials | #proteins

Output EXACTLY this format — no preamble, no text outside this structure:

---
title: [Full paper title as it appears in the text]
authors: [Lastname1 et al. — if >3 authors, else Lastname1, Lastname2, Lastname3]
year: [4-digit year, or "unknown"]
venue: [Journal or conference, e.g. NeurIPS 2024, Nature, Physical Review B, arXiv]
type: paper
tags: [#tag1 #tag2 — from domain list above only]
---

# [Full paper title]

## Abstract
[2–3 sentences: core contribution, primary method, and main quantitative result. Be precise.]

## Key Findings
- [Specific finding with numbers/metrics where available]
- [Second finding]
- [Third finding — add more bullet points if important]

## Methods
- [Primary method, model name, or architecture]
- [Key dataset or benchmark used]
- [Important implementation or training detail]

## Results
- [Best reported metric vs. baseline, with exact numbers]
- [Key comparison result]
- [Notable ablation or sensitivity result — N/A if none]

## Limitations
- [Stated limitation or gap — N/A if none mentioned]

## Open Questions
- [Unresolved question or stated future work — N/A if none mentioned]

## Relevance
[1–2 sentences on relevance to ML potentials / materials simulation / generative models for materials]

## Citation
[Authors] ([year]). [Title]. [Venue].
"""


def structure_with_llm(raw_text: str, pdf_name: str) -> str:
    truncated = raw_text[:25000]
    user_msg = f"Paper filename: {pdf_name}\n\nRaw extracted text:\n{truncated}"

    llm_map = {
        "gemini":    _llm_gemini,
        "groq":      _llm_groq,
        "anthropic": _llm_anthropic,
        "ollama":    _llm_ollama,
        "mistral":   _llm_mistral,
    }
    fn = llm_map.get(LLM_BACKEND)
    if not fn:
        raise ValueError(f"Unknown LLM_BACKEND '{LLM_BACKEND}'. Choose: gemini | groq | anthropic | ollama | mistral")

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


def _llm_mistral(system: str, user: str) -> str:
    try:
        from mistralai import Mistral
    except ImportError:
        print("  FAIL mistralai not installed. Run: pip install mistralai", file=sys.stderr)
        sys.exit(1)
    model = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
    sleep_s = int(os.environ.get("MISTRAL_SLEEP", "2"))
    client = Mistral(api_key=_require_env("MISTRAL_API_KEY"))
    for attempt in range(4):
        try:
            resp = client.chat.complete(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=2000,
            )
            time.sleep(sleep_s)
            return resp.choices[0].message.content
        except Exception as e:
            if "429" in str(e) or "rate_limited" in str(e).lower():
                wait = 60 * (attempt + 1)
                print(f"  Rate limited — waiting {wait}s before retry {attempt + 1}/3...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Mistral rate limit exceeded after 3 retries.")


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


def reingest_all(fresh: bool = False) -> None:
    """Re-ingest all PDFs, overwriting existing wiki pages.

    fresh=True: delete log/ cache first, forcing full re-extraction via PDF_BACKEND.
    fresh=False: reuse cached log/ text, only regenerate wiki pages via LLM_BACKEND.
    """
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {RAW_DIR}/")
        return

    if fresh:
        print(f"Clearing log/ cache — will re-extract {len(pdfs)} PDF(s) via [{PDF_BACKEND}]...")
        for log_file in LOG_DIR.glob("*.txt"):
            log_file.unlink()
    else:
        cached = len(list(LOG_DIR.glob("*.txt"))) if LOG_DIR.exists() else 0
        print(f"Re-ingesting {len(pdfs)} PDF(s) — reusing {cached} cached extraction(s), LLM=[{LLM_BACKEND}]...")

    # Clear existing wiki pages (except index)
    if WIKI_DIR.exists():
        for page in WIKI_DIR.glob("*.md"):
            if page.name != "index.md":
                page.unlink()
        print(f"  Cleared existing wiki pages.")

    failed = 0
    for pdf in pdfs:
        try:
            ingest_pdf(pdf)
        except Exception as e:
            print(f"  FAIL  {pdf.name} - {e}", file=sys.stderr)
            failed += 1

    rebuild_index()
    total = len(list(WIKI_DIR.glob("*.md"))) - 1
    print(f"\nDone. {len(pdfs) - failed} ingested, {failed} failed. Wiki: {total} pages total.")


# -- Hub pages ----------------------------------------------------------------

def _tag_to_hub_slug(tag: str) -> str:
    return "hub-" + tag.lstrip("#")


def _hub_display_name(tag: str) -> str:
    return tag.lstrip("#").replace("-and-", " & ").replace("-", " ").title()


def make_hubs() -> None:
    """Create one hub page per taxonomy category and add ## Categories links to every paper."""
    _skip_tags = {"#uncategorized", "#n/a", "#na", "#personal"}

    # Scan ALL wiki page files directly — don't rely on vectors.json
    def _read_pages():
        for page_path in sorted(WIKI_DIR.glob("*.md")):
            if page_path.name == "index.md" or page_path.stem.startswith("hub-"):
                continue
            text = page_path.read_text(encoding="utf-8")
            if "type: hub" in text:
                continue
            title_m = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
            year_m  = re.search(r"^year:\s*(.+)$",  text, re.MULTILINE)
            tags_m  = re.search(r"^tags:\s*(.+)$",  text, re.MULTILINE)
            title = title_m.group(1).strip() if title_m else page_path.stem
            year  = year_m.group(1).strip()  if year_m  else ""
            tags  = tags_m.group(1).split()  if tags_m  else []
            yield page_path, text, page_path.stem, title, year, tags

    # Build tag → [(slug, title, year)]
    tag_papers: dict = {}
    for page_path, text, slug, title, year, tags in _read_pages():
        for tag in tags:
            tag = tag.strip().lower()
            if not tag.startswith("#") or tag in _skip_tags:
                continue
            tag_papers.setdefault(tag, []).append((slug, title, year))

    # Write one hub page per tag
    hub_slugs: dict = {}
    for tag, papers in sorted(tag_papers.items()):
        hub_slug = _tag_to_hub_slug(tag)
        hub_slugs[tag] = hub_slug
        display = _hub_display_name(tag)
        lines = [
            f"---\ntitle: {display} — Research Hub\ntype: hub\ntags: {tag}\n---\n\n",
            f"# {display}\n\n",
            f"*Hub — {len(papers)} papers in this cluster.*\n\n",
            "## Papers\n\n",
        ]
        for s, t, y in sorted(papers, key=lambda x: x[2], reverse=True):
            suffix = f" ({y})" if y and y != "unknown" else ""
            lines.append(f"- [[{s}|{t}]]{suffix}\n")
        (WIKI_DIR / f"{hub_slug}.md").write_text("".join(lines), encoding="utf-8")
        print(f"  Hub: {hub_slug}.md  ({len(papers)} papers)")

    # Add ## Categories section to every paper page
    updated = 0
    for page_path, text, slug, title, year, tags in _read_pages():
        hub_links = [
            f"- [[{hub_slugs[t.strip().lower()]}|{_hub_display_name(t.strip().lower())}]]"
            for t in tags if t.strip().lower() in hub_slugs
        ]
        if not hub_links:
            continue

        cat_section = "\n\n## Categories\n" + "\n".join(hub_links)
        text = re.sub(r"\n\n## Categories\n.*?(?=\n\n##|\n\n---|\Z)", "",
                      text, flags=re.DOTALL)
        anchor = re.search(r"\n\n## See Also\n|\n\n---\n\*Ingested:", text)
        pos = anchor.start() if anchor else len(text)
        text = text[:pos] + cat_section + text[pos:]
        page_path.write_text(text, encoding="utf-8")
        updated += 1

    # Write meta-hub
    meta_lines = [
        "---\ntitle: Research Knowledge Base\ntype: hub\n---\n\n",
        "# Research Knowledge Base\n\n",
        "*Top-level hub — links to all research clusters.*\n\n",
        "## Clusters\n\n",
    ]
    for tag in sorted(hub_slugs):
        count = len(tag_papers.get(tag, []))
        meta_lines.append(f"- [[{hub_slugs[tag]}|{_hub_display_name(tag)}]] ({count} papers)\n")
    (WIKI_DIR / "hub-index.md").write_text("".join(meta_lines), encoding="utf-8")

    print(f"\n  {len(hub_slugs)} category hubs created: wiki/hub-*.md")
    print(f"  Categories section added to {updated} paper pages.")
    print(f"  Meta-hub: wiki/hub-index.md")


# -- Tag cleanup --------------------------------------------------------------

_BAD_TAGS = {"#n/a", "#na", "#uncategorized"}


def fix_tags() -> None:
    """Strip bad tags (#N/A, #uncategorized) and re-run keyword matcher on all pages."""
    pages = sorted(WIKI_DIR.glob("*.md"))
    fixed = skipped = 0

    for page in pages:
        if page.name == "index.md":
            continue
        text = page.read_text(encoding="utf-8")
        tags_m = re.search(r"^(tags:\s*)(.+)$", text, re.MULTILINE)
        if not tags_m:
            continue

        existing = set(tags_m.group(2).split())
        clean = {t for t in existing if t.lower() not in _BAD_TAGS}
        auto = set(_auto_tags(text))
        # auto_tags returns ["#uncategorized"] if nothing matched — skip that
        if auto == {"#uncategorized"}:
            auto = set()
        merged = clean | auto or {"#uncategorized"}

        new_tags_line = tags_m.group(1) + " ".join(sorted(merged))
        new_text = re.sub(r"^tags:\s*.+$", new_tags_line, text, flags=re.MULTILINE)

        if new_text != text:
            page.write_text(new_text, encoding="utf-8")
            fixed += 1
        else:
            skipped += 1

    rebuild_index()
    print(f"  Tags fixed: {fixed} pages updated, {skipped} unchanged.")


# -- Cross-linking (See Also) -------------------------------------------------

def _tag_set(tags_str: str) -> set:
    return {t.strip().lower() for t in tags_str.split() if t.startswith("#")}


def _keyword_tokens(meta: dict) -> set:
    raw = f"{meta['title']} {meta['keywords']}".lower()
    tokens = set(re.findall(r"[a-z]{4,}", raw))
    return tokens - {"with", "from", "that", "this", "they", "have", "been",
                     "into", "their", "using", "based", "which", "more", "also",
                     "than", "show", "such", "high", "both", "between", "model"}


def link_pages(top_n: int = 5) -> None:
    """Add/update ## See Also wikilinks to each wiki page using the vectors index."""
    if not VECTORS_PATH.exists():
        print("No vectors index found. Run 'all' first.")
        return

    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    updated = 0

    for slug, meta in vectors.items():
        page_path = WIKI_DIR / f"{slug}.md"
        if not page_path.exists():
            continue

        my_tags = _tag_set(meta.get("tags", ""))
        my_tokens = _keyword_tokens(meta)

        scores = []
        for other_slug, other_meta in vectors.items():
            if other_slug == slug:
                continue
            tag_overlap = len(my_tags & _tag_set(other_meta.get("tags", "")))
            kw_overlap  = len(my_tokens & _keyword_tokens(other_meta))
            score = tag_overlap * 3 + kw_overlap
            if score > 0:
                scores.append((score, other_slug, other_meta["title"]))

        scores.sort(reverse=True)
        top = scores[:top_n]
        if not top:
            continue

        see_also = "\n\n## See Also\n" + "\n".join(
            f"- [[{s}|{t}]]" for _, s, t in top
        )

        text = page_path.read_text(encoding="utf-8")
        # Remove old See Also section if present
        text = re.sub(r"\n\n## See Also\n.*", "", text, flags=re.DOTALL)
        # Remove trailing ingestion footer, re-append after See Also
        footer_m = re.search(r"\n\n---\n\*Ingested:.*", text, re.DOTALL)
        footer = footer_m.group(0) if footer_m else ""
        body = text[:footer_m.start()] if footer_m else text

        page_path.write_text(body + see_also + footer, encoding="utf-8")
        updated += 1

    print(f"  See Also links added/updated on {updated} pages.")


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

    p_reingest = sub.add_parser("reingest", help="Re-ingest all PDFs, overwriting existing wiki pages")
    p_reingest.add_argument("--fresh", action="store_true",
                            help="Clear log/ cache and re-extract PDFs via PDF_BACKEND (slower)")

    sub.add_parser("fix-tags", help="Strip bad tags and re-run keyword matcher on all pages")

    p_link = sub.add_parser("link", help="Add See Also wikilinks between related pages")
    p_link.add_argument("--top", type=int, default=5,
                        help="Number of related pages to link per page (default: 5)")

    sub.add_parser("make-hubs", help="Create category hub pages and add Categories links to all papers")

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
    elif args.command == "reingest":
        reingest_all(fresh=args.fresh)
    elif args.command == "fix-tags":
        fix_tags()
    elif args.command == "link":
        link_pages(top_n=args.top)
    elif args.command == "make-hubs":
        make_hubs()


if __name__ == "__main__":
    main()
