#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
structure_local.py - Structure all log/*.txt files into wiki pages with no API.

Uses heuristic text parsing to extract title, authors, year, abstract,
and classify domain. Runs instantly on all 232 papers.

Usage:
    python scripts/structure_local.py
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR      = PROJECT_ROOT / "log"
WIKI_DIR     = PROJECT_ROOT / "wiki"
VECTORS_PATH = WIKI_DIR / ".vectors.json"
INDEX_PATH   = WIKI_DIR / "index.md"

TODAY = datetime.now().strftime("%Y-%m-%d")

# Files to skip (non-research documents)
SKIP_STEMS = {
    "01779167 Research proposal confirmation_Keerati Keeratikarn",
    "01779167_Research_Proposal_Confirmation_Keerati_Keeratikarn",
    "Biography",
    "booking confirmation for return trip London Euston to Coventry (11 September 17_16 - 15 September 14_45) (002)",
    "Customer Gateway",
    "EuroStar_reciept",
    "G00 028340 Keeratikarn",
    "hwloc-a4",
    "hwloc-letter",
    "Imperial College eModule _ Secure Documents",
    "Late-Stage-24M-Review-Form-2023_AW_JMF",
    "MathsProblemsUnit1",
    "MathsProblemsUnit2",
    "MathsProblemsUnit3_updated",
    "MathsProblemsUnit4_updated",
    "ModuleHandbook_22_23",
    "OVGU_SIGN_druck-eps-converted-to",
    "Poster test",
    "Poster-APS-March-2022 A3 QR",
    "Poster-APS-March-2022-poster-QR",
    "ProofForm",
    "Script",
    "Seattle plan",
    "SteinerScan_1",
    "SteinerScan_2",
    "tourist_visa_web",
    "visa_type_document_tourism",
    "interactnlmsample",
    "new",
    # Additional non-research files identified after first run
    "1a3acae0-9f5f-4583-93e0-7139acc42c4c",   # visa decision letter
    "86125f6aee6d87f76de0b5b368fe99d5",        # student records email
    "Deep-Reinforcement-Learning-for-Trading", # finance, not materials science
    "journal.pone.0255558",                    # economics/management paper
    "pthic20",                                 # unidentifiable Latin text
    "Python-code-for-GP (1)",                  # corrupted scan
    "Abstract_ANSCSE29_2026",                  # conference abstract stub
    "Chapter 2 Motion in One Dimension",       # intro physics lecture
    "Chapter 2 Tutorial",                      # intro physics tutorial
    "CHAPTER 3 (LECTURE NOTES)",               # intro physics lecture
}

# Domain taxonomy
TAXONOMY = {
    "ml-potentials":       ["mace", "nequip", "chgnet", "schnet", "ace potential", "interatomic potential",
                            "machine learning potential", "neural network potential", "gap potential",
                            "gaussian approximation potential", "machine-learned"],
    "gaussian-processes":  ["gaussian process", "gp regression", "gaussian approximation", "kernel",
                            "bayesian optimization", "surrogate model", "derivative observations"],
    "phonons-thermal":     ["phonon", "anharmonic", "thermal conductivity", "lattice dynamics",
                            "heat transport", "phono3py", "phonopy", "force constants"],
    "perovskites":         ["perovskite", "lead halide", "methylammonium", "hybrid perovskite",
                            "solar cell", "photovoltaic", "halide"],
    "equivariant-ml":      ["equivariant", "e(3)", "so(3)", "spherical harmonic", "clebsch-gordan",
                            "wigner", "irreducible representation", "se(3)", "young tableau",
                            "young diagram", "tensor representation"],
    "electronic-structure":["dft", "density functional", "vasp", "quantum chemistry", "ab initio",
                            "first principles", "kohn-sham"],
    "generative-models":   ["diffusion model", "flow matching", "vae", "inverse design",
                            "generative model", "crystal generation"],
    "molecular-ml":        ["molecular", "smiles", "conformer", "charge transfer", "organic semiconductor",
                            "electron transfer coupling", "charge transport"],
    "energy-storage":      ["battery", "potassium-oxygen", "lithium-air", "li-air", "fuel cell",
                            "superoxide", "cathode", "electrolyte", "energy storage", "oxygen battery",
                            "dendrite", "potassium oxygen", "metal-air", "li2o2"],
    "photonics":           ["photonic", "optoelectronic", "laser", "optical", "quantum dot",
                            "quantum well", "photoluminescence", "semiconductor laser"],
    "quantum-computing":   ["qubit", "quantum gate", "quantum circuit", "quantum programming",
                            "quantum harmonic oscillator", "quantum simulation"],
    "physics-textbook":    ["lecture notes", "undergraduate", "textbook", "problem set",
                            "ocw.mit.edu", "tutorial", "exercises"],
    "group-theory":        ["group theory", "representation theory", "symmetry", "angular momentum",
                            "spherical tensor", "clebsch-gordan coefficient", "wigner d-matrix"],
    "condensed-matter":    ["condensed matter", "solid state", "band structure", "fermi", "lattice",
                            "crystal structure", "magnetism"],
}


def slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.lower()).strip("-")[:60]


def extract_title(text: str, filename: str) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Heuristic: title is usually one of the first substantial lines
    # Skip very short lines, URLs, and lines that look like headers/footers
    candidates = []
    for line in lines[:20]:
        if (15 < len(line) < 180
                and not line.startswith("http")
                and not re.match(r"^\d+$", line)
                and not re.match(r"^(page|vol|doi|arxiv|journal|copyright)", line.lower())
                and not line.isupper()  # skip ALL CAPS section headers
                ):
            candidates.append(line)

    if candidates:
        # Prefer the longest candidate in the first few (titles tend to be descriptive)
        return max(candidates[:5], key=len)

    # Fallback: clean up filename
    name = filename.replace(".txt", "")
    name = re.sub(r"^\[.*?\]\s*", "", name)   # remove [Author] prefix
    name = name.replace("_", " ").replace("-", " ")
    return name.strip()


def extract_authors(text: str) -> str:
    # Look for author patterns near the top of the document
    top = text[:3000]

    # Pattern: lines with multiple capitalized names separated by commas
    for line in top.split("\n")[:30]:
        line = line.strip()
        if (10 < len(line) < 200
                and re.search(r"[A-Z][a-z]+,?\s+[A-Z]", line)
                and not re.search(r"(abstract|introduction|journal|university|department|institute)", line.lower())
                and len(re.findall(r"[A-Z]", line)) >= 2
                ):
            return line[:100]

    return "unknown"


def extract_year(text: str) -> str:
    # Search first 3000 chars for a 4-digit year
    matches = re.findall(r"\b(19[89]\d|20[012]\d)\b", text[:3000])
    if matches:
        # Prefer years in range 1990-2026
        valid = [m for m in matches if 1990 <= int(m) <= 2026]
        if valid:
            return valid[0]
    return "unknown"


def extract_venue(text: str) -> str:
    top = text[:3000]
    venue_patterns = [
        r"(NeurIPS|ICML|ICLR|Nature|Science|Physical Review|PRB|PRL|JCTC|J\. Chem\. Phys|"
        r"npj Computational Materials|arXiv|Phys\. Rev\.|J\. Phys\.|ACS|Nat\. Commun|"
        r"Nat\. Mater|J\. Chem\. Theory|Machine Learning|PNAS|Angew\. Chem|"
        r"Advanced Materials|J\. Phys\. Chem|RSC|Wiley|Springer)[\w\s.:]*",
    ]
    for pattern in venue_patterns:
        m = re.search(pattern, top)
        if m:
            return m.group(0).strip()[:80]
    return "unknown"


def extract_abstract(text: str) -> str:
    # Look for Abstract section
    m = re.search(
        r"(?i)\bAbstract\b[\s\n:]+(.{100,1500}?)(?=\n\s*\n|\n(?:1[\.\s]|Introduction|Keywords|I\.\s))",
        text,
        re.DOTALL,
    )
    if m:
        abstract = m.group(1).strip()
        abstract = re.sub(r"\s+", " ", abstract)
        return abstract[:600]

    # Fallback: take first substantial paragraph
    paragraphs = re.split(r"\n\s*\n", text)
    for para in paragraphs[1:5]:
        para = para.strip()
        if 100 < len(para) < 800:
            return re.sub(r"\s+", " ", para)[:500]

    return "[Abstract not extracted - check log/ for raw text]"


def classify_tags(text: str, title: str) -> list:
    combined = (title + " " + text[:8000]).lower()
    tags = []
    for tag, keywords in TAXONOMY.items():
        if any(kw in combined for kw in keywords):
            tags.append(f"#{tag}")
    return tags or ["#uncategorized"]


def extract_key_findings(text: str) -> list:
    findings = []

    # Look for conclusion/results sections
    for section in ["conclusion", "result", "finding", "summary", "discussion"]:
        m = re.search(
            rf"(?i)\b{section}s?\b[\s\n:]+(.{{100,2000}}?)(?=\n\s*\n\s*[A-Z]|\Z)",
            text,
            re.DOTALL,
        )
        if m:
            content = m.group(1).strip()
            # Split into sentences
            sentences = re.split(r"(?<=[.!?])\s+", content)
            for s in sentences[:4]:
                s = re.sub(r"\s+", " ", s).strip()
                if 30 < len(s) < 200:
                    findings.append(s)
            if findings:
                break

    return findings[:4] if findings else ["[Key findings not extracted - check log/ for raw text]"]


def build_page(title: str, authors: str, year: str, venue: str,
               abstract: str, findings: list, tags: list, filename: str) -> str:
    findings_md = "\n".join(f"- {f}" for f in findings)
    tags_str = " ".join(tags)

    return f"""---
title: {title}
authors: {authors}
year: {year}
venue: {venue}
type: paper
tags: {tags_str}
---

# {title}

## Abstract
{abstract}

## Key Findings
{findings_md}

## Methods
- [See full text in log/{filename}]

## Results
- [See full text in log/{filename}]

## Limitations
- [See full text in log/{filename}]

## Relevance
Classified under: {tags_str}

## Citation
{authors} ({year}). {title}. {venue}.

---
*Ingested: {TODAY} | Source: `{filename.replace('.txt', '.pdf')}`*
"""


def update_vectors(vectors: dict, page_stem: str, title: str, year: str,
                   authors: str, venue: str, tags: list, findings: list) -> None:
    vectors[page_stem] = {
        "title":    title,
        "year":     year,
        "authors":  authors,
        "venue":    venue,
        "tags":     " ".join(tags),
        "keywords": " ".join(findings[:3]),
        "page":     f"{page_stem}.md",
    }


def rebuild_index(wiki_dir: Path) -> None:
    pages = sorted(wiki_dir.glob("*.md"), key=lambda p: p.stem)
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

    lines = [
        "# Wiki Index\n\n",
        f"*Updated: {TODAY} - {len(pages) - 1} pages*\n\n",
    ]
    for tag, entries in sorted(tagged.items()):
        lines.append(f"## {tag}\n\n")
        for year, title, s in sorted(entries, key=lambda x: x[0], reverse=True):
            lines.append(f"- [[{s}|{title}]] ({year})\n")
        lines.append("\n")

    INDEX_PATH.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    WIKI_DIR.mkdir(exist_ok=True)
    txt_files = sorted(LOG_DIR.glob("*.txt"))

    vectors = {}
    if VECTORS_PATH.exists():
        try:
            vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    ok = skipped = failed = 0

    for txt in txt_files:
        stem = txt.stem

        if stem in SKIP_STEMS:
            print(f"  skip  {stem[:60]}")
            skipped += 1
            continue

        page_path = WIKI_DIR / f"{slug(stem)}.md"
        if page_path.exists():
            print(f"  exists  {stem[:60]}")
            skipped += 1
            continue

        try:
            text = txt.read_text(encoding="utf-8", errors="ignore")
            if len(text.strip()) < 50:
                print(f"  empty  {stem[:60]}")
                skipped += 1
                continue

            title    = extract_title(text, txt.name)
            authors  = extract_authors(text)
            year     = extract_year(text)
            venue    = extract_venue(text)
            abstract = extract_abstract(text)
            findings = extract_key_findings(text)
            tags     = classify_tags(text, title)

            page_content = build_page(title, authors, year, venue,
                                      abstract, findings, tags, txt.name)
            page_path.write_text(page_content, encoding="utf-8")
            update_vectors(vectors, page_path.stem, title, year, authors, venue, tags, findings)

            print(f"  OK  {title[:70]}")
            ok += 1

        except Exception as e:
            print(f"  FAIL  {stem[:60]} - {e}", file=sys.stderr)
            failed += 1

    VECTORS_PATH.write_text(json.dumps(vectors, indent=2, ensure_ascii=False), encoding="utf-8")
    rebuild_index(WIKI_DIR)

    total_pages = len(list(WIKI_DIR.glob("*.md"))) - 1
    print(f"\nDone. {ok} pages created, {skipped} skipped, {failed} failed.")
    print(f"Wiki: {total_pages} pages total across {len(TAXONOMY)} domains.")


if __name__ == "__main__":
    main()
