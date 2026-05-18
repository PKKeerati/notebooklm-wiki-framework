# Raw PDF Relevance Scoring — Design Proposal

**Problem:** The pipeline's Builder agent loads sources from Semantic Scholar into NotebookLM, but ignores the local `raw/` knowledge base (405 PDFs). These PDFs are the user's curated research library and often contain the most relevant material. NotebookLM caps at ~50 sources per notebook, so we need a principled way to select the best ~30 from `raw/` to upload alongside the Semantic Scholar sources.

---

## Option 1 — Keyword Scoring on Filenames

Score each PDF filename by counting how many topic keywords it contains.

```python
keywords = ["mg", "mgh2", "hydride", "pci", "isotherm", "mlip",
            "mace", "nequip", "gap", "ace", "gcmc", "monte carlo",
            "phase transition", "interatomic", "hydrogen"]
score = sum(1 for kw in keywords if kw in filename.lower())
```

**Pros:** Zero API calls, instant, no dependencies.  
**Cons:** Filenames are often truncated or uninformative. A paper titled
"Accurate description of hydrogen diffusion" scores 0 on keywords but is
highly relevant. Cannot distinguish method relevance (GCMC vs NPT).

---

## Option 2 — Semantic Search on Wiki Pages

Use the existing `wiki/.vectors-semantic.json` embedding index built by
`wiki_manager.py index-vectors`. Embed the research query once, then rank
wiki pages by cosine similarity. Map pages back to their source PDFs.

```python
q_vec = embed(research_question)            # 1 API call
scores = {stem: cosine(q_vec, page_vec)
          for stem, page_vec in sem_index.items()}
top_pdfs = match_pdfs(sorted(scores)[:top_n])
```

**Pros:** Semantically grounded. Uses full page content not filenames.
Zero extra calls after index is built.  
**Cons:** Requires semantic index to be built first (`index-vectors`).
PDFs not yet ingested into wiki score 0. Index may be stale.

---

## Option 3 — Multi-Signal Scoring Function ✅ IMPLEMENTED

Combines three complementary signals into a single relevance score.
Robust even when the semantic index is absent (graceful degradation).

### Score formula

```
score(pdf) = semantic_sim + topic_bonus + recency_bonus
```

| Signal | Range | Source |
|--------|-------|--------|
| `semantic_sim` | 0–1 | Cosine similarity to query embedding via `.vectors-semantic.json` |
| `topic_bonus` | 0–1.2 | Keyword group matches on filename + wiki metadata |
| `recency_bonus` | 0–0.15 | Year extracted from filename (≥2022: +0.15, ≥2020: +0.10, ≥2018: +0.05) |

### Topic keyword groups (additive)

| Group | Keywords | Bonus |
|-------|----------|-------|
| System — Mg-H | mg, mgh2, magnesium, hydride | +0.30 |
| Measurement | pci, isotherm, pressure-composition, plateau, hysteresis | +0.30 |
| MLIP methods | mlip, mace, nequip, gap, ace, interatomic, neural network potential | +0.30 |
| Simulation | gcmc, grand canonical, muNPT, monte carlo, chemical potential | +0.30 |
| General H₂ | phase transition, hydrogen storage, hydrogen diffusion | +0.20 |
| Dynamic | top tokens from query + Dao handoff (frequency ≥ 2) | +0.15 |

### Degradation behaviour

| State | Behaviour |
|-------|-----------|
| Semantic index exists + API key set | Full scoring (semantic + topic + recency) |
| No semantic index, API key set | Skip semantic; use topic + recency only |
| No API key | Keyword-only (topic + recency) |

### Pipeline integration point

Runs as **Stage 3.5** in `BuilderAgent.run()` — after notebook creation,
before `NLMClient.add_sources()`. Top-N scored PDFs are merged with the
URL-matched PDFs and uploaded together. Scored results are surfaced in
`handoff_builder.md` so Cherry knows what raw content is available.

---

## Option 4 — LLM Judge

Send each paper's title + abstract (from wiki page) to the LLM with the
research question. Ask it to score 0–10 and justify in one sentence.

```python
prompt = f"""
Research question: {question}
Paper: {title}
Abstract: {abstract[:500]}

Score this paper 0-10 for relevance. Reply: <score>: <one sentence reason>
"""
```

**Pros:** Captures nuance missed by keywords (e.g. method transfer from
water systems to Mg-H). Can reason about indirect relevance.  
**Cons:** 52 API calls per run (~2 min, non-trivial cost). Scores are
subjective and may vary between runs. Adds latency to an already-long
pipeline step.

**Recommended use:** Run Option 4 as a one-off audit to validate and
calibrate Option 3's keyword groups, not as a per-run component.

---

## Chosen Implementation: Option 3

See `pipeline/agents/raw_pdf_scorer.py` for the implementation.
Baked into `BuilderAgent` Stage 3.5 in `pipeline/agents/builder.py`.

### Parameters (configurable via state dict)

| Key | Default | Description |
|-----|---------|-------------|
| `raw_pdf_top_n` | 30 | Max PDFs to upload from raw/ |
| `raw_pdf_min_score` | 0.15 | Minimum score threshold |
