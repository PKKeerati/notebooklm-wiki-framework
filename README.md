# NotebookLM-Wiki Framework

> A multi-agent research intelligence pipeline for Materials Science, ML Potentials, and Generative Models.

---

## What This Is

A two-layer system that turns PK's research questions into structured, compounding knowledge — with minimal token cost and maximum autonomy.

**Layer 1 — Permanent Brain** (`wiki/` + Obsidian)
Compounding knowledge base built from research PDFs. Every paper adds to an interconnected graph of findings, methods, and concepts. Powered by Mistral OCR + embeddings + structured claims extraction.

**Layer 2 — Exploration** (Google NotebookLM via `notebooklm-py`)
Rich media generation: podcasts, quizzes, slide decks, multi-source chat. Discovers new papers. Feeds discoveries back into Layer 1.

The pipeline connects both layers through a multi-agent system that runs autonomously — interrupting PK at exactly 3 checkpoints.

---

## The Pipeline

```
PK: drops a research question
        │
      [Dao]          Scans KB index + Semantic Scholar, identifies gap, proposes sources
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
  [Som ∥ Manao]      Logic critic + Fact auditor in parallel
        │
      [Mod]          Extracts atomic insights, writes to KB
        │
    [Chompoo]        Verifies Done insights against Semantic Scholar, attaches citations
        │
   ── CP3 ──         PK picks output format
        │
    [Nanny]          Writes report / slides / Obsidian update / Excalidraw / LaTeX
```

**3 checkpoints only.** Everything else runs without interruption.
Som and Manao run in parallel. Revision loops are silent — PK is only notified if both attempts fail.

### Visual diagram

Open [`pipeline/pipeline_diagram.excalidraw`](pipeline/pipeline_diagram.excalidraw) in [Excalidraw](https://excalidraw.com) or the Obsidian Excalidraw plugin. Shows every agent with its role, reads, outputs, token budget, revision loop, and feedback path — plus a token efficiency panel and legend.

---

## Checkpoints in Detail

| # | Triggered after | What PK sees | PK's action |
|---|----------------|-------------|-------------|
| **CP1** | Dao | Gap summary + proposed source list | Approve / edit sources / cancel |
| **CP2** | Nam | Research doc + 5 directions (effort-rated) | Pick 1–N directions, optional note |
| **CP3** | Chompoo | Mod's atomic insights + KB pages updated | Pick output format + optional instructions |

Between checkpoints the pipeline runs unattended. Som and Manao run in parallel via threading. On a `REVISE` verdict, Nam retries silently (max 2 attempts). On the second failure PK gets a soft prompt: retry / proceed anyway / abort.

---

## Agent Roles

| Agent | Role | Output |
|-------|------|--------|
| **Dao** | Reads KB index, Semantic Scholar search, identifies knowledge gap, proposes sources | `handoff_dao.md` |
| **Builder** | Mistral OCR on matched PDFs, auto-promotes to wiki/, loads sources into NotebookLM | `handoff_builder.md` |
| **Cherry** | Generates targeted questions, runs NLM Q&A + blind-spot sweep | `handoff_cherry.md` |
| **Nam** | Synthesises Q&A into research doc + 5 strategic directions | `handoff_nam.md` |
| **Som** | Critiques logic and argument quality (parallel with Manao) | `handoff_som.md` |
| **Manao** | Fact-checks claims against Q&A and KB (parallel with Som) | `handoff_manao.md` |
| **Mod** | Extracts atomic insights, classifies Done/Ongoing/Not done, writes KB | `handoff_mod.md` |
| **Chompoo** | Searches Semantic Scholar for each Done insight; attaches real citations or marks Unverified | `handoff_chompoo.md` |
| **Nanny** | Writes selected output format(s) to `output/[run_id]/` | report / slides / Excalidraw / LaTeX |

Full specification: [`AGENTS.md`](AGENTS.md) — Visual diagram: [`pipeline/pipeline_diagram.excalidraw`](pipeline/pipeline_diagram.excalidraw)

---

## CP3 Output Formats

| Choice | Format | Files written |
|--------|--------|---------------|
| **A** | Report only | `report.md` |
| **B** | Slides | `slides.md` (Marp-compatible) |
| **C** | Obsidian only | Updates `wiki/` pages |
| **D** | Report + Obsidian | `report.md` + wiki update |
| **E** | All formats | All of the above + Excalidraw + LaTeX |
| **F** | Excalidraw diagram | `summary.excalidraw` |
| **G** | Report + Obsidian + Excalidraw | `report.md` + wiki update + `summary.excalidraw` |
| **H** | LaTeX report | `report.tex` (compilable, booktabs style) |

---

## Prerequisites

### APIs
- **Anthropic API key** — default engine for all pipeline agents ([console.anthropic.com](https://console.anthropic.com))
- **Mistral API key** — for Mistral OCR, Mistral wiki LLM, or Mistral pipeline agents ([console.mistral.ai](https://console.mistral.ai))
- **Google account** — for NotebookLM access ([notebooklm.google.com](https://notebooklm.google.com))

### PDF Extraction — pick one

`wiki_manager.py` supports three backends for extracting text from research PDFs:

| Backend | Cost | Free Limit | Quality | Handles Scans? | Extracts Figures? | API Key? | Best For |
|---------|------|------------|---------|----------------|-------------------|----------|----------|
| **PyMuPDF** | Free | Unlimited | Good | No | No | None | Text-based PDFs (most arXiv papers) |
| **Mistral OCR** | ~$1 / 1000 pages | None | Excellent | Yes | Yes | `MISTRAL_API_KEY` | Scanned papers, books, figures |
| **Google Gemini** | Free tier | 1000 pages/day | Very good | Yes | Partial | `GEMINI_API_KEY` | Mixed PDFs without Mistral cost |

Set your choice in `wiki_manager.py`:
```python
PDF_BACKEND = "pymupdf"    # free, no API key needed
# PDF_BACKEND = "mistral"  # best quality, requires MISTRAL_API_KEY
# PDF_BACKEND = "gemini"   # free tier, requires GEMINI_API_KEY
```

### LLM for Wiki Structuring — pick one

The wiki manager uses an LLM to turn raw PDF text into structured Obsidian notes:

| Provider | Cost | Free Limit | Speed | Output Quality | Requires | Best For |
|----------|------|------------|-------|----------------|----------|----------|
| **Gemini 1.5 Flash** | Free tier | 1M tokens/day | Fast | Very good | `GEMINI_API_KEY` | Default free choice |
| **Groq (Llama 3)** | Free tier | 6000 tokens/min | Fastest | Good | `GROQ_API_KEY` | Speed priority |
| **Anthropic Claude** | ~$0.01–0.05 / paper | None | Fast | Best | `ANTHROPIC_API_KEY` | Highest quality notes |
| **Mistral** | ~$0.002 / paper | None | Fast | Very good | `MISTRAL_API_KEY` | High quality, low cost |
| **Ollama (local)** | Free | Unlimited | Slow (CPU) | Good | None — local model | Full privacy, no internet |

Set your choice via env var or in `wiki_manager.py`:
```bash
export LLM_BACKEND=mistral   # or: gemini | groq | anthropic | ollama
export MISTRAL_API_KEY="..."
# Optional: override model (default: mistral-small-latest)
export MISTRAL_MODEL=mistral-large-latest
```
```python
LLM_BACKEND = "gemini"      # recommended free option
# LLM_BACKEND = "groq"      # fastest free option
# LLM_BACKEND = "anthropic" # best quality
# LLM_BACKEND = "mistral"   # high quality, low cost
# LLM_BACKEND = "ollama"    # fully local, no API
```

**Recommended zero-cost stack:** PyMuPDF + Gemini — no credit card, handles most research PDFs well.

### Tools
- **Python 3.11+** — required by `notebooklm-py` (Python 3.9/3.10 will not work)
- [Obsidian](https://obsidian.md) — open `wiki/` as your vault

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/PKKeerati/notebooklm-wiki-framework.git
cd notebooklm-wiki-framework
```

### 2. Install Python 3.11+

**Windows** (if not already installed):
```powershell
winget install Python.Python.3.11
```
Or download from [python.org/downloads](https://www.python.org/downloads/).

Verify: `py -3.11 --version` should print `Python 3.11.x`.

### 3. Create a virtual environment

> **Always use the `.venv`** — bare `python` on Windows may resolve to Python 3.9 which lacks `notebooklm-py` support.

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

All subsequent commands assume the venv is **activated** (or you prefix with `.venv/Scripts/python.exe` / `.venv/bin/python`).

### 4. Install dependencies

```bash
pip install -r requirements.txt

# For PDF extraction (pick one):
pip install pymupdf          # free, recommended
# pip install mistralai      # if using Mistral OCR
# pip install google-genai   # if using Gemini

# For LLM backend (pick one):
# pip install google-genai   # Gemini
# pip install groq            # Groq
# pip install mistralai       # Mistral (also used for OCR)

# For semantic search:
pip install numpy            # required for vector similarity
```

### 5. Install notebooklm-py (not on PyPI)

```bash
pip install https://github.com/teng-lin/notebooklm-py/archive/refs/heads/main.zip
```

### 6. Install Playwright (required for NotebookLM login)

```bash
pip install playwright
python -m playwright install chromium
```

Playwright is used only for the one-time browser-based Google login. It is not needed for subsequent pipeline runs.

### 7. Authenticate NotebookLM

> This must be run in a **real terminal window** — it opens a browser for Google OAuth and cannot be run non-interactively.

```powershell
# Windows
.venv\Scripts\notebooklm.exe login

# macOS / Linux
.venv/bin/notebooklm login
```

Sign in with your Google account. Credentials are saved to `~/.notebooklm/profiles/default/storage_state.json` and persist for approximately one year.

**When do you need to re-login?**

| Trigger | Frequency |
|---|---|
| First setup on a new machine | Once |
| Google session revoked (password change, signing out everywhere, security event) | Rare, unpredictable |
| Auth token naturally expires | ~1 year |
| Normal use | Never — tokens persist automatically |

### 8. Store API keys in .env

Create a `.env` file at the project root (auto-loaded by the orchestrator):

```
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...
GEMINI_API_KEY=...
GROQ_API_KEY=...
```

Or set them per session:

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:MISTRAL_API_KEY   = "..."
```

**macOS / Linux:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export MISTRAL_API_KEY="..."
```

---

## Usage

> All examples below assume the `.venv` is **activated**. If not activated, replace `python` with `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (macOS/Linux).

### Run the pipeline

```bash
# Start a new run
python pipeline/orchestrator.py start "What are the most efficient equivariant ML potentials for high-entropy alloys?"

# Resume if interrupted
python pipeline/orchestrator.py resume

# Check status
python pipeline/orchestrator.py status

# Clear state for a fresh start
python pipeline/orchestrator.py reset
```

Checkpoints pause the pipeline and print `Waiting for your response via 'respond' command.` Use the `respond` subcommand to continue:

```bash
# CP1 — approve source plan
python pipeline/orchestrator.py respond "approve"
# CP1 — approve with additions
python pipeline/orchestrator.py respond "approve but also search for papers on MACE benchmarks"
# CP1 — cancel
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

By default the pipeline uses **Anthropic Claude** (claude-sonnet-4-6). To switch all agents to Mistral:

**Windows (PowerShell):**
```powershell
$env:PIPELINE_LLM_BACKEND = "mistral"
$env:MISTRAL_API_KEY       = "..."
$env:MISTRAL_MODEL         = "mistral-small-latest"   # optional override
python pipeline/orchestrator.py start "..."
```

**macOS / Linux:**
```bash
PIPELINE_LLM_BACKEND=mistral MISTRAL_API_KEY="..." python pipeline/orchestrator.py start "..."
```

### Ingest papers into the KB (Layer 1 only)

```bash
# Drop PDFs into raw/, then ingest any new ones:
python scripts/wiki_manager.py all

# Re-ingest everything (reuse cached extractions, overwrite wiki pages):
python scripts/wiki_manager.py reingest

# Re-ingest from scratch (re-extract PDFs too — slower):
python scripts/wiki_manager.py reingest --fresh

# Ingest a single PDF:
python scripts/wiki_manager.py ingest raw/paper.pdf

# Ingest and extract structured claims (RESULT/METHOD/MECHANISM/TABLE/COMPARISON):
python scripts/wiki_manager.py ingest raw/paper.pdf --claims
```

### Maintain graph connectivity

```bash
# Fix broken/missing tags on all wiki pages:
python scripts/wiki_manager.py fix-tags

# Add [[See Also]] wikilinks between related pages (default top-5):
python scripts/wiki_manager.py link
python scripts/wiki_manager.py link --top 8

# Create category hub pages + bidirectional [[wikilinks]] for hub-and-spoke graph:
python scripts/wiki_manager.py make-hubs

# Rebuild wiki/index.md:
python scripts/wiki_manager.py index
```

**Recommended graph setup after a full reingest:**
```bash
python scripts/wiki_manager.py fix-tags
python scripts/wiki_manager.py link
python scripts/wiki_manager.py make-hubs
```

### Search and query

```bash
# Keyword search across KB:
python scripts/wiki_manager.py query "message passing equivariant representations benchmark"

# Semantic (embedding-based) search — requires MISTRAL_API_KEY + numpy:
python scripts/wiki_manager.py query "message passing equivariant" --semantic

# Build/rebuild the semantic vector index:
python scripts/wiki_manager.py index-vectors
```

### KB quality and export

```bash
# Detect broken wikilinks and orphan pages:
python scripts/wiki_manager.py lint

# Export KB claims to structured formats:
python scripts/wiki_manager.py export "MACE benchmark"              # markdown report
python scripts/wiki_manager.py export "equivariant" --format csv    # CSV
python scripts/wiki_manager.py export "lattice dynamics" --format latex  # LaTeX table

# Crystallise a mission/concept file into a wiki/concepts/ page:
python scripts/wiki_manager.py crystallize output/2026-05-21/research_*.md
```

---

## Token Cost Estimates

Approximate cost per full pipeline run using Anthropic Claude (claude-sonnet-4-6) at standard rates ($3/M input, $15/M output, $0.30/M cached):

| Stage | ~Input tokens | ~Output tokens | Est. cost |
|-------|--------------|----------------|-----------|
| Dao (KB scan + Semantic Scholar) | 4 000 | 800 | $0.024 |
| Builder | minimal (NLM CLI) | — | — |
| Cherry (Q&A generation + sweep) | 3 000 | 1 200 | $0.027 |
| Nam (synthesis) | 5 000 | 2 000 | $0.045 |
| Som + Manao (parallel audit) | 3 000 × 2 | 800 × 2 | $0.042 |
| Mod (insight extraction) | 4 000 | 1 000 | $0.027 |
| Chompoo (literature verification) | 1 500 + Semantic Scholar API (free) | 600 | $0.012 |
| Nanny (output writing) | 3 000–5 000 | 2 000–4 000 | $0.06–0.12 |
| **Total per run** | | | **~$0.23–$0.29** |

Cached system prompts (all agents) reduce repeated-run costs by ~60–70%.
Switching to `PIPELINE_LLM_BACKEND=mistral` with `mistral-small-latest` cuts cost to ~$0.01–0.03 per run.

---

## Project Structure

```
notebooklm-wiki-framework/
├── pipeline/
│   ├── orchestrator.py        # Main runner — start/resume/status/reset
│   ├── agents/
│   │   ├── base.py            # BaseAgent: Anthropic/Mistral client + prompt caching
│   │   ├── dao.py             # Librarian — KB scan + Semantic Scholar
│   │   ├── builder.py         # Mistral OCR + auto-promote + NotebookLM loader
│   │   ├── cherry.py          # Question shaper + NLM querier
│   │   ├── nam.py             # Research synthesiser
│   │   ├── som.py             # Logic critic
│   │   ├── manao.py           # Fact auditor
│   │   ├── mod.py             # Insight extractor + KB writer
│   │   ├── chompoo.py         # CP3 preview formatter
│   │   ├── nanny.py           # Output writer (report/slides/Obsidian/Excalidraw/LaTeX)
│   │   ├── excalidraw_builder.py  # Programmatic Excalidraw JSON generator
│   │   └── utils.py           # Semantic Scholar search helpers
│   ├── handoffs/              # Inter-agent files (gitignored)
│   ├── pipeline_state.json    # Run state (gitignored)
│   └── pipeline_diagram.excalidraw  # Visual pipeline map
├── scripts/
│   ├── wiki_manager.py        # Layer 1: ingest / promote / categorize / query / lint / export
│   ├── mistral_ocr_client.py  # Standalone Mistral OCR client
│   ├── synthesize_concepts.py # Cross-source concept synthesis
│   └── auto_pilot.py          # Batch pipeline runner
├── raw/                       # Drop PDFs here (gitignored)
├── log/                       # Intermediate OCR extractions (gitignored)
├── wiki/                      # Knowledge base — open in Obsidian (gitignored)
│   ├── hub-*.md               # Category hub pages (auto-generated by make-hubs)
│   ├── concepts/              # Crystallised concept pages
│   ├── index.md               # Auto-generated vault index (hidden from graph view)
│   ├── .vectors.json          # Keyword embedding index (gitignored)
│   ├── .vectors-semantic.json # Mistral semantic embedding index (gitignored)
│   ├── .audit-log.md          # Agent write audit trail
│   └── .obsidian/             # Obsidian config — tracked in git
│       └── graph.json         # Graph settings: hub-and-spoke layout, index hidden
├── output/                    # Pipeline reports, slides, Excalidraw, LaTeX (gitignored)
├── AGENTS.md                  # Full agent specification
├── requirements.txt
└── .gitignore
```

---

## Layer 1 — KB Features

### Claims Extraction
When `EXTRACT_CLAIMS=1` or `--claims` flag is set, each ingested paper runs an additional LLM pass that extracts structured claims into the YAML frontmatter:

```yaml
claims:
  - fact: "MACE achieves 1.2 meV/Å MAE on MD17 ethanol"
    confidence: high
    category: RESULT
  - fact: "equivariant message passing scales as O(N·k) with k neighbours"
    confidence: medium
    category: METHOD
```

Categories: `RESULT` · `TABLE` · `METHOD` · `MECHANISM` · `COMPARISON`

These claims are queryable via `export` and used by Mod when writing the KB.

### Semantic Search
Builds a Mistral `mistral-embed` vector index (`wiki/.vectors-semantic.json`) keyed by SHA1 content hash — so re-indexing only processes changed pages. The pipeline's `graph_search` uses this as its primary ranking signal, with a multi-hop wikilink traversal bonus (hop-1: +30% of seed score, hop-2: +15%).

### Audit Trail
Every Mod write and Builder auto-promote is appended to `wiki/.audit-log.md` with timestamp, agent, operation, and details. Enables PK to review what the pipeline added or changed.

### Lint
`wiki_manager.py lint` detects broken `[[wikilinks]]` (target page missing) and orphan pages (no incoming links). Reports counts per page — useful before sharing or publishing the vault.

### Export
`wiki_manager.py export [topic]` collects all claims matching a topic from the KB and renders them as a markdown report, CSV table, or LaTeX table. Useful for assembling evidence for a paper or presentation without re-running the full pipeline.

### Crystallize
`wiki_manager.py crystallize [file]` distils a research mission or concept document into a structured wiki page saved to `wiki/concepts/`. Creates a citable, wikilink-connected entry from freeform notes.

---

## Domain Taxonomy

14 pre-configured domains for PK's research. Controls how the Obsidian graph clusters and which hub pages `make-hubs` creates.

| Domain | Sample keywords |
|--------|----------------|
| **ML Potentials** | MACE, NequIP, CHGNet, ACE, equivariant, interatomic potential |
| **Method Acceleration** | DFT, active learning, uncertainty quantification, ab initio |
| **Generative Models** | diffusion, flow matching, VAE, inverse design |
| **Drug Discovery** | ligand, binding affinity, ADMET |
| **Crystals & Alloys** | crystal, alloy, high-entropy, HEA, defect, BCC, FCC |
| **Molecules** | molecular dynamics, SMILES, conformer, charge transfer |
| **2D Materials** | MXene, graphene, monolayer, heterostructure |
| **Proteins** | peptide, enzyme, residue, AlphaFold |
| **Phonons & Anharmonicity** | phonon, anharmonic, thermal conductivity, lattice dynamics |
| **Perovskites** | perovskite, halide, solar cell, thermoelectric, optoelectronic |
| **Electrochemistry** | battery, ORR, OER, electrocatalyst, metal-air, electrode |
| **Quantum Theory** | Hamiltonian, Wigner, Clebsch-Gordan, wave function, spin |
| **Gaussian Processes** | GP regression, kernel matrix, Bayesian optimisation, covariance |
| **Personal** | booking confirmation, research proposal, tourist visa |

To add or edit domains: update the `TAXONOMY` dict in `scripts/wiki_manager.py`, then re-run `make-hubs`.

---

## Obsidian Graph Setup

The wiki uses a **hub-and-spoke topology** for graph connectivity:

- **Hub pages** (`hub-*.md`) — one per taxonomy domain, created by `make-hubs`. Each links to all papers in that domain.
- **Paper pages** — each has a `## Categories` section with `[[wikilinks]]` back to its hub(s) and a `## See Also` section linking to related papers.
- **`index.md`** — hidden from the graph view via the `-path:"index"` filter in `.obsidian/graph.json`.

To change hub node color in Obsidian: **Graph view → Color groups → Add group → `file:hub-`**.

---

## Token Efficiency

Each agent reads only what it needs — never the full KB:

| Agent | Reads |
|-------|-------|
| Dao | `wiki/index.md` (3 000 chars) + hub pages (800 chars × 6) + vector titles only |
| Builder | Mistral OCR output + cached log/ files |
| Cherry | Builder handoff + NotebookLM answers (sources stay in NLM) |
| Som / Manao | Nam's handoff + Cherry's Q&A |
| Mod | Approved handoffs + targeted wiki pages (wikilink-referenced only) |
| Nanny | Mod + Chompoo handoffs + selected format context |

All agent system prompts use **prompt caching** (`cache_control: ephemeral`). Repeated runs on the same topic cost ~60–70% less.

---

## Typical Workflow

**Daily:** Drop new papers in `raw/`, run `wiki_manager.py all` → Obsidian wiki grows.

**After a batch reingest:**
```bash
python scripts/wiki_manager.py fix-tags       # clean up taxonomy tags
python scripts/wiki_manager.py link           # cross-link related pages
python scripts/wiki_manager.py make-hubs      # rebuild hub-and-spoke graph
python scripts/wiki_manager.py index-vectors  # rebuild semantic search index
```

**Weekly deep-dive:**
```bash
python pipeline/orchestrator.py start "Compare MACE vs NequIP vs CHGNet on MD accuracy"
# → CP1: approve sources (e.g. "approve but also search for MACE-MH benchmarks")
# → CP2: pick directions (e.g. "1,3" or "all")
# → CP3: pick output (e.g. "E" for all formats)
```

**Export evidence for a paper:**
```bash
python scripts/wiki_manager.py export "equivariant message passing" --format latex
```

**Batch run multiple questions:**
```bash
python scripts/auto_pilot.py questions.txt   # runs pipeline for each line
```

**Re-authenticate NotebookLM (if session was revoked):**
```powershell
# Windows — run in a real terminal, not Claude Code
.venv\Scripts\notebooklm.exe login
```

---

## Built On

- [llm-wiki-framework](https://github.com/Lovorz/llm-wiki-framework) — Mistral OCR + Obsidian KB engine
- [notebooklm-py](https://github.com/pchaganti/notebooklm-py) — programmatic Google NotebookLM client
- [Anthropic Claude](https://anthropic.com) — agent intelligence (claude-sonnet-4-6)
- [Mistral AI](https://mistral.ai) — OCR and semantic embeddings

---

*"The researcher's job is not to read papers. It is to build understanding."*
