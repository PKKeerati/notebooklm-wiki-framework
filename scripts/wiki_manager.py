#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wiki_manager.py - Layer 1 KB builder for notebooklm-wiki-framework

Commands:
    python scripts/wiki_manager.py all                          # ingest all new PDFs in raw/
    python scripts/wiki_manager.py ingest raw/paper.pdf        # ingest a single PDF
    python scripts/wiki_manager.py ingest raw/paper.pdf --claims  # ingest + extract claims
    python scripts/wiki_manager.py query "search terms"        # keyword search across the KB
    python scripts/wiki_manager.py query "search terms" --semantic  # semantic (embedding) search
    python scripts/wiki_manager.py index                        # rebuild wiki/index.md
    python scripts/wiki_manager.py index-vectors               # build semantic embedding index
    python scripts/wiki_manager.py lint                         # check for broken wikilinks & orphans
    python scripts/wiki_manager.py export "OER catalysis" --format marp  # generate deliverable
    python scripts/wiki_manager.py crystallize output/run/research.md    # distill mission → concept page

Backend config (set here or override with env vars PDF_BACKEND / LLM_BACKEND):
    PDF_BACKEND: gemini | pymupdf | mistral
    LLM_BACKEND: gemini | groq | anthropic | ollama | mistral
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import yaml
from pathlib import Path as _Path
try:
    from dotenv import load_dotenv
    load_dotenv(_Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Force UTF-8 I/O on Windows (handles Unicode chars in filenames/output)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# -- Config -------------------------------------------------------------------

PDF_BACKEND = os.environ.get("PDF_BACKEND", "pymupdf")   # pymupdf | gemini | mistral
LLM_BACKEND = os.environ.get("LLM_BACKEND", "gemini")    # gemini | groq | anthropic | ollama | mistral
EXTRACT_CLAIMS = os.environ.get("EXTRACT_CLAIMS", "0") == "1"  # set to "1" to enable per-PDF claim extraction

# Gemini free tier: 15 requests/min. Sleep 4s between calls to stay safe.
GEMINI_RATE_LIMIT_SLEEP = int(os.environ.get("GEMINI_SLEEP", "4"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR      = PROJECT_ROOT / os.environ.get("RAW_DIR", "raw")
WIKI_DIR     = PROJECT_ROOT / "wiki"
LOG_DIR      = PROJECT_ROOT / "log"
VECTORS_PATH = WIKI_DIR / ".vectors.json"
INDEX_PATH   = WIKI_DIR / "index.md"

# Domain taxonomy - edit to match your research
TAXONOMY = {
    # -- ML / simulation methods -----------------------------------------------
    "ML Potentials":          ["mace", "nequip", "chgnet", "schnet", "ace", "equivariant", "interatomic potential", "force field", "gaussian approximation potential", "gap potential", "atomic cluster expansion", "neural network potential", "mlip", "universal potential"],
    "Method Acceleration":    ["dft", "active learning", "uncertainty quantification", "surrogate", "on-the-fly", "ab initio", "first principles", "density functional", "kohn-sham", "vasp", "wien2k"],
    "Generative Models":      ["diffusion", "flow matching", "vae", "inverse design", "generative model", "crystal generation", "periodic material"],
    "Drug Discovery":         ["ligand", "binding affinity", "admet", "drug discovery"],

    # -- Materials systems ------------------------------------------------------
    "Crystals & Alloys":      ["crystal", "alloy", "high-entropy", "hea", "defect", "lattice", "bcc", "fcc", "solid solution", "intermetallic", "grain boundary"],
    "Molecules":              ["molecular dynamics", "smiles", "conformer", "torsion", "molecular simulation", "organic semiconductor", "electron coupling", "transfer integral", "charge transport", "hopping", "mobility", "organic thin film", "pentacene", "reorganization energy"],
    "2D Materials":           ["mxene", "graphene", "monolayer", "heterostructure", "2d material", "transition metal dichalcogenide", "moiré", "bilayer"],
    "Proteins":               ["peptide", "enzyme", "residue", "protein folding", "alphafold"],
    "Perovskites":            ["perovskite", "halide", "solar cell", "photovoltaic", "thermoelectric", "methylammonium", "cesium lead", "lead iodide", "optoelectronic", "hybrid perovskite"],
    "Glasses & Disorder":     ["glass", "amorphous", "boson peak", "disorder", "vibrational instability", "supercooled liquid", "liquid structure"],

    # -- Physical phenomena -----------------------------------------------------
    "Phonons & Anharmonicity": ["phonon", "phonopy", "anharmonic", "anharmonicity", "thermal conductivity", "force constant", "brillouin", "phono3py", "lattice dynamics", "heat transport", "thermal transport", "gruneisen"],
    "Electrochemistry":       ["battery", "oxygen reduction", "superoxide", "electrocatalyst", "orr", "oer", "metal-air", "li-air", "electrode", "potassium-oxygen", "overpotential", "sodium-air", "na-o2", "k-o2", "electrolyte", "dendrite", "potassium superoxide"],
    "Quantum Photonics":      ["photonics", "quantum optic", "photonic integrated", "quantum communication", "single photon", "optical circuit", "quantum light", "entanglement", "qubit", "laser"],

    # -- Theory & mathematics --------------------------------------------------
    "Quantum Theory":         ["angular momentum", "wigner", "clebsch-gordan", "hamiltonian", "quantum field", "wave function", "spin", "commutator", "hilbert space", "quantum mechanics", "tensor operator", "spherical harmonic", "young tableau", "irreducible representation", "hydrogen atom"],
    "Group Theory":           ["group theory", "representation theory", "character table", "symmetry group", "point group", "space group", "lie group", "so(3)", "o(3)", "rotation group", "irreducible", "symmetric group"],
    "Applied Mathematics":    ["complex number", "differential calculus", "integral", "vector calculus", "fourier", "laplace transform", "linear algebra", "eigenvalue", "tensor calculus", "kronecker"],

    # -- Machine learning & statistics -----------------------------------------
    "Gaussian Processes":     ["gaussian process", "gp regression", "kernel matrix", "bayesian optim", "acquisition function", "covariance function", "radial basis", "posterior mean", "gaussian cox", "kernel learning", "spectral mixture", "derivative gaussian", "gaussian process regression"],
    "ML Theory":              ["neural network", "deep learning", "transformer", "graph neural", "message passing", "attention", "equivariant network", "invariant", "data-driven", "machine learning", "regression", "classification", "training", "benchmark"],

    # -- Hydrogen storage — materials ------------------------------------------
    "Hydrogen Storage Materials": [
        "hydrogen storage", "metal hydride", "solid-state hydrogen", "mgh2", "magnesium hydride",
        "libh4", "nabh4", "libh4", "complex hydride", "borohydride", "alanate", "amide",
        "lani5", "tife", "ab2", "ab5", "bcc alloy", "high entropy alloy hydrogen",
        "palladium hydride", "titanium hydride", "zirconium hydride", "vanadium hydride",
        "intermetallic hydride", "gravimetric capacity", "volumetric capacity", "wt% hydrogen",
        "hydrogen desorption", "hydrogen absorption", "destabilization", "catalytic additive",
        "nanoconfinement", "reversible hydrogen", "hydrogen capacity",
    ],

    # -- Hydrogen storage — simulations ----------------------------------------
    "H2 Storage Simulations": [
        "grand canonical monte carlo", "gcmc", "widom insertion", "hydrogen adsorption simulation",
        "calphad", "van't hoff", "thermodynamic model hydrogen", "enthalpy of formation hydride",
        "reaction enthalpy", "phase diagram hydrogen", "reaxff hydrogen", "reactive molecular dynamics",
        "nudged elastic band", "activation barrier hydrogen", "diffusion hydrogen",
        "dft hydrogen", "first principles hydrogen", "high-throughput screening hydride",
        "computational screening hydrogen", "machine learning hydrogen", "ml hydrogen storage",
    ],

    # -- Hydrogen storage — experiments ----------------------------------------
    "H2 Storage Experiments": [
        "pressure-composition isotherm", "pct curve", "sievert", "temperature programmed desorption",
        "tpd hydrogen", "activation procedure", "hydrogenation kinetics", "dehydrogenation kinetics",
        "cycling stability", "hydrogen cycling", "ball milling hydrogen", "melt spinning",
        "xrd hydrogen", "neutron diffraction hydrogen", "synchrotron hydrogen",
        "tem hydrogen", "in situ hydrogen", "calorimetry hydrogen", "dsc hydrogen",
        "hydrogen purity", "tank system", "on-board storage",
    ],

    # -- Porous materials for H2 -----------------------------------------------
    "Porous H2 Adsorbents": [
        "metal-organic framework hydrogen", "mof hydrogen", "hydrogen uptake mof",
        "physisorption hydrogen", "cryogenic hydrogen", "liquid hydrogen",
        "carbon adsorbent hydrogen", "activated carbon hydrogen", "zeolite hydrogen",
        "porous carbon hydrogen", "hydrogen adsorption isotherm", "langmuir hydrogen",
        "bet surface area hydrogen", "microporous hydrogen", "high pressure hydrogen",
        "70 mpa", "700 bar", "cryo-adsorption",
    ],

    # -- Personal & admin ------------------------------------------------------
    "Personal":               ["booking confirmation", "statement of registration", "tourist visa", "schengen", "seattle plan", "research proposal confirmation", "late stage review", "registration", "itinerary", "visa requirement", "travel document", "phd registration"],
}

# Domain-specific short acronyms to include in keyword matching (3-letter terms
# missed by the 4+ char filter).
_DOMAIN_SHORT_TERMS = {
    "dft", "cvd", "kmc", "gnn", "mlp", "ace", "gap", "oer", "orr", "her",
    "bcc", "fcc", "hcp", "dos", "bz", "md", "mc", "neb", "rdf", "xrd",
    "eam", "vdw", "qm", "mm",
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
        try:
            from mistralai import Mistral
        except ImportError:
            from mistralai.client.sdk import Mistral
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


STRUCTURE_PROMPT_MD = """\
You are a research knowledge base builder for a materials science / ML potentials researcher.
Given markdown content (a web article, blog post, repo README, or personal note), produce a dense,
accurate Obsidian wiki page.

Rules:
- Extract only facts present in the text. Do not hallucinate or invent details.
- NEVER write placeholder text like "[See full text...]" — if a section has no content, write N/A.
- Be specific: include numbers, tool names, library names, URLs exactly as stated.
- Tags must be chosen from these domains (lowercase-hyphenated):
  #ml-potentials | #method-acceleration | #generative-models | #drug-discovery
  #crystals-and-alloys | #molecules | #2d-materials | #proteins | #quantum-theory
  #group-theory | #applied-mathematics | #gaussian-processes | #ml-theory
  #phonons-and-anharmonicity | #electrochemistry | #quantum-photonics
  #hydrogen-storage-materials | #h2-storage-simulations | #h2-storage-experiments
  #porous-h2-adsorbents | #personal

Output EXACTLY this format — no preamble, no text outside this structure:

---
title: [Full title as it appears, or infer from content]
author: [Author or organization, or "unknown"]
date: [Date YYYY-MM-DD or "unknown"]
url: [Source URL if present, else ""]
source: [Website, platform, or repo name — e.g. "Towards Data Science", "GitHub", "arXiv blog"]
type: article
tags: [#tag1 #tag2 — from domain list above only]
---

# [Title]

## Summary
[2–3 sentences: main topic, core argument or tool, and key takeaway. Be precise.]

## Key Points
- [Specific point with details/numbers where available]
- [Second point]
- [Add more as needed]

## Tools & Methods
- [Any software, framework, library, dataset, or method mentioned — N/A if none]

## Code & Implementation
[Relevant commands, configs, or code snippets exactly as written — N/A if none]

## Relevance
[1–2 sentences on relevance to ML potentials / materials simulation / research workflow]

## Citation
[Author] ([date]). [Title]. [Source/URL].
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


def structure_md_with_llm(body: str, filename: str, fm_data: dict) -> str:
    """Structure markdown content (web clip, note, README) into a wiki page."""
    hints = []
    for key, label in [("title", "Title"), ("url", "URL"), ("source", "URL"),
                       ("author", "Author"), ("date", "Date"), ("created", "Date")]:
        val = fm_data.get(key)
        if val and label not in [h.split(":")[0] for h in hints]:
            hints.append(f"{label}: {val}")

    hint_block = "\n".join(hints)
    user_msg = (
        f"Source filename: {filename}\n"
        + (f"Metadata hints:\n{hint_block}\n\n" if hint_block else "")
        + f"Content:\n{body[:25000]}"
    )

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
    return fn(STRUCTURE_PROMPT_MD, user_msg)


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
                wait = 60 * (attempt + 1) + random.uniform(0, 10)
                print(f"  Rate limited - waiting {wait:.0f}s before retry {attempt + 1}/3...")
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
        try:
            from mistralai import Mistral
        except ImportError:
            from mistralai.client.sdk import Mistral
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
                wait = 60 * (attempt + 1) + random.uniform(0, 10)
                print(f"  Rate limited — waiting {wait:.0f}s before retry {attempt + 1}/3...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Mistral rate limit exceeded after 3 retries.")


# -- Claims extraction (ported from Repo B) -----------------------------------

_CLAIMS_SYSTEM = """\
You are a scientific claim extractor. Extract ALL precise claims from the paper excerpt.
Output one claim per line in this exact format:
[CATEGORY] <one precise sentence with numbers/LaTeX preserved>

Categories (use exactly these labels):
RESULT    — quantitative results, benchmark numbers, performance metrics
TABLE     — data from tables (include all columns/values)
METHOD    — computational or experimental parameters, software, functionals
MECHANISM — reaction pathways, charge transfer, bonding mechanisms
COMPARISON — comparisons between materials, methods, or conditions

Rules:
- Preserve all numbers, units, LaTeX formulas exactly as written
- Do NOT paraphrase — use the paper's own language
- Extract at least 20 claims if the text is long enough
- Skip figure captions and reference lists
"""

_CATEGORY_CONFIDENCE = {
    "RESULT": 0.95, "TABLE": 0.90, "METHOD": 0.85,
    "MECHANISM": 0.80, "COMPARISON": 0.85,
}


def extract_claims(raw_text: str, title: str) -> list[dict]:
    """Extract structured claims from paper text via LLM. Returns list of {fact, confidence, category}."""
    user = f"**Paper:** {title}\n\n{raw_text[:12_000]}"
    try:
        raw = _llm_mistral(_CLAIMS_SYSTEM, user) if LLM_BACKEND == "mistral" else \
              _llm_anthropic(_CLAIMS_SYSTEM, user) if LLM_BACKEND == "anthropic" else \
              _llm_gemini(_CLAIMS_SYSTEM, user)
    except Exception as e:
        print(f"  [claim extraction failed: {e}]")
        return []

    claims = []
    for line in raw.splitlines():
        line = line.strip()
        for cat, conf in _CATEGORY_CONFIDENCE.items():
            if line.startswith(f"[{cat}]"):
                fact = line[len(f"[{cat}]"):].strip()
                if len(fact) > 10:
                    claims.append({"fact": fact, "confidence": conf, "category": cat})
                break
    return claims


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


def write_wiki_page(structured: str, pdf_path: Path, claims: list | None = None) -> Path:
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

    # Inject claims into frontmatter if provided
    if claims:
        fm_end = structured.find("\n---\n", 4)
        if fm_end > 0:
            try:
                fm_data = yaml.safe_load(structured[4:fm_end]) or {}
                fm_data["claims"] = claims
                new_fm = yaml.dump(fm_data, sort_keys=False, allow_unicode=True)
                rest = structured[fm_end + 5:]
                structured = f"---\n{new_fm}---\n{rest}"
            except Exception:
                pass  # Frontmatter parse failed — skip claims injection

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


# -- Semantic vector index (ported from Repo B) --------------------------------

_MISTRAL_EMBED_URL = "https://api.mistral.ai/v1/embeddings"
_EMBED_MODEL = "mistral-embed"
_SEM_VECTORS_PATH = WIKI_DIR / ".vectors-semantic.json"


def _embed(text: str) -> list[float]:
    """Call Mistral Embed API. Returns [] if unavailable."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        return []
    import requests
    try:
        resp = requests.post(
            _MISTRAL_EMBED_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": _EMBED_MODEL, "input": text[:4096]},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except Exception as e:
        print(f"  [embed failed: {e}]")
        return []


def _content_hash(text: str) -> str:
    return hashlib.sha1(text[:4000].encode("utf-8", errors="ignore")).hexdigest()


def index_vectors_semantic() -> None:
    """Build/update semantic embedding index (wiki/.vectors-semantic.json).

    Uses SHA1 of content (not mtime) to skip unchanged pages.
    Requires MISTRAL_API_KEY and numpy (pip install numpy).
    """
    try:
        import numpy as np  # noqa: F401 — just a check
    except ImportError:
        print("  FAIL numpy not installed. Run: pip install numpy", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("  FAIL MISTRAL_API_KEY not set — required for embeddings.", file=sys.stderr)
        sys.exit(1)

    print("Building semantic vector index (Mistral embeddings)...")
    data: dict = {}
    if _SEM_VECTORS_PATH.exists():
        try:
            data = json.loads(_SEM_VECTORS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    _fm_re = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
    updated = skipped = 0

    for f in sorted(WIKI_DIR.glob("**/*.md")):
        if f.name in ("index.md",) or ".vectors" in f.name:
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        body = _fm_re.sub("", content, count=1).strip()
        chash = _content_hash(body)

        if f.name in data and data[f.name].get("hash") == chash:
            skipped += 1
            continue

        vec = _embed(body)
        if not vec:
            print(f"  skip {f.name} (embed failed)")
            continue

        data[f.name] = {"vector": vec, "hash": chash, "title": f.stem}
        updated += 1
        print(f"  indexed {f.name}")
        time.sleep(0.3)  # Gentle rate-limit padding

    _SEM_VECTORS_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"  Semantic index updated: {updated} new, {skipped} unchanged.")


def query_semantic(search: str, top_k: int = 10) -> None:
    """Cosine-similarity search against the semantic embedding index."""
    try:
        import numpy as np
    except ImportError:
        print("  FAIL numpy not installed. Run: pip install numpy", file=sys.stderr)
        sys.exit(1)

    if not _SEM_VECTORS_PATH.exists():
        print("No semantic index found. Run 'index-vectors' first.")
        return

    data = json.loads(_SEM_VECTORS_PATH.read_text(encoding="utf-8"))
    q_vec = _embed(search)
    if not q_vec:
        print("  Embedding failed — falling back to keyword search.")
        query_kb(search)
        return

    q = np.array(q_vec)
    results = []
    for fname, info in data.items():
        d = np.array(info["vector"])
        norm = np.linalg.norm(q) * np.linalg.norm(d)
        sim = float(np.dot(q, d) / norm) if norm > 0 else 0.0
        results.append((sim, info["title"], fname))

    results.sort(reverse=True)
    print(f"\nSemantic results for: '{search}'\n" + "-" * 56)
    for sim, title, fname in results[:top_k]:
        stem = Path(fname).stem
        print(f"  [{sim:.3f}]  {title}")
        print(f"         wiki/{stem}.md\n")

    _log_operation("query-semantic", f"'{search[:80]}' → {min(top_k, len(results))} results")


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


# -- Query (keyword) ----------------------------------------------------------

def query_kb(search: str) -> None:
    if not VECTORS_PATH.exists():
        print("No index found. Run 'all' first to ingest papers.")
        return

    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    terms = search.lower().split()
    results = []

    for slug, meta in vectors.items():
        haystack = f"{meta['title']} {meta['tags']} {meta['keywords']} {meta['authors']}".lower()
        # Use word-boundary matching to avoid "ml" matching "html"
        score = sum(1 for t in terms if re.search(r"\b" + re.escape(t) + r"\b", haystack))
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

def ingest_pdf(pdf_path: Path, with_claims: bool = False) -> None:
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

    claims = None
    if with_claims or EXTRACT_CLAIMS:
        title_m = re.search(r"^title:\s*(.+)$", structured, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else pdf_path.stem
        print(f"  Extracting claims [{LLM_BACKEND}]...")
        claims = extract_claims(raw_text, title)
        print(f"  {len(claims)} claims extracted.")

    page_path = write_wiki_page(structured, pdf_path, claims=claims)
    update_vectors(page_path, structured)
    _log_operation("ingest", f"{pdf_path.name} → wiki/{page_path.name}")
    print(f"  OK  wiki/{page_path.name}")


def ingest_md(md_path: Path) -> None:
    """Ingest a markdown file (web clip, note, README) into the wiki."""
    md_path = md_path.resolve()
    if not md_path.exists():
        print(f"FAIL File not found: {md_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n>> {md_path.name}")
    LOG_DIR.mkdir(exist_ok=True)

    content = md_path.read_text(encoding="utf-8", errors="ignore")

    # Strip and preserve any YAML frontmatter (Obsidian Web Clipper, etc.)
    fm_data: dict = {}
    body = content
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if fm_match:
        try:
            fm_data = yaml.safe_load(fm_match.group(1)) or {}
        except Exception:
            pass
        body = content[fm_match.end():]

    log_path = LOG_DIR / (md_path.stem + ".txt")
    if log_path.exists():
        print("  Using cached text from log/")
        body = log_path.read_text(encoding="utf-8")
    else:
        log_path.write_text(body, encoding="utf-8")
        print(f"  Cached to log/{log_path.name}")

    structured = structure_md_with_llm(body, md_path.name, fm_data)
    page_path = write_wiki_page(structured, md_path)
    update_vectors(page_path, structured)
    _log_operation("ingest-md", f"{md_path.name} → wiki/{page_path.name}")
    print(f"  OK  wiki/{page_path.name}")


def ingest_all() -> None:
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    mds  = sorted(RAW_DIR.glob("*.md"))

    if not pdfs and not mds:
        print(f"No PDFs or markdown files found in {RAW_DIR}/")
        print("Drop paper PDFs or web-clipped .md files into raw/ and run again.")
        return

    existing_slugs = {p.stem for p in WIKI_DIR.glob("*.md")} if WIKI_DIR.exists() else set()
    new_pdfs = [p for p in pdfs if _slug(p.stem) not in existing_slugs]
    new_mds  = [m for m in mds  if _slug(m.stem) not in existing_slugs]
    total_new = len(new_pdfs) + len(new_mds)
    already   = len(pdfs) + len(mds) - total_new

    if not total_new:
        print(f"All {len(pdfs)} PDF(s) and {len(mds)} MD(s) already ingested.")
        return

    print(f"Found {len(new_pdfs)} new PDF(s) and {len(new_mds)} new MD(s) "
          f"(skipping {already} already done)...")
    failed = 0
    for pdf in new_pdfs:
        try:
            ingest_pdf(pdf, with_claims=EXTRACT_CLAIMS)
        except Exception as e:
            print(f"  FAIL  {pdf.name} - {e}", file=sys.stderr)
            failed += 1
    for md in new_mds:
        try:
            ingest_md(md)
        except Exception as e:
            print(f"  FAIL  {md.name} - {e}", file=sys.stderr)
            failed += 1

    rebuild_index()
    total = len(list(WIKI_DIR.glob("*.md"))) - 1
    print(f"\nDone. {total_new - failed} ingested, {failed} failed. Wiki: {total} pages total.")


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

    print(f"\n  {len(hub_slugs)} category hubs created: wiki/hub-*.md")
    print(f"  Categories section added to {updated} paper pages.")


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
    long_tokens = set(re.findall(r"[a-z]{4,}", raw))
    short_tokens = {w for w in raw.split() if w in _DOMAIN_SHORT_TERMS}
    tokens = long_tokens | short_tokens
    return tokens - {
        "with", "from", "that", "this", "they", "have", "been",
        "into", "their", "using", "based", "which", "more", "also",
        "than", "show", "such", "high", "both", "between",
    }


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
        text = re.sub(r"\n\n## See Also\n.*", "", text, flags=re.DOTALL)
        footer_m = re.search(r"\n\n---\n\*Ingested:.*", text, re.DOTALL)
        footer = footer_m.group(0) if footer_m else ""
        body = text[:footer_m.start()] if footer_m else text

        page_path.write_text(body + see_also + footer, encoding="utf-8")
        updated += 1

    print(f"  See Also links added/updated on {updated} pages.")


# -- Lint (ported from Repo B) ------------------------------------------------

def lint() -> None:
    """Find broken wikilinks and orphan pages in wiki/."""
    pages = [f for f in WIKI_DIR.glob("*.md") if f.name != "index.md"]
    all_stems = {p.stem for p in pages}
    incoming: dict = defaultdict(set)
    broken: list = []

    for page in pages:
        content = page.read_text(encoding="utf-8", errors="ignore")
        links = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", content)
        for link in links:
            if link in all_stems:
                incoming[link].add(page.stem)
            else:
                broken.append((page.stem, link))

    orphans = [p.stem for p in pages if p.stem not in incoming]

    print(f"\n=== Wiki Lint Report ===")
    print(f"Total pages : {len(pages)}")
    print(f"Broken links: {len(broken)}")
    for page, link in broken[:30]:
        print(f"  [[{link}]]  ←  in {page}")
    if len(broken) > 30:
        print(f"  ... and {len(broken) - 30} more")
    print(f"\nOrphan pages (no incoming links): {len(orphans)}")
    for o in orphans[:30]:
        print(f"  {o}")
    if len(orphans) > 30:
        print(f"  ... and {len(orphans) - 30} more")

    _log_operation("lint", f"{len(broken)} broken links, {len(orphans)} orphans")


# -- Fix broken wikilinks -----------------------------------------------------

def fix_broken_links() -> None:
    """Repair broken [[wikilinks]] across all wiki pages using fuzzy slug matching."""
    from difflib import SequenceMatcher

    pages = [f for f in WIKI_DIR.glob("*.md")]
    all_stems = {p.stem for p in pages}

    def _best_match(lnk: str) -> str | None:
        if lnk in all_stems:
            return lnk
        # Try truncating to 60 chars (matches _slug() limit)
        truncated = lnk[:60]
        if truncated in all_stems:
            return truncated
        # Find stem that starts with the same prefix (first 40 chars)
        prefix = lnk[:40]
        candidates = [s for s in all_stems if s.startswith(prefix)]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            # Pick closest by edit distance
            best = max(candidates, key=lambda s: SequenceMatcher(None, lnk, s).ratio())
            if SequenceMatcher(None, lnk, best).ratio() >= 0.80:
                return best
        # Broad fuzzy fallback
        best = max(all_stems, key=lambda s: SequenceMatcher(None, lnk, s).ratio())
        ratio = SequenceMatcher(None, lnk, best).ratio()
        if ratio >= 0.85:
            return best
        return None

    fixed_pages = 0
    fixed_links = 0
    removed_links = 0

    for page in pages:
        content = page.read_text(encoding="utf-8", errors="ignore")
        original = content

        # Find all wikilinks and fix broken ones
        def _replace(m: re.Match) -> str:
            nonlocal fixed_links, removed_links
            lnk = m.group(1)
            display = m.group(2)  # may be None
            if lnk in all_stems:
                return m.group(0)  # already valid
            best = _best_match(lnk)
            if best:
                fixed_links += 1
                return f"[[{best}|{display}]]" if display else f"[[{best}]]"
            # No match — keep display text if available, else drop brackets
            removed_links += 1
            return display if display else lnk

        content = re.sub(
            r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]",
            _replace,
            content,
        )

        # Remove list lines whose wikilink was unrepairable and left bare text
        # (lines that were "- some-bare-slug" with no display text)
        content = re.sub(r"^- [a-z][a-z0-9-]{20,}\n", "", content, flags=re.MULTILINE)

        if content != original:
            page.write_text(content, encoding="utf-8")
            fixed_pages += 1

    print(f"  Fixed: {fixed_links} links repaired, {removed_links} removed, across {fixed_pages} pages.")
    _log_operation("fix-links", f"{fixed_links} repaired, {removed_links} removed, {fixed_pages} pages")


# -- Export (ported from Repo B) ----------------------------------------------

_EXPORT_SYSTEMS = {
    "marp": (
        "Format as a complete Marp slide deck. Include YAML front matter "
        "(marp: true, theme: gaia, size: 16:9, paginate: true). "
        "Slides separated by ---. One key finding per slide with 4-6 bullet points. "
        "Preserve all LaTeX. End with a Summary and Open Questions slide."
    ),
    "latex": (
        "Format as LaTeX section content. Use \\section, \\subsection, itemize, "
        "and equation environments. Preserve all math in $ or $$ delimiters. "
        "Academic tone. Include a tabular environment for quantitative comparisons."
    ),
    "csv": (
        "Format as CSV with header: Claim,Confidence,Category,Source\n"
        "Extract all quantitative claims. One row per claim. "
        "Escape commas with quotes. No extra text — CSV only."
    ),
    "report": (
        "Format as an academic report section with full paragraphs. "
        "Include: Overview, Current State of the Art, Quantitative Comparison, "
        "Contradictions & Gaps, Strategic Outlook. Preserve all LaTeX."
    ),
}


def export_kb(topic: str, fmt: str = "marp") -> None:
    """Generate a deliverable (marp/latex/csv/report) from wiki knowledge on a topic."""
    print(f"Exporting '{topic}' as {fmt}...")

    pages_content = ""
    count = 0
    _fm_re = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

    for f in WIKI_DIR.glob("*.md"):
        if count >= 8:
            break
        content = f.read_text(encoding="utf-8", errors="ignore")
        if not any(w.lower() in content.lower() for w in topic.split()):
            continue

        fm_match = _fm_re.match(content)
        body = content[fm_match.end():].strip() if fm_match else content

        # Prefer structured claims from frontmatter if present
        claims: list = []
        if fm_match:
            try:
                fm_data = yaml.safe_load(fm_match.group(0).strip("---\n")) or {}
                claims = fm_data.get("claims", [])
            except Exception:
                pass

        snippet = "\n".join(f"- {c['fact']}" for c in claims[:20]) if claims else body[:2000]
        pages_content += f"\n\n### [[{f.stem}]]\n{snippet}"
        count += 1

    if not pages_content:
        print("No relevant wiki pages found for this topic.")
        return

    system = _EXPORT_SYSTEMS.get(fmt, _EXPORT_SYSTEMS["report"])
    llm_fn = {
        "gemini": _llm_gemini, "groq": _llm_groq,
        "anthropic": _llm_anthropic, "ollama": _llm_ollama, "mistral": _llm_mistral,
    }.get(LLM_BACKEND, _llm_mistral)

    result = llm_fn(system, f"Topic: {topic}\n\nWiki Knowledge:\n{pages_content}")

    exports_dir = PROJECT_ROOT / "exports"
    exports_dir.mkdir(exist_ok=True)
    ext = {"marp": "md", "latex": "tex", "csv": "csv", "report": "md"}.get(fmt, "md")
    out_path = exports_dir / f"{_slug(topic)}.{ext}"
    out_path.write_text(result, encoding="utf-8")
    _log_operation("export", f"'{topic}' as {fmt} → {out_path.name}")
    print(f"  → {out_path}")


# -- Crystallize (ported from Repo B) -----------------------------------------

_CRYSTALLIZE_SYSTEM = """\
You are a research crystallizer. Read this research mission file and distill
the most important permanent insights for a knowledge base.

Output a structured Markdown wiki page with:
- YAML frontmatter: title, type: insight, date, tags (list), confidence (0.0–1.0)
- ## Summary (3–5 sentences capturing the core finding)
- ## Key Findings (bullet list, preserve all LaTeX)
- ## Mechanisms (how/why it works)
- ## Open Questions (speculative insights reframed as testable questions)
- ## Related Pages (list of [[wikilinks]] to relevant wiki pages)

Be precise and permanent — this page will be read by future research sessions.
"""


def crystallize(mission_file: str | None = None) -> None:
    """Distill a mission/research file into a permanent wiki/concepts/ insight page."""
    if mission_file:
        path = Path(mission_file)
    else:
        # Auto-find most recent research_ file in output/
        candidates = sorted(
            (PROJECT_ROOT / "output").glob("**/research_*.md"), reverse=True
        )
        if not candidates:
            print("No mission files found. Pass a path or run the pipeline first.")
            return
        path = candidates[0]

    if not path.exists():
        print(f"FAIL file not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Crystallizing: {path.name} ...")
    content = path.read_text(encoding="utf-8", errors="ignore")

    llm_fn = {
        "gemini": _llm_gemini, "groq": _llm_groq,
        "anthropic": _llm_anthropic, "ollama": _llm_ollama, "mistral": _llm_mistral,
    }.get(LLM_BACKEND, _llm_mistral)

    result = llm_fn(_CRYSTALLIZE_SYSTEM, content[:15_000])

    title_m = re.search(r"title:\s*[\"']?(.+?)[\"']?\s*\n", result)
    title = title_m.group(1).strip() if title_m else path.stem
    slug = _slug(title)

    concepts_dir = WIKI_DIR / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    out_path = concepts_dir / f"{slug}.md"
    out_path.write_text(result, encoding="utf-8")
    _log_operation("crystallize", f"{path.name} → concepts/{slug}.md")
    print(f"  → wiki/concepts/{slug}.md")


# -- Ask (Q&A synthesis) ------------------------------------------------------

_ASK_SYSTEM = """\
You are a research assistant for a materials science / ML potentials researcher.
Answer the question below using ONLY the knowledge provided from the wiki KB pages.

Rules:
- Cite sources using [[wikilink]] notation inline as you write.
- Be specific: preserve numbers, model names, benchmark results exactly as stated in the pages.
- Do NOT invent or speculate beyond what the pages contain.
- If the KB lacks enough information to fully answer, say so explicitly in ## Gaps.

Output exactly this structure:

## Answer
[Direct answer in 3–6 sentences with inline [[citations]]]

## Evidence
- [[slug|Title]]: [key supporting fact with numbers/metrics]
- (one bullet per supporting page)

## Gaps
[What the KB doesn't cover — or "None" if fully answered]
"""


def _find_relevant(question: str, top_k: int = 8) -> list[tuple[str, float, str]]:
    """Return [(slug, score, title)] for the most relevant KB pages.

    Prefers semantic similarity when the index and API key are available;
    falls back to keyword scoring from .vectors.json.
    """
    # Semantic path
    if _SEM_VECTORS_PATH.exists() and os.environ.get("MISTRAL_API_KEY"):
        q_vec = _embed(question)
        if q_vec:
            try:
                import numpy as np
                data = json.loads(_SEM_VECTORS_PATH.read_text(encoding="utf-8"))
                q = np.array(q_vec)
                results = []
                for fname, info in data.items():
                    d = np.array(info["vector"])
                    norm = np.linalg.norm(q) * np.linalg.norm(d)
                    sim = float(np.dot(q, d) / norm) if norm > 0 else 0.0
                    slug = Path(fname).stem
                    results.append((slug, sim, info.get("title", slug)))
                results.sort(key=lambda x: x[1], reverse=True)
                return results[:top_k]
            except Exception:
                pass  # fall through to keyword

    # Keyword fallback
    if not VECTORS_PATH.exists():
        return []
    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    terms = question.lower().split()
    results = []
    for slug, meta in vectors.items():
        haystack = f"{meta['title']} {meta['tags']} {meta['keywords']} {meta['authors']}".lower()
        score = sum(1 for t in terms if re.search(r"\b" + re.escape(t) + r"\b", haystack))
        if score > 0:
            results.append((slug, float(score), meta.get("title", slug)))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def ask_kb(question: str, top_k: int = 8, save: bool = False) -> None:
    """Synthesize an answer to a research question from relevant KB pages."""
    relevant = _find_relevant(question, top_k=top_k)
    if not relevant:
        print("No relevant pages found. Run 'all' to ingest papers, or try 'query' to check coverage.")
        return

    _fm_re = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
    pages_content = ""
    loaded: list[tuple[str, str]] = []  # (slug, title)

    for slug, score, title in relevant:
        page_path = WIKI_DIR / f"{slug}.md"
        if not page_path.exists():
            continue
        content = page_path.read_text(encoding="utf-8", errors="ignore")
        fm_match = _fm_re.match(content)
        body = content[fm_match.end():].strip() if fm_match else content
        pages_content += f"\n\n---\n### [[{slug}|{title}]]\n{body[:3000]}"
        loaded.append((slug, title))

    if not loaded:
        print("Pages found in index but not on disk — run 'index' to rebuild.")
        return

    names = ", ".join(t for _, t in loaded[:4])
    suffix = f" + {len(loaded) - 4} more" if len(loaded) > 4 else ""
    print(f"  Drawing from {len(loaded)} pages: {names}{suffix}")

    llm_fn = {
        "gemini": _llm_gemini, "groq": _llm_groq,
        "anthropic": _llm_anthropic, "ollama": _llm_ollama, "mistral": _llm_mistral,
    }.get(LLM_BACKEND, _llm_gemini)

    print(f"  Synthesizing [{LLM_BACKEND}]...")
    answer = llm_fn(_ASK_SYSTEM, f"Question: {question}\n\nWiki Knowledge:\n{pages_content}")

    print(f"\n{'=' * 60}")
    print(answer)
    print(f"{'=' * 60}\n")

    if save:
        concepts_dir = WIKI_DIR / "concepts"
        concepts_dir.mkdir(parents=True, exist_ok=True)
        out_path = concepts_dir / f"qa-{_slug(question[:60])}.md"
        source_list = ", ".join(s for s, _ in loaded)
        header = (
            f"---\ntitle: \"Q&A — {question[:80]}\"\ntype: qa\n"
            f"date: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"sources: [{source_list}]\n---\n\n"
            f"# Q: {question}\n\n"
        )
        out_path.write_text(header + answer, encoding="utf-8")
        _log_operation("ask", f"'{question[:80]}' → concepts/{out_path.name}")
        print(f"  Saved → wiki/concepts/{out_path.name}")
    else:
        _log_operation("ask", f"'{question[:80]}' ({len(loaded)} pages)")


# -- Health check -------------------------------------------------------------

_HEALTH_CHECK_SYSTEM = """\
You are a research knowledge base auditor for a materials science / ML potentials researcher.
You receive a compact fingerprint of every page in the KB: slug, title, year, venue, tags, and key findings.

Produce a health report with exactly these five sections. Use [[slug]] citations throughout. Be specific.

## Inconsistencies
Contradictions or suspicious discrepancies across pages (e.g. the same model reported with different
benchmark scores on the same dataset, conflicting mechanistic claims).
If none detected, write "None detected."

## Missing Link Candidates
Pairs of pages with strong conceptual overlap that have no See Also connection.
Format each as: [[slug-a]] ↔ [[slug-b]] — one-line reason
Limit to 5 pairs.

## Data Gaps
Pages with weak or missing content: mostly N/A sections, unknown year/venue, very thin findings,
or an important topic not covered by any page.
Format each as: [[slug]] — what is missing  (or "Topic gap: ..." for uncovered topics)
Limit to 8 entries.

## Suggested Concept Pages
Cross-cutting themes spanning 3+ papers that deserve their own synthesis page.
Format each as: "Proposed title" — [[slug-a]], [[slug-b]], [[slug-c]]
Limit to 5 suggestions.

## Research Questions
Specific questions the KB raises but cannot fully answer from its current content.
Each question must be grounded in actual page content, not generic.
List exactly 5 questions.
"""


def _extract_key_findings(page_path: Path) -> str:
    """Pull the first 300 chars of ## Key Findings as a single joined line."""
    try:
        content = page_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"## Key Findings\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
        if m:
            lines = [ln.strip().lstrip("- ").strip()
                     for ln in m.group(1).strip().splitlines() if ln.strip()]
            return " / ".join(lines)[:300]
    except Exception:
        pass
    return ""


def _page_fingerprint(slug: str, meta: dict) -> str:
    """Compact one-entry summary of a wiki page for the health-check LLM prompt."""
    page_path = WIKI_DIR / f"{slug}.md"
    findings = _extract_key_findings(page_path) if page_path.exists() else ""
    title  = meta.get("title",  slug)
    year   = meta.get("year",   "?")
    venue  = meta.get("venue",  "")
    tags   = meta.get("tags",   "")
    venue_part = f", {venue}" if venue else ""
    return (
        f"[[{slug}|{title}]] ({year}{venue_part}) {tags}\n"
        f"  {findings or '(no key findings)'}"
    )


def _save_health_report(content: str) -> None:
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = WIKI_DIR / f".health-check-{date_str}.md"
    WIKI_DIR.mkdir(exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"\n  Report saved → wiki/.health-check-{date_str}.md")


def health_check(topic: str | None = None, structural_only: bool = False) -> None:
    """KB health check: structural lint + LLM content audit.

    topic: scope the LLM phase to pages matching this keyword/topic.
    structural_only: skip the LLM call, only run phase 1.
    """
    print("\n=== KB Health Check ===\n")
    report_parts: list[str] = [
        f"# KB Health Check\n\n*{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
    ]

    # --- Phase 1: Structural (no LLM) ---
    pages = [f for f in sorted(WIKI_DIR.glob("*.md"))
             if f.name != "index.md" and not f.stem.startswith("hub-")]
    all_stems = {p.stem for p in pages}
    incoming: dict = defaultdict(set)
    broken: list[tuple[str, str]] = []
    thin: list[tuple[str, int]] = []

    for page in pages:
        content = page.read_text(encoding="utf-8", errors="ignore")
        for link in re.findall(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", content):
            if link in all_stems:
                incoming[link].add(page.stem)
            else:
                broken.append((page.stem, link))
        na_count = len(re.findall(r"\bN/A\b", content, re.IGNORECASE))
        if na_count >= 3:
            thin.append((page.stem, na_count))

    orphans = [p.stem for p in pages
               if p.stem not in incoming and not p.stem.startswith("hub-")]

    struct = ["## Structural\n\n"]
    struct.append(f"- Total pages: {len(pages)}\n")
    struct.append(f"- Broken wikilinks: {len(broken)}\n")
    struct.append(f"- Orphan pages (no incoming links): {len(orphans)}\n")
    struct.append(f"- Thin pages (3+ N/A sections): {len(thin)}\n")
    if broken:
        struct.append("\n**Broken links:**\n")
        for src, lnk in broken[:20]:
            struct.append(f"  - `[[{lnk}]]` ← `{src}`\n")
        if len(broken) > 20:
            struct.append(f"  - ... and {len(broken) - 20} more\n")
    if orphans:
        struct.append("\n**Orphan pages:**\n")
        for o in orphans[:20]:
            struct.append(f"  - [[{o}]]\n")
        if len(orphans) > 20:
            struct.append(f"  - ... and {len(orphans) - 20} more\n")

    struct_block = "".join(struct)
    print(struct_block)
    report_parts.append(struct_block)

    if structural_only:
        _save_health_report("".join(report_parts))
        _log_operation("health-check", f"structural only — {len(broken)} broken, {len(orphans)} orphans")
        return

    # --- Phase 2: LLM content audit ---
    if not VECTORS_PATH.exists():
        print("No vectors index — run 'all' first, then retry.")
        _save_health_report("".join(report_parts))
        return

    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

    if topic:
        relevant = _find_relevant(topic, top_k=30)
        scoped = {s for s, _, _ in relevant}
        vectors = {k: v for k, v in vectors.items() if k in scoped}
        print(f"  Scoped to {len(vectors)} pages matching: '{topic}'")

    fingerprints = [_page_fingerprint(slug, meta) for slug, meta in sorted(vectors.items())]
    kb_size = len(fingerprints)
    if not fingerprints:
        print("No pages to analyze.")
        _save_health_report("".join(report_parts))
        return

    scope_label = f"topic='{topic}'" if topic else "full KB"
    print(f"  Analyzing {kb_size} pages ({scope_label}) [{LLM_BACKEND}]...")

    fingerprint_block = "\n\n".join(fingerprints)
    llm_fn = {
        "gemini": _llm_gemini, "groq": _llm_groq,
        "anthropic": _llm_anthropic, "ollama": _llm_ollama, "mistral": _llm_mistral,
    }.get(LLM_BACKEND, _llm_gemini)

    llm_report = llm_fn(
        _HEALTH_CHECK_SYSTEM,
        f"KB Fingerprint ({kb_size} pages, {scope_label}):\n\n{fingerprint_block}",
    )

    print(f"\n{'=' * 60}")
    print(llm_report)
    print(f"{'=' * 60}")

    report_parts.append("\n" + llm_report + "\n")
    _save_health_report("".join(report_parts))
    _log_operation("health-check", f"{kb_size} pages, {len(broken)} broken, {len(orphans)} orphans")


# -- Cross-synthesize ---------------------------------------------------------

_CROSS_SYNTHESIZE_SYSTEM = """\
You are a research knowledge base enricher for a materials science / ML potentials researcher.
Given one paper's wiki page and a digest of all other papers in the KB, write a concise
## Cross-KB Insights section that surfaces specific connections to other papers.

Rules:
- Cite other papers using [[slug|Title]] notation.
- Be specific: comparisons, contradictions, complementary methods, shared benchmarks.
- Do NOT repeat findings already stated in the paper's own sections.
- 4–8 bullet points maximum. Each bullet names a specific other paper.

Output ONLY the section — no preamble:

## Cross-KB Insights
- [[slug|Title]]: one sentence on connection, comparison, or contrast
"""


def _build_kb_digest(pages: list[Path]) -> list[str]:
    """Return one digest line per page: [[slug|Title]]: key findings (≤150 chars)."""
    lines = []
    for page in pages:
        content = page.read_text(encoding="utf-8", errors="ignore")
        title_m = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else page.stem
        findings = _extract_key_findings(page)[:150]
        lines.append(f"[[{page.stem}|{title}]]: {findings or '(no key findings)'}")
    return lines


def cross_synthesize() -> None:
    """Add ## Cross-KB Insights to every wiki page using a KB-wide digest."""
    pages = [f for f in sorted(WIKI_DIR.glob("*.md"))
             if f.name != "index.md"
             and not f.stem.startswith("hub-")
             and f.parent == WIKI_DIR]

    if not pages:
        print("No wiki pages found. Run 'all' or 'reingest' first.")
        return

    print(f"Building KB digest from {len(pages)} pages...")
    digest_lines = _build_kb_digest(pages)

    llm_fn = {
        "gemini": _llm_gemini, "groq": _llm_groq,
        "anthropic": _llm_anthropic, "ollama": _llm_ollama, "mistral": _llm_mistral,
    }.get(LLM_BACKEND, _llm_gemini)

    _fm_re = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
    already_done = sum(1 for p in pages if "## Cross-KB Insights" in p.read_text(encoding="utf-8", errors="ignore"))
    print(f"Cross-synthesizing [{LLM_BACKEND}] — {already_done} already done, {len(pages) - already_done} remaining...")
    updated = failed = skipped = 0

    for page in pages:
        content = page.read_text(encoding="utf-8", errors="ignore")
        title_m = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else page.stem

        # Exclude this page from the digest shown to the LLM
        other_digest = "\n".join(
            line for line in digest_lines
            if not line.startswith(f"[[{page.stem}|")
        )

        # Skip pages already enriched — safe to resume after interruption
        if "## Cross-KB Insights" in content:
            skipped += 1
            continue

        fm_match = _fm_re.match(content)
        body = content[fm_match.end():].strip() if fm_match else content

        user_msg = (
            f"Current paper: [[{page.stem}|{title}]]\n\n"
            f"Paper content:\n{body[:4000]}\n\n"
            f"All other papers in KB:\n{other_digest}"
        )

        try:
            insights = llm_fn(_CROSS_SYNTHESIZE_SYSTEM, user_msg)

            # Strip any existing Cross-KB Insights section
            content = re.sub(
                r"\n\n## Cross-KB Insights\n.*?(?=\n\n##|\n\n---|\Z)",
                "", content, flags=re.DOTALL,
            )

            # Insert before the ingestion footer, or at end
            footer_m = re.search(r"\n\n---\n\*Ingested:", content)
            if footer_m:
                content = content[:footer_m.start()] + f"\n\n{insights}" + content[footer_m.start():]
            else:
                content = content + f"\n\n{insights}"

            page.write_text(content, encoding="utf-8")
            print(f"  enriched: {page.name}")
            updated += 1
        except Exception as e:
            print(f"  FAIL {page.name}: {e}", file=sys.stderr)
            failed += 1

    _log_operation("cross-synthesize", f"{updated} enriched, {skipped} skipped, {failed} failed")
    print(f"\nDone. {updated} enriched, {skipped} already done (skipped), {failed} failed.")


# -- Redo (full KB rebuild) ---------------------------------------------------

def redo() -> None:
    """Full KB rebuild: fresh reingest → cross-synthesize → link → make-hubs → index."""
    print("=== KB Redo ===\n")
    reingest_all(fresh=True)
    print("\n--- Cross-synthesis pass ---\n")
    cross_synthesize()
    print("\n--- Wiring See Also links ---\n")
    link_pages()
    print("\n--- Rebuilding category hubs ---\n")
    make_hubs()
    rebuild_index()
    print("\n=== Redo complete ===")


# -- Orphan cleanup -----------------------------------------------------------

def cleanup_orphans(force: bool = False) -> None:
    """Remove wiki pages whose source PDF no longer exists in raw/."""
    raw_pdfs = {p.name for p in RAW_DIR.glob("*.pdf")}

    to_delete: list[Path] = []
    skipped_no_source: list[str] = []

    skip_stems = {"index", "hub-index"}

    for page in sorted(WIKI_DIR.glob("*.md")):
        if page.stem in skip_stems or page.stem.startswith("hub-"):
            continue
        content = page.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"Source: `(.+?)`", content)
        if not m:
            skipped_no_source.append(page.name)
            continue
        source_pdf = m.group(1)
        if source_pdf not in raw_pdfs:
            to_delete.append(page)

    if not to_delete:
        print("Nothing to clean up — all wiki pages have a matching PDF in raw/.")
        if skipped_no_source:
            print(f"  Skipped {len(skipped_no_source)} pages with no Source footer (not touched).")
        return

    print(f"\nOrphaned wiki pages ({len(to_delete)}):")
    for p in to_delete:
        m = re.search(r"Source: `(.+?)`", p.read_text(encoding="utf-8", errors="ignore"))
        src = m.group(1) if m else "?"
        print(f"  {p.name}  ← {src}")

    if skipped_no_source:
        print(f"\nSkipping {len(skipped_no_source)} pages with no Source footer (kept as-is).")

    if not force:
        print()
        confirm = input(f"Delete {len(to_delete)} page(s)? [y/N] ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    deleted_stems = set()
    for page in to_delete:
        page.unlink()
        deleted_stems.add(page.stem)

    if VECTORS_PATH.exists():
        try:
            vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
            before = len(vectors)
            vectors = {k: v for k, v in vectors.items() if k not in deleted_stems}
            VECTORS_PATH.write_text(json.dumps(vectors, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  Removed {before - len(vectors)} entries from .vectors.json.")
        except Exception as e:
            print(f"  Warning: could not update .vectors.json — {e}", file=sys.stderr)

    rebuild_index()
    print(f"\nDone. {len(to_delete)} orphaned page(s) removed.")


# -- Audit log ----------------------------------------------------------------

def _log_operation(op_type: str, details: str) -> None:
    """Append a row to wiki/.audit-log.md."""
    log_path = WIKI_DIR / ".audit-log.md"
    WIKI_DIR.mkdir(exist_ok=True)
    if not log_path.exists():
        log_path.write_text(
            "# Audit Trail\n\n"
            "| Timestamp | Operation | Details |\n"
            "|-----------|-----------|---------|",
            encoding="utf-8",
        )
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    safe = details.replace("|", "∣").replace("\n", " ")[:150]
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n| {ts} | {op_type} | {safe} |")


# -- Helpers ------------------------------------------------------------------

def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"FAIL  {name} not set.", file=sys.stderr)
        print(f"      Set it with:  export {name}=\"your-key-here\"", file=sys.stderr)
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
            "  python scripts/wiki_manager.py ingest raw/mace-paper.pdf --claims\n"
            "  python scripts/wiki_manager.py query 'equivariant ML potentials'\n"
            "  python scripts/wiki_manager.py query 'MACE benchmark' --semantic\n"
            "  python scripts/wiki_manager.py index-vectors\n"
            "  python scripts/wiki_manager.py lint\n"
            "  python scripts/wiki_manager.py export 'OER catalysis' --format marp\n"
            "  python scripts/wiki_manager.py crystallize output/2026-05-12/research_*.md\n"
            "  python scripts/wiki_manager.py ask 'Which ML potentials work best for thermal conductivity?'\n"
            "  python scripts/wiki_manager.py ask 'Compare MACE vs NequIP accuracy' --top 10 --save\n"
            "  python scripts/wiki_manager.py health-check\n"
            "  python scripts/wiki_manager.py health-check --topic 'thermal conductivity'\n"
            "  python scripts/wiki_manager.py health-check --structural-only\n"
            "  python scripts/wiki_manager.py ingest-md raw/article.md\n"
            "  python scripts/wiki_manager.py redo\n"
            "  python scripts/wiki_manager.py cross-synthesize\n\n"
            "Backends (set env vars to override defaults):\n"
            "  PDF_BACKEND=gemini|pymupdf|mistral   (default: pymupdf)\n"
            "  LLM_BACKEND=gemini|groq|anthropic|ollama|mistral  (default: gemini)\n"
            "  EXTRACT_CLAIMS=1  — enable claims extraction during ingest\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("all",   help="Ingest all new PDFs from raw/")
    sub.add_parser("index", help="Rebuild wiki/index.md from existing pages")
    sub.add_parser("index-vectors", help="Build semantic embedding index (requires MISTRAL_API_KEY + numpy)")
    sub.add_parser("lint",  help="Check for broken wikilinks and orphan pages")

    p_ingest = sub.add_parser("ingest", help="Ingest a single PDF file")
    p_ingest.add_argument("pdf", help="Path to the PDF file")
    p_ingest.add_argument("--claims", action="store_true",
                          help="Extract structured claims from the paper (extra LLM call)")

    p_ingest_md = sub.add_parser("ingest-md", help="Ingest a single Markdown file (web clip, note, README)")
    p_ingest_md.add_argument("file", help="Path to the .md file")

    p_query = sub.add_parser("query", help="Search across the KB")
    p_query.add_argument("search", help="Search terms (quoted string)")
    p_query.add_argument("--semantic", action="store_true",
                         help="Use semantic (embedding) search instead of keyword matching")

    p_reingest = sub.add_parser("reingest", help="Re-ingest all PDFs, overwriting existing wiki pages")
    p_reingest.add_argument("--fresh", action="store_true",
                            help="Clear log/ cache and re-extract PDFs via PDF_BACKEND (slower)")

    sub.add_parser("fix-tags", help="Strip bad tags and re-run keyword matcher on all pages")
    sub.add_parser("fix-links", help="Repair broken [[wikilinks]] using fuzzy slug matching")

    p_link = sub.add_parser("link", help="Add See Also wikilinks between related pages")
    p_link.add_argument("--top", type=int, default=5,
                        help="Number of related pages to link per page (default: 5)")

    sub.add_parser("make-hubs", help="Create category hub pages and add Categories links to all papers")

    p_cleanup = sub.add_parser("cleanup", help="Remove wiki pages whose source PDF is no longer in raw/")
    p_cleanup.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    p_export = sub.add_parser("export", help="Generate a deliverable from wiki knowledge on a topic")
    p_export.add_argument("topic", help="Topic or research question to export")
    p_export.add_argument("--format", "-f", default="marp",
                          choices=["marp", "latex", "csv", "report"],
                          help="Output format (default: marp)")

    p_crystallize = sub.add_parser("crystallize", help="Distill a mission file into a permanent concept page")
    p_crystallize.add_argument("file", nargs="?", help="Path to research mission markdown file (auto-detects latest if omitted)")

    p_ask = sub.add_parser("ask", help="Synthesize an answer from the KB (Q&A with citations)")
    p_ask.add_argument("question", help="Research question (quoted string)")
    p_ask.add_argument("--top", type=int, default=8,
                       help="Number of pages to draw from (default: 8)")
    p_ask.add_argument("--save", action="store_true",
                       help="Save the answer as wiki/concepts/qa-*.md")

    p_hc = sub.add_parser("health-check", help="Structural lint + LLM content audit of the KB")
    p_hc.add_argument("--topic", default=None,
                      help="Scope the LLM audit to pages matching this topic (default: full KB)")
    p_hc.add_argument("--structural-only", action="store_true",
                      help="Run structural checks only (no LLM call)")

    sub.add_parser("cross-synthesize", help="Add Cross-KB Insights section to every wiki page")
    sub.add_parser("redo", help="Full KB rebuild: fresh reingest → cross-synthesize → link → hubs → index")

    args = parser.parse_args()

    if args.command == "all":
        ingest_all()
    elif args.command == "ingest":
        ingest_pdf(Path(args.pdf), with_claims=args.claims)
        rebuild_index()
    elif args.command == "ingest-md":
        ingest_md(Path(args.file))
        rebuild_index()
    elif args.command == "query":
        if args.semantic:
            query_semantic(args.search)
        else:
            query_kb(args.search)
    elif args.command == "index":
        rebuild_index()
    elif args.command == "index-vectors":
        index_vectors_semantic()
    elif args.command == "lint":
        lint()
    elif args.command == "reingest":
        reingest_all(fresh=args.fresh)
    elif args.command == "fix-tags":
        fix_tags()
    elif args.command == "fix-links":
        fix_broken_links()
    elif args.command == "link":
        link_pages(top_n=args.top)
    elif args.command == "make-hubs":
        make_hubs()
    elif args.command == "cleanup":
        cleanup_orphans(force=args.force)
    elif args.command == "export":
        export_kb(args.topic, fmt=args.format)
    elif args.command == "crystallize":
        crystallize(args.file)
    elif args.command == "ask":
        ask_kb(args.question, top_k=args.top, save=args.save)
    elif args.command == "health-check":
        health_check(topic=args.topic, structural_only=args.structural_only)
    elif args.command == "cross-synthesize":
        cross_synthesize()
    elif args.command == "redo":
        redo()


class WikiManager:
    """Thin class wrapper so pipeline/orchestrator.py can import WikiManager."""

    def crystallize(self, mission_file: str | None = None) -> None:
        crystallize(mission_file)


if __name__ == "__main__":
    main()
