"""Score raw/ PDFs for relevance to a research query — Option 3.

Score = semantic_similarity (cosine, wiki semantic index)
      + topic_bonus          (keyword group matches)
      + recency_bonus        (year from filename)

Degrades gracefully:
  - No semantic index → topic + recency only (no API calls)
  - No API key        → keyword-only (topic + recency)
  - No wiki meta      → filename keywords only
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

_YEAR_RE = re.compile(r"\b(19|20)(\d{2})\b")

# ── Fallback topic keyword groups (used only when Dao provides none) ──────────
# Hard-coded for the Mg-hydride / MLIP domain. At runtime these are replaced
# by the query-specific groups Dao writes into its handoff.
_DOMAIN_GROUPS: list[tuple[list[str], float]] = [
    (["mg", "mgh2", "magnesium", "mgni", "mgga", "mgla", "mg-based",
      "mg2ni", "mg2co", "mg-h"], 0.30),
    (["pci", "isotherm", "pressure-composition", "pressure composition",
      "plateau", "hysteresis", "desorption", "absorption", "sorption",
      "thermodynamic"], 0.30),
    (["mlip", "mace", "nequip", "gap", " ace ", "interatomic potential",
      "machine learning potential", "neural network potential",
      "force field", "mlp", "machine-learned", "machine learned"], 0.30),
    (["gcmc", "grand canonical", "munpt", "monte carlo",
      "chemical potential", "grand-canonical"], 0.30),
    (["phase transition", "hydrogen storage", "hydrogen diffusion",
      "hydride formation", "hydrogenation", "dehydrogenation"], 0.20),
]

_WEIGHT_MAP = {"high": 0.30, "medium": 0.20, "low": 0.10}


def parse_keyword_groups(dao_handoff: str) -> list[tuple[list[str], float]]:
    """Parse the ### Keyword Groups section from Dao's handoff.

    Returns list of (terms, weight) ready for score_raw_pdfs().
    Empty list if the section is absent or unparseable (caller falls back).
    """
    section = re.search(r"### Keyword Groups\n(.*?)(?=\n###|\Z)", dao_handoff, re.DOTALL)
    if not section:
        return []
    groups: list[tuple[list[str], float]] = []
    for line in section.group(1).splitlines():
        m = re.match(r"-\s*(high|medium|low):\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            weight = _WEIGHT_MAP.get(m.group(1).lower(), 0.15)
            terms = [t.strip().lower() for t in m.group(2).split(",") if t.strip()]
            if terms:
                groups.append((terms, weight))
    return groups


# ── Helpers ───────────────────────────────────────────────────────────────────

def _year_from_name(path: Path) -> int | None:
    m = _YEAR_RE.search(path.stem)
    return int(m.group(1) + m.group(2)) if m else None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na * nb > 0 else 0.0


def _embed(text: str, api_key: str) -> list[float]:
    import requests
    try:
        resp = requests.post(
            "https://api.mistral.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": "mistral-embed", "input": text[:4096]},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except Exception as e:
        print(f"  [scorer] embed failed: {e}")
        return []


def _dynamic_keywords(query: str, dao_handoff: str) -> list[str]:
    """Extract high-frequency content words from query + Dao gap text."""
    _STOP = {
        "what", "which", "that", "this", "with", "from", "have", "been",
        "they", "their", "will", "into", "also", "both", "using", "used",
        "best", "show", "shows", "found", "study", "paper", "papers",
        "data", "model", "models", "method", "methods", "result", "results",
        "work", "works", "approach", "provide", "based", "between", "compare",
        "literature", "interest", "know", "want", "need", "does",
    }
    text = (query + " " + dao_handoff[:2000]).lower()
    tokens = re.findall(r"\b[a-z][a-z0-9\-]{3,}\b", text)
    freq: dict[str, int] = {}
    for t in tokens:
        if t not in _STOP:
            freq[t] = freq.get(t, 0) + 1
    return [w for w, c in sorted(freq.items(), key=lambda x: -x[1])
            if c >= 2][:20]


# ── Public API ────────────────────────────────────────────────────────────────

def score_raw_pdfs(
    query: str,
    dao_handoff: str,
    wiki_dir: Path,
    raw_dir: Path,
    top_n: int = 30,
    min_score: float = 0.15,
    api_key: str | None = None,
    query_groups: list[tuple[list[str], float]] | None = None,
) -> list[tuple[Path, float, str]]:
    """Score PDFs in raw_dir for relevance to query.

    Returns list of (pdf_path, score, reason_string) sorted descending,
    capped at top_n, filtered to min_score.

    Scoring layers:
      1. semantic_sim  — cosine vs query embedding (needs semantic index)
      2. topic_bonus   — keyword group matches (query_groups from Dao, else _DOMAIN_GROUPS)
      3. recency_bonus — year from filename
    """
    if not raw_dir.exists():
        return []

    # ── Load wiki metadata (.vectors.json) ────────────────────────────────────
    meta: dict = {}
    vectors_path = wiki_dir / ".vectors.json"
    if vectors_path.exists():
        try:
            meta = json.loads(vectors_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Load semantic index (.vectors-semantic.json) ──────────────────────────
    sem_index: dict = {}
    sem_path = wiki_dir / ".vectors-semantic.json"
    if sem_path.exists():
        try:
            sem_index = json.loads(sem_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Embed query once if semantic index + API key available ────────────────
    q_vec: list[float] = []
    if sem_index and api_key:
        print("  [scorer] Embedding query for semantic similarity...")
        q_vec = _embed(query, api_key)
        time.sleep(0.5)  # rate-limit courtesy pause

    # ── Build topic groups ────────────────────────────────────────────────────
    # Prefer Dao's query-specific groups; fall back to hard-coded domain groups.
    if query_groups:
        base_groups = query_groups
        print(f"  [scorer] Using {len(base_groups)} query-specific keyword groups from Dao.")
    else:
        base_groups = _DOMAIN_GROUPS.copy()
        print("  [scorer] No Dao keyword groups found — using fallback domain groups.")

    dynamic_kws = _dynamic_keywords(query, dao_handoff)
    topic_groups = base_groups
    if dynamic_kws:
        topic_groups = base_groups + [(dynamic_kws, 0.10)]

    # ── Score every PDF ───────────────────────────────────────────────────────
    results: list[tuple[Path, float, str]] = []

    for pdf in sorted(raw_dir.glob("*.pdf")):
        stem = pdf.stem.lower()
        reasons: list[str] = []
        score = 0.0

        # 1. Semantic similarity
        if q_vec and stem in sem_index:
            d_vec = sem_index[stem].get("embedding", sem_index[stem].get("vec", []))
            if d_vec:
                sim = _cosine(q_vec, d_vec)
                score += sim
                reasons.append(f"sem={sim:.2f}")

        # 2. Topic bonus — search filename + wiki metadata
        page_meta = meta.get(stem, {})
        search_text = " ".join([
            stem,
            page_meta.get("title", ""),
            page_meta.get("tags", ""),
            page_meta.get("keywords", ""),
        ]).lower()

        topic_bonus = 0.0
        hit_groups: list[str] = []
        for keywords, weight in topic_groups:
            if any(kw in search_text for kw in keywords):
                topic_bonus += weight
                hit_groups.append(keywords[0].strip())

        if topic_bonus > 0:
            score += topic_bonus
            reasons.append(f"topic={topic_bonus:.2f}[{','.join(hit_groups[:3])}]")

        # 3. Recency bonus
        year = _year_from_name(pdf)
        recency = 0.0
        if year:
            if year >= 2022:
                recency = 0.15
            elif year >= 2020:
                recency = 0.10
            elif year >= 2018:
                recency = 0.05
        if recency:
            score += recency
            reasons.append(f"year={year}")

        score = round(score, 3)
        if score >= min_score:
            results.append((pdf, score, " | ".join(reasons) or "no signal"))

    results.sort(key=lambda x: -x[1])
    return results[:top_n]
