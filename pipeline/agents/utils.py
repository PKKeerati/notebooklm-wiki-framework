"""Shared utilities for pipeline agents."""
import json
import re
import time
import urllib.parse
import urllib.request


def search_semantic_scholar(query: str, limit: int = 10) -> list[dict]:
    """Search Semantic Scholar API. Returns list of paper dicts."""
    import os
    base = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = urllib.parse.urlencode({
        "query": query,
        "limit": limit,
        "fields": "title,authors,year,externalIds,openAccessPdf,abstract",
    })
    url = f"{base}?{params}"
    headers = {"User-Agent": "notebooklm-wiki-pipeline/1.0"}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("data", [])
    except Exception:
        return []


def paper_citation(paper: dict) -> str:
    """Format a Semantic Scholar paper dict as a citation string."""
    authors = paper.get("authors", [])
    first_author = authors[0].get("name", "Unknown") if authors else "Unknown"
    author_str = f"{first_author} et al." if len(authors) > 1 else first_author
    year = paper.get("year", "n.d.")
    title = paper.get("title", "Unknown title")
    ext = paper.get("externalIds", {})
    if ext.get("DOI"):
        link = f"https://doi.org/{ext['DOI']}"
    elif ext.get("ArXiv"):
        link = f"https://arxiv.org/abs/{ext['ArXiv']}"
    else:
        link = ""
    return f"{author_str} ({year}). {title}. {link}".strip()


def paper_url(paper: dict) -> str:
    """Return the best loadable URL for a paper (arXiv preferred for NLM)."""
    ext = paper.get("externalIds", {})
    if ext.get("ArXiv"):
        return f"https://arxiv.org/abs/{ext['ArXiv']}"
    pdf = paper.get("openAccessPdf")
    if pdf and pdf.get("url"):
        return pdf["url"]
    if ext.get("DOI"):
        return f"https://doi.org/{ext['DOI']}"
    return ""


def format_papers_for_llm(papers: list[dict]) -> str:
    """Format a list of Semantic Scholar papers for LLM consumption."""
    lines = []
    for i, p in enumerate(papers, 1):
        url = paper_url(p)
        authors = p.get("authors", [])
        first = authors[0].get("name", "?") if authors else "?"
        author_str = f"{first} et al." if len(authors) > 1 else first
        abstract = (p.get("abstract") or "")[:200]
        lines.append(
            f"[{i}] {author_str} ({p.get('year', '?')}). {p.get('title', '?')}\n"
            f"    URL: {url or 'no open-access URL'}\n"
            f"    Abstract: {abstract}..."
        )
    return "\n\n".join(lines)


# Known ML potential / HEA keyword patterns for Chompoo query extraction
_MODEL_NAMES = re.compile(
    r"\b(MACE|NequIP|Allegro|ACE|GemNet|PaiNN|SpookyNet|CHGNet|SevenNet|"
    r"DeePMD|SchNet|DimeNet|ForceNet|M3GNet|ALIGNN|BOWSR|GAP|ANI)\b",
    re.IGNORECASE,
)
_MATERIAL_TERMS = re.compile(
    r"\b(high.entropy alloy|HEA|Cantor alloy|CoCrFeMnNi|NbMoTaW|"
    r"refractory alloy|multicomponent alloy|interatomic potential|"
    r"force field|elastic constant|stacking fault|phonon|MD simulation)\b",
    re.IGNORECASE,
)


def extract_search_keywords(title: str, fact: str) -> str:
    """Extract concise search query from an insight title + fact."""
    text = f"{title} {fact}"
    models = _MODEL_NAMES.findall(text)
    materials = _MATERIAL_TERMS.findall(text)
    # Deduplicate preserving order
    seen: set[str] = set()
    terms: list[str] = []
    for t in models + materials:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            terms.append(t)
    if terms:
        return " ".join(terms[:6])
    # Fallback: first 8 words of title
    return " ".join(title.split()[:8])
