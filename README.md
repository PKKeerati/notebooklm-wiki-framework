# NotebookLM-Wiki Framework

> A two-layer research intelligence system for Materials Science, Machine Learning Potentials, and Generative Models.

---

## The Problem

Modern computational materials science research moves fast. A single week on arXiv can produce 20 relevant papers across ML potentials, generative models, and method development. The tools researchers typically use fall into two failure modes:

- **Chat-based LLMs** (ChatGPT, Claude): Smart, but stateless. Every session starts from zero. You explain the same background every time.
- **Google NotebookLM**: Great for exploring a specific set of papers, but knowledge doesn't compound. Notebooks are isolated. Nothing you learn in one session enriches the next.

Neither tool builds toward anything permanent. You are always renting knowledge, never owning it.

---

## The Solution: Two-Layer Research Intelligence

This framework combines two open-source tools into a single, coherent research OS:

```
Layer 1 — Permanent Brain (llm-wiki-framework)
    Compounding knowledge base · LaTeX rendering · Obsidian graph view
    Semantic search · Domain taxonomy · Local & private

Layer 2 — Exploration & Consumption (notebooklm-py)
    Podcast generation · Quiz/flashcards · Multi-source chat
    Web research agent · Slide deck generation · Mind maps
```

**Layer 1 is your long-term investment.** Every paper you read gets ingested, structured, and linked to existing knowledge. After 100 papers on ML potentials, you have a rich, searchable graph of architectures, benchmarks, and findings — not 100 isolated PDFs.

**Layer 2 is your short-term accelerator.** When you need to deep-dive a topic fast, compare three competing methods, or turn a dense paper into a podcast for your commute — NotebookLM handles it. Then the best insights flow back into Layer 1.

---

## Target Research Domains

This framework is pre-configured for:

| Domain | Examples |
|--------|---------|
| **ML Interatomic Potentials** | MACE, NequIP, CHGNet, SchNet, PaiNN, ACE, ALIGNN |
| **Method Acceleration** | Active learning, uncertainty quantification, distillation, surrogate models |
| **Generative Models for Materials** | Crystal diffusion, flow matching, inverse design, CDVAE, DiffCSP |
| **Drug Discovery** | Molecular generation, protein-ligand, binding affinity, ADMET |
| **Ab initio Methods** | DFT, VASP, CP2K, quantum chemistry, basis sets |
| **Materials Classes** | Crystals & alloys, 2D materials, molecules, proteins, high-entropy alloys |

---

## Architecture

```
                         ┌─────────────────────────────────┐
                         │        Your Research Inbox       │
                         │   (arXiv · journals · PDFs)      │
                         └────────────────┬────────────────┘
                                          │
                          ┌───────────────▼───────────────┐
                          │         raw/  (drop zone)      │
                          └───────────────┬───────────────┘
                                          │
               ┌──────────────────────────▼──────────────────────────┐
               │               LAYER 1 — Permanent Brain              │
               │                  (llm-wiki-framework)                │
               │                                                       │
               │  [Ingest] Mistral OCR → log/                         │
               │  [Promote] Type-aware structuring → wiki/             │
               │  [Categorize] Domain taxonomy → Obsidian graph        │
               │  [Index] Semantic embeddings → vector search          │
               └──────────┬──────────────────────┬───────────────────┘
                          │                       │
               Permanent  │              On demand │ (topic clusters)
               knowledge  │                       │
                          │          ┌────────────▼────────────────┐
                          │          │   LAYER 2 — Exploration      │
                          │          │      (notebooklm-py)         │
                          │          │                              │
                          │          │  Podcast · Quiz · Chat       │
                          │          │  Slides · Mind map           │
                          │          │  Web research agent          │
                          │          └────────────┬────────────────┘
                          │                       │
                          │          New papers discovered
                          │                       │
                          └───────────────────────┘
                               (loop back to raw/)
```

---

## Workflow

### Daily: Ingest new papers

```bash
# Drop PDFs into raw/, then:
python scripts/wiki_manager.py all
```

Every paper is OCR'd, structured with key findings and methodology extracted, wrapped in LaTeX, and linked into your Obsidian graph. Chemical formulas, energies, and units render perfectly.

### Weekly: Topic deep-dive

```bash
# Find new papers on a topic
notebooklm source add-research "equivariant neural network potentials 2025" --mode deep

# Load a cluster of related papers → listen as podcast
notebooklm generate audio --wait

# Generate a quiz to test understanding
notebooklm generate quiz --wait
notebooklm download quiz --format markdown
```

### Anytime: Search your brain

```bash
# Semantic search across your entire library
python scripts/wiki_manager.py query "message passing equivariant representations benchmark"
```

### Research comparison: Multi-source chat

```bash
# Load MACE, NequIP, CHGNet papers into one notebook
notebooklm source add mace_paper.pdf nequip_paper.pdf chgnet_paper.pdf

# Ask structured questions
notebooklm ask "Compare the architectural choices, training data requirements, and MD accuracy of each potential"
```

---

## Key Features

### From llm-wiki-framework
- **High-fidelity OCR** — Mistral OCR handles multi-column papers, tables, figures
- **Scientific LaTeX wrapping** — Auto-detects formulas (`E_f`, `eV/atom`, `F = -∇E`) and renders them in Obsidian
- **Type-aware extraction** — Detects research article vs. review vs. thesis, adjusts structure accordingly
- **Compounding knowledge** — New papers automatically enrich existing concept pages (e.g., every MLP paper adds evidence to your `[[Equivariant Networks]]` concept page)
- **Obsidian graph view** — Your literature visually clusters into ML Potentials, Generative Models, Methods hubs
- **Semantic vector search** — Query your library with natural language
- **Local & private** — Nothing leaves your machine

### From notebooklm-py
- **Podcast generation** — Turn a 30-page methods paper into a 15-minute audio overview
- **Quiz & flashcards** — Exportable as JSON/Markdown for Anki or self-study
- **Multi-source chat** — Ask questions spanning multiple papers simultaneously
- **Slide deck generation** — Instant presentation outline from source material
- **Mind map export** — Visual architecture comparison as JSON
- **Web research agent** — Fast (1–2 min) or deep (5–10 min) literature discovery from within the tool
- **Programmatic control** — Full Python API for scripting and automation

---

## Domain Taxonomy (Pre-configured)

The Obsidian graph view clusters automatically using this taxonomy:

### Applications
| Hub | Keywords |
|-----|---------|
| ML Potentials Hub | MACE, NequIP, SchNet, PaiNN, ACE, force field, equivariant, interatomic potential |
| Method Acceleration Hub | DFT, active learning, uncertainty, distillation, surrogate, fine-tuning |
| Generative Models Hub | diffusion, flow matching, VAE, GAN, denoising, crystal generation, inverse design |
| Drug Discovery Hub | protein, ligand, binding affinity, docking, ADMET, drug-like, scaffold |

### Materials
| Hub | Keywords |
|-----|---------|
| Crystals & Alloys Hub | crystal, alloy, high entropy, defect, grain boundary, perovskite |
| Molecules Hub | molecular, organic, SMILES, conformer, torsion, drug-like |
| 2D Materials Hub | MXene, graphene, monolayer, heterostructure, TMD |
| Proteins & Biomolecules Hub | protein, peptide, enzyme, residue, secondary structure |

---

## Why Not Just Use One?

| Scenario | Best tool |
|----------|-----------|
| Reading a paper — build permanent knowledge | Layer 1 (wiki) |
| Preparing a group meeting on a topic | Layer 2 (NotebookLM) |
| Comparing 3 competing architectures | Layer 2 (NotebookLM chat) |
| Searching "what did I read about uncertainty quantification?" | Layer 1 (semantic search) |
| Learning a new subfield fast | Layer 2 (podcast + quiz) |
| Staying current with arXiv | Layer 2 (web research agent) → Layer 1 (ingest discoveries) |
| Long-term concept synthesis across 100 papers | Layer 1 (concept pages) |

They are designed to feed each other. NotebookLM discovers and explores; the wiki accumulates and persists.

---

## Stack

| Component | Technology |
|-----------|-----------|
| OCR & Synthesis | Mistral AI (OCR, Large, Embed) |
| Exploration & Media | Google NotebookLM (via notebooklm-py) |
| Knowledge UI | Obsidian |
| Storage | Local Markdown (portable, version-control friendly) |
| Language | Python 3.10+ |

---

## Planned Structure

```
notebooklm-wiki-framework/
├── README.md                        # This file
├── scripts/
│   ├── wiki_manager.py              # Layer 1 orchestration (customized taxonomy)
│   ├── mistral_ocr_client.py        # PDF extraction
│   ├── synthesize_concepts.py       # Cross-source synthesis
│   └── bridge.py                    # Layer 1 ↔ Layer 2 workflow automation
├── raw/                             # Drop PDFs here (gitignored)
├── log/                             # Intermediate extractions (gitignored)
└── wiki/                            # Your knowledge base (gitignored)
    ├── concepts/                    # AI-synthesized concept pages
    ├── assets/                      # Extracted figures
    └── index.md                     # Auto-generated graph index
```

The key addition over `llm-wiki-framework` is `bridge.py` — a script that automates the handoff between layers: discovering papers via NotebookLM's web research agent and routing them into `raw/` for permanent ingestion.

---

## Roadmap

- [ ] Customized taxonomy for materials science / ML research domains
- [ ] `bridge.py` — automated Layer 1 ↔ Layer 2 handoff
- [ ] arXiv RSS integration — daily paper discovery routed to `raw/`
- [ ] Citation graph extraction — auto-link related papers via `[[wikilinks]]`
- [ ] Benchmark tracking — structured tables comparing model accuracy across datasets (MatBench, MD17, QM9)
- [ ] Obsidian plugin config — pre-configured for LaTeX, graph view, dataview queries

---

## Credits

Built on top of:
- [llm-wiki-framework](https://github.com/Lovorz/llm-wiki-framework) — by Lovorz
- [notebooklm-py](https://github.com/pchaganti/notebooklm-py) — community client for Google NotebookLM

---

*"The researcher's job is not to read papers. It is to build understanding. These tools handle the former so you can focus on the latter."*
