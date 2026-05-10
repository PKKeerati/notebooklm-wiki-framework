#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rename_papers.py - Rename wiki pages and PDFs to a consistent format.

Target format:  {YYYY_MM}_[{FirstAuthor},{CorrespAuthor}]_{Title}
Example:        2024_06_[Batatia,Csanyi]_MACE-Higher-Order-Equivariant

Usage:
    python scripts/rename_papers.py           # dry-run (show proposed renames)
    python scripts/rename_papers.py --apply   # actually rename files
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
WIKI_DIR     = PROJECT_ROOT / "wiki"
RAW_DIR      = PROJECT_ROOT / "raw"
LOG_DIR      = PROJECT_ROOT / "log"
VECTORS_PATH = WIKI_DIR / ".vectors.json"
INDEX_PATH   = WIKI_DIR / "index.md"

MONTHS = {
    "january": "01",  "february": "02", "march": "03",    "april": "04",
    "may": "05",      "june": "06",     "july": "07",     "august": "08",
    "september": "09","october": "10",  "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
}

# Markers that mean the title/author field caught the wrong line
BAD_TITLE_SIGNALS = [
    r"^\d+\s*(department|school|institute|university|laboratory|college|center|centre)",
    r"^\d+[A-Z]",        # "1Department of..."
    r"@",                # email address
    r"ocw\.mit\.edu",
    r"^\s*cite as",
    r"^\s*to cite",
    r"^published",
    r"^\s*received\s+\d",
    r"^doi:",
    r"^https?://",
]

# Words that are definitely not a person's surname
NOT_SURNAMES = {
    # institutions / org types
    "laboratory", "lab", "institute", "university", "department", "college",
    "centre", "center", "school", "faculty", "division", "group", "team",
    # cities / countries
    "london", "cambridge", "oxford", "usa", "uk", "germany", "china", "japan",
    "france", "australia", "canada", "korea", "switzerland", "princeton",
    "harvard", "stanford", "cornell", "mit", "caltech", "beijing", "tokyo",
    "jerusalem", "paris", "berlin", "chicago", "boston", "amsterdam",
    # domain / science keywords
    "computational", "materials", "physics", "chemistry", "mathematics",
    "science", "engineering", "technology", "perovskites", "alloy",
    "extrapolation", "initial", "scattering", "potential", "transfer",
    "theory", "review", "advanced", "physical", "tutorial", "ace",
    "conductivity", "reaction", "surfaces", "material", "discovery",
    "anharmonicity", "batteries", "battery", "constants", "cycle",
    "stable", "stability", "score", "electrical", "electronic", "pristine",
    "translations", "laws", "classic", "learning", "machine", "deep",
    "neural", "network", "model", "models", "method", "methods", "approximation",
    "significance", "challenges", "applications", "properties", "effects",
    "reality", "thermal", "molecules", "redox", "conspectus", "fundamentals",
    "abstract", "introduction", "conclusion", "results", "discussion",
    "first", "second", "third", "fourth", "fifth", "part", "volume",
    "crystal", "structure", "energy", "force", "density", "functional",
    "molecular", "atomic", "quantum", "classical", "simulation",
    "gradient", "hessian", "kernel", "gaussian", "bayesian",
    # publication / metadata words
    "author", "publisher", "honours", "published", "received", "accepted",
    "abstract", "journal", "volume", "issue", "chapter", "section",
    "proceedings", "preprint", "report", "thesis", "dissertation",
    # prepositions / articles / conjunctions / pronouns
    "of", "the", "in", "on", "at", "by", "for", "and", "or", "is", "an",
    "this", "that", "with", "from", "to", "we", "our", "its",
    # Roman numerals (e.g. "Part II")
    "i", "ii", "iii", "iv", "vi", "vii", "viii", "ix", "xi", "xii", "xiii",
    # German institution words
    "festkorperforschung", "forschungszentrum", "julich", "jülich",
    "gesellschaft", "akademie", "hochschule",
    # sentinel
    "unknown",
}


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _field(text: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _looks_bad(s: str) -> bool:
    s_low = s.lower()
    return any(re.search(p, s_low) for p in BAD_TITLE_SIGNALS)


def get_title(wiki_text: str, pdf_stem: str) -> str:
    title = _field(wiki_text, "title")

    if title and not _looks_bad(title) and len(title) > 10:
        return title

    # Fallback: derive from PDF filename
    # Strip author prefix patterns like "[A. Bartok]" or "Eriksson et al. - 2018 - "
    name = pdf_stem
    name = re.sub(r"^\[.*?\]\s*", "", name)                        # [Author] prefix
    name = re.sub(r"^[\w\s.]+\s+-\s+\d{4}\s+-\s+", "", name)      # "Author - Year - "
    name = re.sub(r"^\d{4}_\d{2}_", "", name)                      # already dated prefix
    name = name.replace("_", " ").replace("-", " ").strip()
    return name if name else pdf_stem


def get_year_month(wiki_text: str, log_text: str) -> tuple:
    year = _field(wiki_text, "year")
    if not re.match(r"^\d{4}$", year):
        # Try from log text
        m = re.search(r"\b(19[89]\d|20[012]\d)\b", log_text[:3000])
        year = m.group(1) if m else "XXXX"

    # Month: search near the year in raw text
    month = "XX"
    for mon_name, mon_num in MONTHS.items():
        pattern = rf"(?i){mon_name}\.?\s+{year}|{year}\s+{mon_name}"
        if re.search(pattern, log_text[:4000]):
            month = mon_num
            break

    # Also check venue: NeurIPS→12, ICLR→05, ICML→07, CVPR→06, AAAI→02
    if month == "XX":
        venue = _field(wiki_text, "venue").lower()
        venue_months = {
            "neurips": "12", "nips": "12", "iclr": "05", "icml": "07",
            "cvpr": "06", "aaai": "02", "iccv": "10", "eccv": "10",
        }
        for kw, mon in venue_months.items():
            if kw in venue:
                month = mon
                break

    return year, month


def _is_valid_surname(s: str) -> bool:
    """True if s looks like a real person's surname."""
    s_low = s.lower().strip()
    # Normalise unicode ligatures (fi, fl, etc.) before checking
    s_norm = unicodedata.normalize("NFKC", s_low)
    clean = re.sub(r"[^\w]", "", s_norm)
    if not clean or len(clean) < 2:
        return False
    # Purely numeric (e.g. "1998", "2021")
    if clean.isdigit():
        return False
    # Trailing digit means affiliation superscript crept in (e.g. "Liao1", "Riutort-Mayol1")
    if clean[-1].isdigit():
        return False
    # Very short (1 char) — not a surname
    if len(clean) < 2:
        return False
    # Looks like a URL or DOI slug
    if re.search(r"https?|doi|arxiv|\d{4,}", clean):
        return False
    if clean in NOT_SURNAMES or s_norm in NOT_SURNAMES:
        return False
    # Reject institution-like patterns
    if re.search(r"(laboratory|institute|university|department|college|centre|center|"
                 r"school|faculty|division|vol\.|issue|doi:|journal)", s_norm):
        return False
    return True


def _parse_authors_from_log(log_text: str) -> tuple:
    """Try to find real author names in the raw log text.

    Only accepts lines that visually match known author-list formats:
      "A. Smith, B. Jones, C. Brown"   (initial-dot surname)
      "Alice Smith, Bob Jones"          (firstname surname)
    """
    top = log_text[:4000]
    corresp_marker = re.compile(r"[*✉†‡§∗]")

    # Patterns that look like a single author token
    _name_token = re.compile(
        r"^(?:[A-Z]\.(?:\s*[A-Z]\.)*\s+[A-Z][a-z\-]{1,20}"   # "A. Smith" / "A.B. Smith"
        r"|[A-Z][a-z\-]{1,15}\s+[A-Z][a-z\-]{1,20}"           # "Alice Smith"
        r"|[A-Z][a-z\-]{1,20},\s*[A-Z]\.?)"                    # "Smith, A."
        r"[*✉†‡§∗]?$"
    )

    for line in top.split("\n")[:60]:
        line = line.strip()
        if not (10 < len(line) < 250):
            continue
        # Skip lines with URLs, DOIs, years, or numbers
        if re.search(r"https?://|doi:|arxiv|\d{4,}|\d{2,}\s*(pages|pp)", line.lower()):
            continue
        # Skip lines with institution / metadata words
        if re.search(r"(department|university|institute|laboratory|college|centre|center|"
                     r"abstract|introduction|journal|received|published|copyright|"
                     r"volume|issue|chapter|section|proceedings|preprint)", line.lower()):
            continue
        # Split on commas/semicolons/and
        parts = [corresp_marker.sub("", p).strip()
                 for p in re.split(r"[,;]|\band\b", line) if p.strip()]
        if len(parts) < 2:
            continue
        # All parts must match an author token pattern
        if not all(_name_token.match(p) for p in parts):
            continue

        def ln(s: str) -> str:
            # "A. Smith" → "Smith";  "Smith, A." → "Smith";  "Alice Smith" → "Smith"
            s = re.sub(r"^[A-Z]\.(?:\s*[A-Z]\.)*\s+", "", s)   # strip initials prefix
            s = re.sub(r",.*$", "", s)                           # strip ", A." suffix
            return s.strip().split()[-1] if s.strip() else ""

        surnames = [ln(p) for p in parts]
        valid = [s for s in surnames if _is_valid_surname(s)]
        if len(valid) >= 2:
            return valid[0], valid[-1]
        if len(valid) == 1:
            return valid[0], valid[0]

    return "Unknown", "Unknown"


def get_authors(wiki_text: str, log_text: str = "") -> tuple:
    """Return (first_author_lastname, corresp_author_lastname)."""
    raw = _field(wiki_text, "authors")

    if not raw or raw.lower() in ("unknown", ""):
        return _parse_authors_from_log(log_text) if log_text else ("Unknown", "Unknown")

    # If the field looks like it caught an institution, bail early to log fallback
    if _looks_bad(raw) or len(raw) > 200:
        return _parse_authors_from_log(log_text) if log_text else ("Unknown", "Unknown")

    # Normalise: remove superscripts, affiliation numbers, URLs
    cleaned = re.sub(r"\d+[,\s]", " ", raw)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Detect corresponding author (marked with * or ✉)
    corresp_marker = re.compile(r"[*✉†‡§∗]")
    corresp_name = None

    # Split by comma or semicolon into individual author chunks
    parts = [p.strip() for p in re.split(r"[,;]", cleaned) if p.strip()]

    def lastname(s: str) -> str:
        s = corresp_marker.sub("", s).strip()
        # "Lastname, Firstname" → Lastname
        if re.search(r",", s):
            return s.split(",")[0].strip()
        # "Firstname MI Lastname" → last word
        words = s.split()
        return words[-1] if words else s

    first = "Unknown"
    for part in parts:
        ln = lastname(part)
        if _is_valid_surname(ln):
            first = ln
            break

    for part in parts:
        if corresp_marker.search(part):
            ln = lastname(part)
            if _is_valid_surname(ln):
                corresp_name = ln
                break
    if not corresp_name:
        for part in reversed(parts):
            ln = lastname(part)
            if _is_valid_surname(ln):
                corresp_name = ln
                break

    # If we still got bad names, try log text
    if first == "Unknown" and log_text:
        return _parse_authors_from_log(log_text)

    return first or "Unknown", corresp_name or first or "Unknown"


def safe_name(s: str, max_len: int = 60) -> str:
    """Make a filesystem-safe string: keep alphanum, hyphens, underscores."""
    s = re.sub(r"[^\w\s\-]", "", s)     # strip punctuation
    s = re.sub(r"\s+", "-", s.strip())  # spaces → hyphens
    s = re.sub(r"-{2,}", "-", s)        # collapse double hyphens
    return s[:max_len].strip("-")


def build_new_stem(year: str, month: str, first: str, corresp: str, title: str) -> str:
    f = safe_name(first, 20)
    c = safe_name(corresp, 20)
    t = safe_name(title, 60)
    authors_part = f"[{f},{c}]" if f != c else f"[{f}]"
    return f"{year}_{month}_{authors_part}_{t}"


# ---------------------------------------------------------------------------
# Main rename logic
# ---------------------------------------------------------------------------

def load_vectors() -> dict:
    if VECTORS_PATH.exists():
        try:
            return json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def rebuild_index() -> None:
    from datetime import datetime
    pages = sorted(WIKI_DIR.glob("*.md"), key=lambda p: p.stem)
    tagged: dict = {}
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

    today = datetime.now().strftime("%Y-%m-%d")
    lines = ["# Wiki Index\n\n", f"*Updated: {today} - {len(pages)-1} pages*\n\n"]
    for tag, entries in sorted(tagged.items()):
        lines.append(f"## {tag}\n\n")
        for yr, ttl, sl in sorted(entries, key=lambda x: x[0], reverse=True):
            lines.append(f"- [[{sl}|{ttl}]] ({yr})\n")
        lines.append("\n")
    INDEX_PATH.write_text("".join(lines), encoding="utf-8")


def run(apply: bool) -> None:
    wiki_pages = [p for p in sorted(WIKI_DIR.glob("*.md")) if p.name != "index.md"]
    vectors = load_vectors()
    new_vectors: dict = {}

    seen_stems: set = set()
    renames: list = []   # (old_wiki, new_wiki, old_pdf, new_pdf)

    print(f"{'DRY RUN — no files changed' if not apply else 'APPLYING RENAMES'}")
    print("-" * 70)

    for wiki_page in wiki_pages:
        wiki_text = wiki_page.read_text(encoding="utf-8", errors="ignore")

        # Find original PDF stem from Source line
        src_m = re.search(r"Source: `(.+?)`", wiki_text)
        pdf_stem = Path(src_m.group(1)).stem if src_m else wiki_page.stem

        # Load log file for month extraction
        log_file = LOG_DIR / (pdf_stem + ".txt")
        log_text = ""
        if log_file.exists():
            log_text = log_file.read_text(encoding="utf-8", errors="ignore")[:6000]

        title              = get_title(wiki_text, pdf_stem)
        year, month        = get_year_month(wiki_text, log_text)
        first, corresp     = get_authors(wiki_text, log_text)
        new_stem           = build_new_stem(year, month, first, corresp, title)

        # Ensure uniqueness
        base_stem = new_stem
        suffix = 1
        while new_stem in seen_stems:
            new_stem = f"{base_stem}_{suffix}"
            suffix += 1
        seen_stems.add(new_stem)

        new_wiki = WIKI_DIR / f"{new_stem}.md"
        old_pdf  = RAW_DIR / (pdf_stem + ".pdf")
        new_pdf  = RAW_DIR / f"{new_stem}.pdf"

        changed = new_stem != wiki_page.stem

        if changed:
            print(f"\n  OLD wiki: {wiki_page.name}")
            print(f"  NEW wiki: {new_wiki.name}")
            if old_pdf.exists():
                print(f"  OLD pdf:  {old_pdf.name}")
                print(f"  NEW pdf:  {new_pdf.name}")
            else:
                print(f"  PDF:      not found in raw/ (skipping PDF rename)")

        renames.append((wiki_page, new_wiki, old_pdf if old_pdf.exists() else None, new_pdf))

        # Update vectors entry
        old_key = wiki_page.stem
        if old_key in vectors:
            entry = vectors[old_key].copy()
            entry["page"] = new_wiki.name
            new_vectors[new_stem] = entry
        else:
            new_vectors[new_stem] = {"page": new_wiki.name}

    if not apply:
        changed_count = sum(1 for o, n, *_ in renames if o.stem != n.stem)
        print(f"\n{'=' * 70}")
        print(f"Would rename {changed_count} of {len(renames)} wiki pages.")
        print(f"Run with --apply to execute.")
        return

    # Apply renames
    ok = 0
    for old_wiki, new_wiki, old_pdf, new_pdf in renames:
        if old_wiki.stem == new_wiki.stem:
            continue
        try:
            old_wiki.rename(new_wiki)
            if old_pdf and old_pdf != new_pdf:
                old_pdf.rename(new_pdf)
            ok += 1
        except Exception as e:
            print(f"  FAIL {old_wiki.name}: {e}", file=sys.stderr)

    # Save updated vectors
    VECTORS_PATH.write_text(
        json.dumps(new_vectors, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Rebuild index
    rebuild_index()

    print(f"\nDone. {ok} files renamed. Index and vectors updated.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Rename wiki pages and PDFs to standard format.")
    parser.add_argument("--apply", action="store_true", help="Actually rename files (default: dry-run)")
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
