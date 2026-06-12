# NotebookLM-Wiki Framework

> A multi-agent research intelligence pipeline for Materials Science, ML Potentials, and Generative Models.

---

## What This Is

A two-layer system that turns research questions into structured, compounding knowledge — with minimal token cost and maximum autonomy.

| Layer | What it does |
|-------|-------------|
| **Layer 1 — Permanent Brain** (`wiki/` + Obsidian) | KB built from research PDFs. Every paper adds to an interconnected graph of findings, methods, and concepts. |
| **Layer 2 — Exploration** (`pipeline/`) | Multi-agent pipeline: NotebookLM as source reader, Claude agents for synthesis and KB writing. |

---

## Quick Start

```bash
# 1. Clone and create venv (Python 3.11+ required)
git clone https://github.com/PKKeerati/notebooklm-wiki-framework.git
cd notebooklm-wiki-framework
py -3.11 -m venv .venv && .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install pymupdf numpy
pip install https://github.com/teng-lin/notebooklm-py/archive/refs/heads/main.zip
pip install playwright && python -m playwright install chromium

# 3. Store API keys in .env
echo ANTHROPIC_API_KEY=sk-ant-... >> .env
echo GEMINI_API_KEY=...           >> .env   # for wiki LLM + PDF backend

# 4. Authenticate NotebookLM (opens browser — run in a real terminal)
.venv\Scripts\notebooklm.exe login

# 5. Drop PDFs into raw/, ingest them, then run the pipeline
python scripts/wiki_manager.py all
python pipeline/orchestrator.py start "Your research question here"
```

> **Always use `.venv\Scripts\python.exe`** (or activate the venv). Bare `python` may resolve to Python 3.9 which lacks `notebooklm-py` support.

---

## The Pipeline

```
PK: drops a research question
        │
      [Dao]          Scans KB index + Semantic Scholar → identifies gap, proposes sources
        │
   ── CP1 ──         PK approves source list
        │
    [Builder]        Mistral OCR → log/ → wiki/; loads sources into NotebookLM
        │
    [Cherry]         Shapes questions, queries NotebookLM, blind-spot sweep
        │
      [Nam]          Synthesises Q&A → research doc + 5 strategic directions
        │
   ── CP2 ──         PK picks which directions to pursue
        │
  [Som ∥ Manao]      Logic critic + Fact auditor (parallel)
        │
      [Mod]          Extracts atomic insights, writes to KB
        │
    [Chompoo]        Verifies insights against Semantic Scholar, attaches citations
        │
   ── CP3 ──         PK picks output format
        │
    [Nanny]          Writes report / slides / Obsidian update / Excalidraw / LaTeX
```

**3 checkpoints only.** Everything else runs without interruption. Som and Manao run in parallel. Revision loops are silent — PK is only notified if both attempts fail.

### Checkpoints

| # | After | What you see | Your action |
|---|-------|-------------|-------------|
| **CP1** | Dao | Gap summary + proposed source list | Approve / edit / cancel |
| **CP2** | Nam | Research doc + 5 directions (effort-rated) | Pick 1–N, optional note |
| **CP3** | Chompoo | Atomic insights + KB pages updated | Pick output format |

### Agent Roles

| Agent | Role |
|-------|------|
| **Dao** | Reads KB index, Semantic Scholar search, identifies gap, proposes sources |
| **Builder** | Mistral OCR on matched PDFs, auto-promotes to wiki/, loads into NotebookLM |
| **Cherry** | Generates targeted questions, runs NLM Q&A + blind-spot sweep |
| **Nam** | Synthesises Q&A into research doc + 5 strategic directions |
| **Som** | Critiques logic and argument quality (parallel with Manao) |
| **Manao** | Fact-checks claims against Q&A and KB (parallel with Som) |
| **Mod** | Extracts atomic insights, classifies Done/Ongoing/Not done, writes KB |
| **Chompoo** | Searches Semantic Scholar for each Done insight; attaches real citations |
| **Nanny** | Writes selected output format(s) to `output/[run_id]/` |

### CP3 Output Formats

| Choice | Output |
|--------|--------|
| **A** | `report.md` |
| **B** | `slides.md` (Marp-compatible) |
| **C** | Obsidian wiki update only |
| **D** | `report.md` + wiki update |
| **E** | All formats |
| **F** | `summary.excalidraw` diagram |
| **G** | `report.md` + wiki update + Excalidraw |
| **H** | `report.tex` (LaTeX, booktabs style) |

---

## Usage

> All commands below assume the `.venv` is activated. If not, prefix with `.venv\Scripts\python.exe`.

### Pipeline

```bash
# Start a new run
python pipeline/orchestrator.py start "What are the most efficient MLIPs for high-entropy alloys?"

# Resume after interruption
python pipeline/orchestrator.py resume

# Check status
python pipeline/orchestrator.py status

# Clear state for a fresh start
python pipeline/orchestrator.py reset
```

**Responding to checkpoints:**

```bash
# CP1 — approve source list
python pipeline/orchestrator.py respond "approve"
python pipeline/orchestrator.py respond "approve but also search for MACE benchmark papers"
python pipeline/orchestrator.py respond "cancel"

# CP2 — pick directions
python pipeline/orchestrator.py respond "1,3"
python pipeline/orchestrator.py respond "all"
python pipeline/orchestrator.py respond "2: focus on simulation-free approaches"

# CP3 — pick output format
python pipeline/orchestrator.py respond "D"   # Report + Obsidian
python pipeline/orchestrator.py respond "E"   # All formats
python pipeline/orchestrator.py respond "G"   # Report + Obsidian + Excalidraw
```

**Switch all agents to Mistral (cheaper):**

```powershell
$env:PIPELINE_LLM_BACKEND = "mistral"
$env:MISTRAL_API_KEY       = "..."
$env:MISTRAL_MODEL         = "mistral-small-latest"   # optional override
python pipeline/orchestrator.py start "..."
```

### Layer 1 — KB Ingestion

```bash
# Ingest all new PDFs from raw/
python scripts/wiki_manager.py all

# Ingest a single PDF
python scripts/wiki_manager.py ingest raw/paper.pdf

# Ingest with structured claims extraction (extra LLM call)
python scripts/wiki_manager.py ingest raw/paper.pdf --claims

# Re-ingest all (reuse cached extractions)
python scripts/wiki_manager.py reingest

# Re-ingest from scratch (re-extract PDFs too)
python scripts/wiki_manager.py reingest --fresh
```

### Graph Maintenance

```bash
# Fix broken/missing tags
python scripts/wiki_manager.py fix-tags

# Add See Also wikilinks between related pages (default top-5)
python scripts/wiki_manager.py link
python scripts/wiki_manager.py link --top 8

# Create category hub pages + bidirectional wikilinks
python scripts/wiki_manager.py make-hubs

# Rebuild wiki/index.md
python scripts/wiki_manager.py index

# Rebuild semantic vector index (requires MISTRAL_API_KEY + numpy)
python scripts/wiki_manager.py index-vectors

# Repair broken [[wikilinks]] using fuzzy slug matching
python scripts/wiki_manager.py fix-links

# Add Cross-KB Insights to every wiki page
python scripts/wiki_manager.py cross-synthesize
```

**Recommended after a full reingest:**
```bash
python scripts/wiki_manager.py fix-tags && python scripts/wiki_manager.py link && python scripts/wiki_manager.py make-hubs
```

### Search, Query & Export

```bash
# Keyword search
python scripts/wiki_manager.py query "equivariant message passing benchmark"

# Semantic search
python scripts/wiki_manager.py query "equivariant" --semantic

# KB Q&A with citations
python scripts/wiki_manager.py ask "How does MACE compare to NequIP on MD17?"
python scripts/wiki_manager.py ask "..." --save   # saves to wiki/concepts/

# Export KB claims on a topic
python scripts/wiki_manager.py export "equivariant message passing"             # markdown
python scripts/wiki_manager.py export "equivariant" --format csv
python scripts/wiki_manager.py export "lattice dynamics" --format latex

# Lint for broken wikilinks and orphan pages
python scripts/wiki_manager.py lint

# Full KB health check
python scripts/wiki_manager.py health-check
python scripts/wiki_manager.py health-check --structural-only

# Crystallise a concept file into wiki/concepts/
python scripts/wiki_manager.py crystallize output/2026-05-21/research_*.md
```

### Typical Workflows

**Daily — add new papers:**
```bash
# Drop PDFs into raw/, then:
python scripts/wiki_manager.py all
```

**After a batch reingest:**
```bash
python scripts/wiki_manager.py fix-tags
python scripts/wiki_manager.py link
python scripts/wiki_manager.py make-hubs
python scripts/wiki_manager.py index-vectors
```

**Weekly deep-dive:**
```bash
python pipeline/orchestrator.py start "Compare MACE vs NequIP vs CHGNet on MD accuracy"
# → CP1: "approve but also search for MACE-MH benchmarks"
# → CP2: "1,3"
# → CP3: "E"
```

**Export evidence for a paper:**
```bash
python scripts/wiki_manager.py export "equivariant message passing" --format latex
```

**Batch multiple questions:**
```bash
python scripts/auto_pilot.py questions.txt
```

---

## Installation

### Requirements
- **Python 3.11+** — required by `notebooklm-py`
- **Obsidian** — open `wiki/` as your vault
- API keys (see [Configuration](#configuration))

### Steps

**1. Clone**
```bash
git clone https://github.com/PKKeerati/notebooklm-wiki-framework.git
cd notebooklm-wiki-framework
```

**2. Python 3.11+ (Windows)**
```powershell
winget install Python.Python.3.11
# Verify: py -3.11 --version
```

**3. Virtual environment**
```powershell
# Windows
py -3.11 -m venv .venv
.venv\Scripts\activate
```
```bash
# macOS / Linux
python3.11 -m venv .venv
source .venv/bin/activate
```

**4. Dependencies**
```bash
pip install -r requirements.txt
pip install pymupdf        # PDF extraction (free, recommended)
pip install numpy          # semantic search
```

**5. notebooklm-py** (not on PyPI)
```bash
pip install https://github.com/teng-lin/notebooklm-py/archive/refs/heads/main.zip
pip install playwright && python -m playwright install chromium
```

**6. Authenticate NotebookLM** (one-time, opens browser)
```powershell
# Run in a real terminal — not Claude Code
.venv\Scripts\notebooklm.exe login
```

Re-authentication is only needed if your Google session is revoked (~1 year expiry).

**7. API keys — create `.env` at project root**
```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
MISTRAL_API_KEY=...
GROQ_API_KEY=...
```

---

## Configuration

### PDF Extraction backend

Set `PDF_BACKEND` in `scripts/wiki_manager.py` or via env var:

| Backend | Cost | Quality | Handles Scans? | Requires |
|---------|------|---------|----------------|---------|
| **pymupdf** (default) | Free | Good | No | Nothing |
| **gemini** | Free tier (1000 pages/day) | Very good | Yes | `GEMINI_API_KEY` |
| **mistral** | ~$1/1000 pages | Excellent | Yes | `MISTRAL_API_KEY` |

**Recommended zero-cost stack:** `pymupdf` + `gemini`

### Wiki LLM backend

Set `LLM_BACKEND` in `scripts/wiki_manager.py` or via env var:

| Backend | Cost | Speed | Quality | Requires |
|---------|------|-------|---------|---------|
| **gemini** (default) | Free tier | Fast | Very good | `GEMINI_API_KEY` |
| **groq** | Free tier | Fastest | Good | `GROQ_API_KEY` |
| **mistral** | ~$0.002/paper | Fast | Very good | `MISTRAL_API_KEY` |
| **anthropic** | ~$0.01–0.05/paper | Fast | Best | `ANTHROPIC_API_KEY` |
| **ollama** | Free (local) | Slow | Good | Local model |

### Pipeline LLM backend

Controls which LLM the pipeline agents use:

```bash
# Default — Claude (claude-sonnet-4-6)
PIPELINE_LLM_BACKEND=anthropic

# Cheaper alternative — Mistral
PIPELINE_LLM_BACKEND=mistral
MISTRAL_MODEL=mistral-small-latest   # optional override
MISTRAL_SLEEP=2                       # optional inter-call sleep
```

---

## Layer 1 — KB Features

### Claims Extraction
Add `--claims` to any ingest command for a structured claims pass:
```yaml
claims:
  - fact: "MACE achieves 1.2 meV/Å MAE on MD17 ethanol"
    confidence: high
    category: RESULT
```
Categories: `RESULT` · `TABLE` · `METHOD` · `MECHANISM` · `COMPARISON`

### Semantic Search
Builds a Mistral `mistral-embed` vector index keyed by content hash — only changed pages are re-indexed. Uses multi-hop wikilink traversal bonus (hop-1: +30%, hop-2: +15%).

### Cross-KB Insights
`cross-synthesize` adds a `## Cross-KB Insights` section to every page — LLM-generated connections across the full KB. Resumable: already-enriched pages are skipped.

### Audit Trail
Every Mod write and Builder auto-promote is appended to `wiki/.audit-log.md` with timestamp, agent, operation, and details.

### Lint & Fix Links
```bash
python scripts/wiki_manager.py lint        # detect broken links + orphans
python scripts/wiki_manager.py fix-links   # auto-repair broken [[wikilinks]]
```

### Export
Collect claims matching a topic and render as markdown, CSV, or LaTeX — useful for assembling evidence without re-running the pipeline.

### Crystallize
Distil a research mission or concept document into a structured `wiki/concepts/` page with frontmatter, wikilinks, and citations.

---

## Domain Taxonomy

24 pre-configured domains. Controls Obsidian graph clustering and hub pages.

| Domain | Sample keywords |
|--------|----------------|
| **ML Potentials** | MACE, NequIP, CHGNet, ACE, equivariant, interatomic potential |
| **Method Acceleration** | DFT, active learning, uncertainty quantification, ab initio |
| **Generative Models** | diffusion, flow matching, VAE, inverse design |
| **Crystals & Alloys** | crystal, alloy, high-entropy, HEA, defect, BCC, FCC |
| **Molecules** | molecular dynamics, SMILES, conformer, charge transfer |
| **2D Materials** | MXene, graphene, monolayer, heterostructure |
| **Proteins** | peptide, enzyme, residue, AlphaFold |
| **Phonons & Anharmonicity** | phonon, anharmonic, thermal conductivity, lattice dynamics |
| **Perovskites** | perovskite, halide, solar cell, thermoelectric |
| **Electrochemistry** | battery, ORR, OER, electrocatalyst, metal-air, Li-air |
| **Quantum Theory** | Hamiltonian, Wigner, Clebsch-Gordan, wave function |
| **Gaussian Processes** | GP regression, kernel matrix, Bayesian optimisation |
| **Hydrogen Storage Materials** | MgH2, LiBH4, metal hydride, gravimetric capacity |
| **H2 Storage Simulations** | GCMC, Widom insertion, CALPHAD, ReaxFF hydrogen |
| … and more | See `TAXONOMY` dict in `scripts/wiki_manager.py` |

To add or edit domains: update `TAXONOMY` in `scripts/wiki_manager.py`, then re-run `make-hubs`.

---

## Obsidian Graph Setup

Hub-and-spoke topology:
- **Hub pages** (`hub-*.md`) — one per domain, created by `make-hubs`
- **Paper pages** — `## Categories` links to hub(s), `## See Also` links to related papers
- **`index.md`** — hidden from graph via `-path:"index"` filter in `.obsidian/graph.json`

To colour hub nodes: **Graph view → Color groups → Add group → `file:hub-`**

---

## Token Efficiency & Cost

Each agent reads only what it needs — never the full KB:

| Agent | Reads |
|-------|-------|
| Dao | `wiki/index.md` + hub pages + vector titles only |
| Cherry | Builder handoff + NotebookLM answers |
| Som / Manao | Nam's handoff + Cherry's Q&A |
| Mod | Approved handoffs + targeted wiki pages only |
| Nanny | Mod + Chompoo handoffs + selected format context |

All agent system prompts use **prompt caching** (`cache_control: ephemeral`). Repeated runs on the same topic cost ~60–70% less.

**Approximate cost per full pipeline run (Anthropic Claude, standard rates):**

| Stage | Est. cost |
|-------|-----------|
| Dao + Builder + Cherry | ~$0.05 |
| Nam + Som + Manao | ~$0.09 |
| Mod + Chompoo + Nanny | ~$0.09–0.15 |
| **Total** | **~$0.23–0.29** |

Switching to `PIPELINE_LLM_BACKEND=mistral` with `mistral-small-latest` cuts cost to ~**$0.01–0.03** per run.

---

## Project Structure

```
notebooklm-wiki-framework/
├── pipeline/
│   ├── orchestrator.py           # Main runner — start/resume/status/reset
│   ├── agents/
│   │   ├── base.py               # BaseAgent: Anthropic/Mistral client + prompt caching
│   │   ├── dao.py / builder.py / cherry.py / nam.py
│   │   ├── som.py / manao.py / mod.py / chompoo.py / nanny.py
│   │   ├── excalidraw_builder.py # Programmatic Excalidraw JSON generator
│   │   └── utils.py              # Semantic Scholar search helpers
│   ├── handoffs/                 # Inter-agent files (gitignored)
│   ├── pipeline_state.json       # Run state (gitignored)
│   └── pipeline_diagram.excalidraw
├── scripts/
│   ├── wiki_manager.py           # Layer 1: ingest / link / query / lint / export
│   ├── mistral_ocr_client.py     # Standalone Mistral OCR client
│   ├── synthesize_concepts.py    # Cross-source concept synthesis
│   └── auto_pilot.py             # Batch pipeline runner
├── raw/                          # Drop PDFs here (gitignored)
├── log/                          # Intermediate OCR extractions (gitignored)
├── wiki/                         # Knowledge base — open in Obsidian (gitignored)
│   ├── hub-*.md                  # Category hub pages
│   ├── concepts/                 # Crystallised concept pages
│   ├── index.md                  # Auto-generated vault index
│   ├── .audit-log.md             # Agent write audit trail
│   └── .obsidian/                # Obsidian config (tracked in git)
├── output/                       # Pipeline reports, slides, etc. (gitignored)
├── AGENTS.md                     # Full agent specification
└── requirements.txt
```

---

## Built On

- [llm-wiki-framework](https://github.com/Lovorz/llm-wiki-framework) — Mistral OCR + Obsidian KB engine
- [notebooklm-py](https://github.com/pchaganti/notebooklm-py) — programmatic Google NotebookLM client
- [Anthropic Claude](https://anthropic.com) — agent intelligence (claude-sonnet-4-6)
- [Mistral AI](https://mistral.ai) — OCR and semantic embeddings

---

*"The researcher's job is not to read papers. It is to build understanding."*
