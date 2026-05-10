# NotebookLM-Wiki Framework

> A multi-agent research intelligence pipeline for Materials Science, ML Potentials, and Generative Models.

---

## What This Is

A two-layer system that turns PK's research questions into structured, compounding knowledge — with minimal token cost and maximum autonomy.

**Layer 1 — Permanent Brain** (`wiki/` + Obsidian)
Compounding knowledge base built from research PDFs. Every paper adds to an interconnected graph of findings, methods, and concepts. Powered by Mistral OCR + embeddings.

**Layer 2 — Exploration** (Google NotebookLM via `notebooklm-py`)
Rich media generation: podcasts, quizzes, slide decks, multi-source chat. Discovers new papers. Feeds discoveries back into Layer 1.

The pipeline connects both layers through a multi-agent system that runs autonomously — interrupting PK at exactly 3 checkpoints.

---

## The Pipeline

```
PK: drops a research question
        │
      [Dao]          Scans KB index, identifies gap, proposes sources
        │
   ── CP1 ──         PK approves source list
        │
    [Builder]        Creates NotebookLM notebook, loads sources
        │
    [Cherry]         Shapes questions, queries NotebookLM, blind-spot sweep
        │
      [Nam]          Synthesises Q&A → research doc + 5 strategic directions
        │
   ── CP2 ──         PK picks which directions to pursue
        │
  [Som ∥ Manao]      Critic + Fact audit in parallel
        │
      [Mod]          Extracts atomic insights, writes to KB
        │
   ── CP3 ──         PK picks output format
        │
    [Nanny]          Writes report / slides / Obsidian update
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
| **CP3** | Mod | Atomic insights preview + KB diff | Pick output format + optional instructions |

Between checkpoints the pipeline runs unattended. Som and Manao run in parallel via threading. On a `REVISE` verdict, Nam retries silently (max 2 attempts). On the second failure PK gets a soft prompt: retry / proceed anyway / abort.

---

## Agent Roles

| Agent | Role | Output |
|-------|------|--------|
| **Dao** | Reads KB index, identifies knowledge gap, proposes sources | `handoff_dao.md` |
| **Builder** | Creates NotebookLM notebook, loads sources via CLI | `handoff_builder.md` |
| **Cherry** | Generates targeted questions, runs NLM Q&A + blind-spot sweep | `handoff_cherry.md` |
| **Nam** | Synthesises Q&A into research doc + 5 strategic directions | `handoff_nam.md` |
| **Som** | Critiques logic and argument quality (parallel) | `handoff_som.md` |
| **Manao** | Fact-checks claims against Q&A and KB (parallel) | `handoff_manao.md` |
| **Mod** | Extracts atomic insights, classifies Done/Ongoing/Not done, writes KB | `handoff_mod.md` |
| **Nanny** | Writes report, slides, and/or Obsidian update | `output/[run_id]/` |

Full specification: [`AGENTS.md`](AGENTS.md) — Visual diagram: [`pipeline/pipeline_diagram.excalidraw`](pipeline/pipeline_diagram.excalidraw)

---

## Prerequisites

### APIs
- **Anthropic API key** — powers all pipeline agents ([console.anthropic.com](https://console.anthropic.com))
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
| **Ollama (local)** | Free | Unlimited | Slow (CPU) | Good | None — local model | Full privacy, no internet |

Set your choice in `wiki_manager.py`:
```python
LLM_BACKEND = "gemini"      # recommended free option
# LLM_BACKEND = "groq"      # fastest free option
# LLM_BACKEND = "anthropic" # best quality
# LLM_BACKEND = "ollama"    # fully local, no API
```

**Recommended zero-cost stack:** PyMuPDF + Gemini — no credit card, handles most research PDFs well.

### Tools
- Python 3.9+
- [Obsidian](https://obsidian.md) — open `wiki/` as your vault

---

## Installation

```bash
git clone https://github.com/PKKeerati/notebooklm-wiki-framework.git
cd notebooklm-wiki-framework
pip install -r requirements.txt

# For PDF extraction (pick one):
pip install pymupdf          # free, recommended
# pip install mistralai      # if using Mistral OCR
# pip install google-genai   # if using Gemini

# For Gemini or Groq LLM backend:
# pip install google-genai
# pip install groq
```

### Authenticate NotebookLM
```bash
notebooklm login
```
This opens a browser for Google OAuth and saves credentials locally.

### Set environment variables

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

### Ingest papers into the KB (Layer 1 only)

```bash
# Drop PDFs into raw/, then:
python scripts/wiki_manager.py all
```

### Semantic search across your KB

```bash
python scripts/wiki_manager.py query "message passing equivariant representations benchmark"
```

---

## Project Structure

```
notebooklm-wiki-framework/
├── pipeline/
│   ├── orchestrator.py        # Main runner — start/resume/status/reset
│   ├── agents/
│   │   ├── base.py            # BaseAgent: Anthropic client + prompt caching
│   │   ├── dao.py             # Librarian
│   │   ├── builder.py         # Notebook constructor
│   │   ├── cherry.py          # Question shaper + NLM querier
│   │   ├── nam.py             # Research synthesiser
│   │   ├── som.py             # Logic critic
│   │   ├── manao.py           # Fact auditor
│   │   ├── mod.py             # Insight extractor + KB writer
│   │   └── nanny.py           # Output writer
│   ├── handoffs/              # Inter-agent files (gitignored)
│   ├── pipeline_state.json    # Run state (gitignored)
│   └── pipeline_diagram.excalidraw  # Visual pipeline map
├── scripts/
│   ├── wiki_manager.py        # Layer 1: ingest / promote / categorize / query
│   ├── mistral_ocr_client.py  # PDF extraction via Mistral OCR
│   └── synthesize_concepts.py # Cross-source concept synthesis
├── raw/                       # Drop PDFs here (gitignored)
├── log/                       # Intermediate extractions (gitignored)
├── wiki/                      # Knowledge base — open in Obsidian (gitignored)
│   ├── concepts/              # AI-synthesised concept pages
│   ├── assets/                # Extracted figures
│   └── index.md               # Auto-generated vault index
├── output/                    # Pipeline reports and slides (gitignored)
├── AGENTS.md                  # Full agent specification
├── requirements.txt
└── .gitignore
```

---

## Domain Taxonomy

Pre-configured for PK's research domains. Controls how the Obsidian graph clusters.

**Applications**
- ML Potentials — MACE, NequIP, CHGNet, SchNet, ACE, equivariant
- Method Acceleration — DFT, active learning, uncertainty, surrogate
- Generative Models — diffusion, flow matching, VAE, inverse design
- Drug Discovery — protein, ligand, binding affinity, ADMET

**Materials**
- Crystals & Alloys — crystal, alloy, high-entropy, defect, perovskite
- Molecules — molecular, SMILES, conformer, torsion
- 2D Materials — MXene, graphene, monolayer, heterostructure
- Proteins & Biomolecules — protein, peptide, enzyme, residue

To edit: update `self.taxonomy_apps` and `self.taxonomy_materials` in `scripts/wiki_manager.py`.

---

## Token Efficiency

Each agent reads only what it needs — never the full KB:

| Agent | Reads |
|-------|-------|
| Dao | `wiki/index.md` + vector titles only |
| Cherry | Handoffs + NotebookLM answers (sources stay in NLM) |
| Som / Manao | Nam's handoff + Cherry's Q&A |
| Mod | Approved handoffs + targeted wiki pages |

All agent system prompts use **prompt caching** (`cache_control: ephemeral`). Repeated runs on the same topic cost significantly less.

---

## Typical Workflow

**Daily:** Drop new papers in `raw/`, run `wiki_manager.py all` → Obsidian wiki grows.

**Weekly deep-dive:**
```bash
python pipeline/orchestrator.py start "Compare MACE vs NequIP vs CHGNet on MD accuracy"
# → CP1: approve sources
# → CP2: pick directions (e.g. "1,3")
# → CP3: pick output (e.g. "D: report + obsidian")
```

**Stay current:**
```bash
notebooklm source add-research "equivariant neural network potentials 2025" --mode deep
# → review discovered papers → drop PDFs in raw/ → ingest
```

---

## Built On

- [llm-wiki-framework](https://github.com/Lovorz/llm-wiki-framework) — Mistral OCR + Obsidian KB engine
- [notebooklm-py](https://github.com/pchaganti/notebooklm-py) — programmatic Google NotebookLM client
- [Anthropic Claude](https://anthropic.com) — agent intelligence (claude-sonnet-4-6)
- [Mistral AI](https://mistral.ai) — OCR and semantic embeddings

---

*"The researcher's job is not to read papers. It is to build understanding."*
