# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A two-layer research intelligence system for materials science / ML potentials research:

- **Layer 1 — Permanent Brain** (`wiki/` + Obsidian): KB built from research PDFs via `scripts/wiki_manager.py`
- **Layer 2 — Exploration** (`pipeline/`): Multi-agent pipeline using Google NotebookLM as a source reader and Claude agents for synthesis

## Python Environment

This project requires Python 3.11+ (notebooklm-py dependency). Always use the `.venv`:

```bash
# Activate (do this once per terminal session)
.venv\Scripts\activate        # Windows PowerShell / CMD
source .venv/Scripts/activate # Git Bash / WSL

# Or invoke directly without activating
.venv\Scripts\python.exe pipeline/orchestrator.py start "..."
```

Claude Code: **always prefix Python commands with `.venv/Scripts/python.exe`** (or use the activated venv). Never use bare `python` — it resolves to Python 3.9 which lacks notebooklm-py support.

## Running the Pipeline

```bash
# Start a new run
.venv/Scripts/python.exe pipeline/orchestrator.py start "Your research question here"

# Resume after interruption or checkpoint
.venv/Scripts/python.exe pipeline/orchestrator.py resume

# Show current state
.venv/Scripts/python.exe pipeline/orchestrator.py status

# Clear state and handoffs (prompts for confirmation)
.venv/Scripts/python.exe pipeline/orchestrator.py reset
```

## Layer 1 — KB Ingestion (wiki_manager.py)

```bash
# Ingest all new PDFs from raw/
.venv/Scripts/python.exe scripts/wiki_manager.py all

# Ingest one PDF
.venv/Scripts/python.exe scripts/wiki_manager.py ingest raw/paper.pdf

# Semantic search across the KB
.venv/Scripts/python.exe scripts/wiki_manager.py query "equivariant message passing benchmark"

# Rebuild wiki/index.md
.venv/Scripts/python.exe scripts/wiki_manager.py index
```

**Backend config** — set in `scripts/wiki_manager.py` or via env vars:
```bash
export PDF_BACKEND=pymupdf    # pymupdf (free) | gemini | mistral
export LLM_BACKEND=gemini     # gemini | groq | anthropic | ollama | mistral
```

**Required API keys** (depending on backends chosen):
- `ANTHROPIC_API_KEY` — required for pipeline agents unless `PIPELINE_LLM_BACKEND=mistral`
- `MISTRAL_API_KEY` — if `PDF_BACKEND=mistral` or `PIPELINE_LLM_BACKEND=mistral`
- `GEMINI_API_KEY` — if `PDF_BACKEND=gemini` or `LLM_BACKEND=gemini`
- `GROQ_API_KEY` — if `LLM_BACKEND=groq`

**Pipeline LLM backend** — controls which LLM the pipeline agents use:
```bash
export PIPELINE_LLM_BACKEND=anthropic   # default — uses Claude (claude-sonnet-4-6)
export PIPELINE_LLM_BACKEND=mistral     # uses Mistral (MISTRAL_MODEL, default: mistral-small-latest)
export MISTRAL_MODEL=mistral-large-latest  # optional model override
export MISTRAL_SLEEP=2                     # optional inter-call sleep in seconds
```

**NotebookLM auth** (one-time):
```bash
notebooklm login
```
Install `notebooklm-py` from GitHub — it is not on PyPI (see `requirements.txt`).

## Architecture

### Agent Flow (pipeline/)

```
Dao [→ Fah internally] → Builder → Cherry → Nam → [Som ∥ Manao] → Mod → Chompoo → Nanny
```

Fah is called inside `DaoAgent.run()` as its first step — not by the orchestrator. The orchestrator always starts from Dao.

The orchestrator (`pipeline/orchestrator.py`) is a state machine keyed on `state["current_step"]`. It saves state to `pipeline/pipeline_state.json` after every step so runs survive interruption. Som and Manao are always launched in parallel via `threading.Thread`.

**3 interactive checkpoints** (CLI prompts):
| CP | After | PK decides |
|----|-------|------------|
| CP1 | Dao | Approve/edit/cancel source list |
| CP2 | Nam | Pick 1–N research directions |
| CP3 | Chompoo | Pick output format (report / slides / Obsidian / all) |

Between checkpoints the pipeline runs without user input. If Som or Manao returns `REVISE`, Nam retries silently (max 2 attempts), then prompts PK if still failing.

### BaseAgent pattern (pipeline/agents/base.py)

All agents extend `BaseAgent`. The `_llm()` method wraps every Claude call with prompt caching (`cache_control: ephemeral`) on the system prompt — always preserve this when adding or modifying agents.

Agents communicate exclusively through `pipeline/handoffs/handoff_[agent].md` files. Each agent reads only the handoffs it needs — never the full KB. Handoffs are cleared at the start of each new run.

### Inter-agent handoff routing (from AGENTS.md §7)

| Handoff file | Written by | Read by |
|---|---|---|
| `handoff_fah.md` | Fah (inside Dao) | Dao |
| `handoff_dao.md` | Dao | Builder, Cherry, Nam |
| `handoff_builder.md` | Builder | Cherry |
| `handoff_cherry.md` | Cherry | Nam, Som, Manao, Nanny |
| `handoff_nam.md` | Nam | Som, Manao, Mod |
| `handoff_som.md` | Som | Nam (revision), Mod |
| `handoff_manao.md` | Manao | Nam (revision), Mod |
| `handoff_mod.md` | Mod | Nanny |
| `handoff_nanny.md` | Nanny | Nam (PK feedback re-entry) |

### KB write rules (Mod only)

- **Append only** — never overwrite existing KB entries; always date-stamp new facts
- If a new insight contradicts an existing KB entry, log the conflict in `handoff_mod.md` and do NOT write to the KB — leave resolution to PK
- Mod is the only agent with write access to `wiki/`

### Domain taxonomy

Defined in `scripts/wiki_manager.py` as the `TAXONOMY` dict. Controls how Obsidian graph clusters. Edit it there to add or change research domains.

## Key Files

| Path | Purpose |
|---|---|
| `pipeline/orchestrator.py` | State machine + CLI entry point |
| `pipeline/agents/base.py` | `BaseAgent` with `_llm()` (prompt caching) |
| `pipeline/agents/*.py` | One file per agent (Dao, Builder, Cherry, Nam, Som, Manao, Mod, Nanny) |
| `pipeline/pipeline_state.json` | Live run state (gitignored) |
| `pipeline/handoffs/` | Inter-agent communication files (gitignored) |
| `scripts/wiki_manager.py` | Layer 1 KB builder — PDF ingestion, structuring, search |
| `scripts/mistral_ocr_client.py` | Standalone Mistral OCR client |
| `wiki/index.md` | Auto-generated vault index — Dao reads this |
| `wiki/.vectors.json` | Embedding index for semantic search (gitignored) |
| `AGENTS.md` | Full agent specification and schema reference |

## Gitignored at Runtime

`raw/`, `log/`, `wiki/`, `output/`, `pipeline/pipeline_state.json`, `pipeline/handoffs/handoff_*.md` are all gitignored — they hold private research data and runtime state.
