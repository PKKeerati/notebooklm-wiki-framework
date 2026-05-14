# AGENTS.md — Multi-Agent Research Pipeline Spec

> Design specification for the NotebookLM-Wiki research intelligence pipeline.
> **Status:** Fully implemented — all agents in `pipeline/agents/`, orchestrator in `pipeline/orchestrator.py`.

---

## 1. Overview

This pipeline converts PK's research questions into structured, persistent knowledge — with minimal token cost and maximum autonomy. PK interacts at 3 checkpoints only. Everything else runs without interruption.

**Agents (in order):**
Dao → Builder → Cherry → Nam → [Som ∥ Manao] → Mod → Chompoo → Nanny

**Implemented as:** Claude Code subagents (Agent tool), orchestrated by `pipeline/orchestrator.py`.

---

## 2. Core Design Principles

### Token Efficiency Rules (non-negotiable)
1. **Index before pages** — Agents read `wiki/index.md` and `.vectors.json` first. Full wiki pages are only read when specifically needed.
2. **Compressed handoffs** — Each agent outputs a single `handoff_[agent].md` file (~1 page max). Agents downstream read only this file, not the full conversation.
3. **NotebookLM holds the sources** — Cherry queries NotebookLM instead of re-reading PDFs. Raw text never enters agent context.
4. **Atomic KB entries** — Mod writes short structured facts, not prose. Future reads stay cheap forever.
5. **Narrow tool access** — Each agent is granted access only to files it needs. No agent reads the whole KB.

### Autonomy Rules
- Agents run sequentially unless marked `PARALLEL`.
- Som and Manao always run in parallel.
- Revision loops (Som/Manao → Nam) are silent — PK is not interrupted unless the loop fails twice.
- PK is interrupted at exactly 3 checkpoints.
- If PK's input is a follow-up (not a new idea), entry point is Nam, not Dao.

---

## 3. Pipeline Flow

```
PK: idea / question
        │
        ▼
      [Dao]  ── reads: index.md, vectors.json
        │
   ╔═══ CP1 ════╗  PK approves source plan
        │
      [Builder]  ── builds NotebookLM notebook
        │
      [Cherry]  ── queries NotebookLM, blind-spot sweep
        │
       [Nam]  ── synthesizes, proposes 5 directions
        │
   ╔═══ CP2 ════╗  PK picks directions
        │
   [Som ∥ Manao]  ── parallel critic + fact audit
        │
        ├── Pass ──────────────────────────────┐
        └── Revise → [Nam] retry (silent)       │
              └── 2nd fail → notify PK (soft)  │
                                               ▼
                                            [Mod]  ── extracts atomic insights, writes KB
                                               │
                                         [Chompoo]  ── verifies Done insights via Semantic Scholar
                                               │
                                        ╔═══ CP3 ════╗  PK picks output format
                                               │
                                           [Nanny]  ── writes report/slides/Obsidian
                                               │
                                        PK reviews
                                               │
                              feedback? → back to [Nam] with correction flag
```

---

## 4. The Three Checkpoints

### CP1 — Source Plan Approval
**Triggered by:** Dao completing its gap analysis.
**What PK sees:**
```
CHECKPOINT 1 — Source Plan

What we already know:
  [2-3 sentence summary from KB]

The gap:
  [1-2 sentences on what's missing]

Proposed sources (N total):
  1. [title] — [why relevant]
  2. [title] — [why relevant]
  ...

→ Approve / Edit list / Cancel
```
**PK's actions:** Approve as-is, remove/add sources, or cancel the run.
**On cancel:** Pipeline halts. State saved. Can resume later.

---

### CP2 — Direction Selection
**Triggered by:** Nam completing synthesis.
**What PK sees:**
```
CHECKPOINT 2 — Research Directions

Research summary: [3-4 sentences]

Top 5 directions:
  1. [Direction title] — [1-line description] — Effort: Low/Med/High
  2. ...
  3. ...
  4. ...
  5. ...

→ Pick one or more to pursue (e.g. "1, 3")
→ Or: "all" / "none" / add a note
```
**PK's actions:** Pick 1–N directions. Optionally add a note (e.g. "focus on #2 but skip simulation").
**The note is passed to Som, Manao, and Mod as a constraint.**

---

### CP3 — Output Format + Final Approval
**Triggered by:** Mod completing insight extraction.
**What PK sees:**
```
CHECKPOINT 3 — Ready to Write

Insights extracted: N atomic facts added to KB
Topics updated: [list]

Preview (first 3 insights):
  • [insight 1]
  • [insight 2]
  • [insight 3]

Output format:
  A) Report only (Markdown)
  B) Slides outline (Markdown → PowerPoint-ready)
  C) Obsidian update only
  D) Report + Obsidian
  E) All of the above

→ Pick format. Add any notes for Nanny (optional).
```
**PK's actions:** Pick output format. Add optional instructions (e.g. "keep slides under 10", "focus on limitations").

---

## 5. Agent Specifications

---

### Dao — Librarian

**Role:** Understand what PK already knows, identify the knowledge gap, and propose a source plan.

**Entry condition:** New idea or question from PK.

**Reads:**
- `wiki/index.md` — topic + thesis index
- `wiki/.vectors.json` — for semantic similarity lookup (titles + scores only, not full vectors)
- Relevant wiki pages only if a topic match score > 0.85

**Writes:**
- `pipeline/handoffs/handoff_dao.md`

**Output schema (`handoff_dao.md`):**
```markdown
## Dao Handoff

**PK's input:** [verbatim]
**Run ID:** [timestamp]

### What we already know
[2–3 sentences from KB. Cite [[page titles]].]

### The gap
[1–2 sentences. What is NOT in the KB yet.]

### Proposed sources
| # | Title / URL | Type | Relevance reason |
|---|-------------|------|-----------------|
| 1 | ...         | PDF/URL/YouTube | ... |

### Notes for Builder
[Any special instructions: e.g. "add as URL not PDF", "skip source 3 if paywalled"]
```

**Token budget:** ~2,000 tokens in, ~500 tokens out.

**Constraints:**
- Never read full wiki pages unless similarity > 0.85.
- If the KB already fully answers PK's question (similarity > 0.95, coverage > 80%), flag it: "KB may already answer this — suggest running a query first."
- Propose no more than 10 sources.

---

### Builder — Notebook Constructor

**Role:** Create the NotebookLM notebook and add all approved sources.

**Entry condition:** CP1 approved by PK.

**Reads:**
- `pipeline/handoffs/handoff_dao.md` (approved source list only)

**Actions (via notebooklm-py CLI):**
```bash
notebooklm create "Run: [Run ID]"
notebooklm use [notebook_id]
notebooklm source add [source1] [source2] ...
notebooklm source list --wait  # poll until all COMPLETED
```

**Writes:**
- `pipeline/handoffs/handoff_builder.md`

**Output schema (`handoff_builder.md`):**
```markdown
## Builder Handoff

**Notebook ID:** [id]
**Run ID:** [timestamp]

### Sources loaded
| # | Title | Status | Type |
|---|-------|--------|------|
| 1 | ...   | COMPLETED | PDF |

### Failed sources
[List any that failed + reason. Builder attempted fallback if URL was dead.]

### Notes for Cherry
[e.g. "source 3 timed out, excluded"]
```

**Token budget:** Minimal — mostly CLI calls.

**Constraints:**
- If a source fails twice, exclude it and log it. Do not block the pipeline.
- Wait for all sources to reach COMPLETED or FAILED before proceeding. Timeout: 5 minutes.

---

### Cherry — Question Shaper

**Role:** Turn the gap into precise questions, query NotebookLM, and run a blind-spot sweep.

**Entry condition:** Builder completes successfully.

**Reads:**
- `pipeline/handoffs/handoff_dao.md` (gap description)
- `pipeline/handoffs/handoff_builder.md` (notebook ID + loaded sources)

**Actions (via notebooklm-py CLI):**
```bash
notebooklm use [notebook_id]
notebooklm ask "[question 1]"
notebooklm ask "[question 2]"
...
notebooklm ask "What important aspects of [topic] did the above answers NOT cover?"  # blind-spot sweep
```

**Writes:**
- `pipeline/handoffs/handoff_cherry.md`

**Output schema (`handoff_cherry.md`):**
```markdown
## Cherry Handoff

**Notebook ID:** [id]
**Questions asked:** N

### Idea Card
[3–5 sentences framing what this research run is about]

### Q&A
**Q1:** [question]
**A1:** [NotebookLM answer, compressed to key points]

...

### Blind Spots
[What the sources did NOT cover, per NotebookLM's own assessment]

### Notes for Nam
[e.g. "Source 2 dominated most answers — may need broader sources next run"]
```

**Token budget:** ~1,000 tokens in, ~800 tokens out.

**Constraints:**
- Ask no more than 8 questions.
- Always end with the blind-spot sweep question.
- Compress NotebookLM answers to key points only — never paste full responses.

---

### Nam — Synthesizer

**Role:** Synthesize Cherry's Q&A into a structured research document and propose 5 strategic directions.

**Entry condition:** Cherry completes. (Also re-entry point for feedback from PK after Nanny.)

**Reads:**
- `pipeline/handoffs/handoff_cherry.md`
- `pipeline/handoffs/handoff_dao.md` (gap context)
- On revision: `pipeline/handoffs/handoff_som.md` and/or `pipeline/handoffs/handoff_manao.md` (critique)
- On PK feedback re-entry: `pipeline/handoffs/handoff_nanny.md` + PK's correction note

**Writes:**
- `pipeline/handoffs/handoff_nam.md`

**Output schema (`handoff_nam.md`):**
```markdown
## Nam Handoff

**Revision:** [0 = first run, 1+ = revised]

### Research Summary
[4–6 sentences synthesizing the key findings across all Q&A]

### Knowledge Gaps
- [gap 1]
- [gap 2]
...

### Limitations
- [limitation 1]
- [limitation 2]
...

### Top 5 Strategic Directions
| # | Direction | Description | Effort | Rationale |
|---|-----------|-------------|--------|-----------|
| 1 | ...       | 1 sentence  | Low/Med/High | why this |
| 2 | ...       | ...         | ...    | ...       |
| 3 | ...
| 4 | ...
| 5 | ...

### Revision notes
[If revised: what was changed and why]
```

**Token budget:** ~1,500 tokens in, ~700 tokens out.

**Constraints:**
- Exactly 5 directions — no more, no less.
- Effort rating must be Low / Medium / High — no other values.
- On revision, address every specific point raised by Som/Manao. If a claim can't be supported, remove it rather than hedging.

---

### Som — Critic

**Role:** Evaluate the logical quality and argumentative strength of Nam's synthesis. Run in parallel with Manao.

**Entry condition:** CP2 approved by PK (with selected directions noted).

**Reads:**
- `pipeline/handoffs/handoff_nam.md`
- `pipeline/handoffs/handoff_cherry.md` (source Q&A)
- PK's direction selection + any notes from CP2

**Writes:**
- `pipeline/handoffs/handoff_som.md`

**Output schema (`handoff_som.md`):**
```markdown
## Som Handoff — Critic

**Verdict:** PASS / REVISE

### Critique (if REVISE)
- [Issue 1]: [specific claim or section] — [why it's weak] — [suggested fix]
- [Issue 2]: ...

### Strengths
- [what Nam did well]

### Notes for Mod (if PASS)
- [any caveats Mod should carry into insight extraction]
```

**Token budget:** ~1,200 tokens in, ~400 tokens out.

**Constraints:**
- If verdict is REVISE, every issue must include a specific suggested fix. Vague critiques are not allowed.
- Som does NOT fact-check. That is Manao's job. Som focuses on logic, argument structure, and completeness.
- If PK selected specific directions at CP2, Som focuses critique on those directions only.

---

### Manao — Fact Auditor

**Role:** Verify factual accuracy of Nam's claims against the source Q&A and existing KB. Run in parallel with Som.

**Entry condition:** CP2 approved by PK.

**Reads:**
- `pipeline/handoffs/handoff_nam.md`
- `pipeline/handoffs/handoff_cherry.md` (source Q&A — ground truth)
- Specific wiki pages only if a claim references a known KB topic

**Writes:**
- `pipeline/handoffs/handoff_manao.md`

**Output schema (`handoff_manao.md`):**
```markdown
## Manao Handoff — Fact Audit

**Verdict:** PASS / REVISE

### Flagged Claims (if REVISE)
- [Claim]: "[exact quote from Nam]" — [issue: unsupported / contradicted / overstated] — [evidence from Q&A or KB]

### Confirmed Claims
- [N claims verified against sources]

### Notes for Mod (if PASS)
- [confidence flags: any claims that passed but are weakly supported]
```

**Token budget:** ~1,200 tokens in, ~400 tokens out.

**Constraints:**
- Manao only flags claims that are directly contradicted or entirely unsupported by `handoff_cherry.md` or the KB.
- Do not flag claims that are reasonable inferences from evidence. Only hard factual errors.
- If a claim is weakly supported (not wrong, but thin), note it in "Notes for Mod" rather than issuing a REVISE verdict.

---

### Revision Loop (Som + Manao → Nam)

**Trigger:** Either Som OR Manao returns verdict REVISE.

**Behavior:**
1. Both handoffs are passed to Nam for a revision run (Nam revision counter increments).
2. Nam re-runs silently. No PK notification.
3. Som and Manao re-run on the revised output.
4. If both PASS: continue to Mod.
5. If either returns REVISE again (2nd fail): pipeline pauses and sends PK a soft notification:
   ```
   [Non-blocking notice]
   Som/Manao flagged issues after 2 attempts.
   Issue: [summary]
   Options: A) Let Nam try once more  B) Proceed anyway  C) Abort
   ```
6. PK responds. Pipeline continues per choice.

**Maximum revision attempts:** 3 total before forced stop.

---

### Mod — Insight Extractor

**Role:** Extract atomic insights from Nam's approved synthesis, classify their status, and write to the KB. The only agent with KB write access.

**Entry condition:** Both Som and Manao return PASS.

**Reads:**
- `pipeline/handoffs/handoff_nam.md`
- `pipeline/handoffs/handoff_som.md` (notes for Mod)
- `pipeline/handoffs/handoff_manao.md` (confidence flags)
- `wiki/index.md` (to find which existing pages to update)

**Writes:**
- `pipeline/handoffs/handoff_mod.md` (preview for CP3)
- `wiki/[relevant pages].md` (KB entries — append or create)
- `wiki/concepts/[topic].md` (concept page updates)

**Atomic insight format (written to KB):**
```markdown
### [Insight title]
- **Fact:** [1 sentence, precise]
- **Status:** Done / Ongoing / Not done
- **Est. completion:** [year or "N/A"]
- **Confidence:** High / Medium / Low
- **Source:** [[handoff reference]] | [date]
- **Topic tags:** #[tag1] #[tag2]
```

**Output schema (`handoff_mod.md`):**
```markdown
## Mod Handoff

**Insights extracted:** N
**KB pages updated:** [list]
**KB pages created:** [list]

### Preview (first 5 insights)
[formatted atomic insights]

### Done / Ongoing / Not done summary
- Done: N insights
- Ongoing: N insights  
- Not done: N insights

### Top 5 tactical choices (from PK's selected directions)
| # | Direction | Status | Effort | Why now |
|---|-----------|--------|--------|---------|
| 1 | ...       | ...    | ...    | ...     |
```

**Token budget:** ~1,500 tokens in, ~600 tokens out (plus KB writes).

**Constraints:**
- One insight = one fact. No compound sentences.
- Never overwrite existing KB entries. Append only, with date stamp.
- If a new insight contradicts an existing KB entry, flag it in the handoff but do NOT overwrite. Leave conflict resolution to PK.
- Status classification rules:
  - **Done:** Paper published, method released, result confirmed in literature.
  - **Ongoing:** Active research group, preprint exists, recent conference paper.
  - **Not done:** Proposed, speculated, or identified as a gap with no known active work.

---

### Chompoo — Literature Verifier

**Role:** For every "Done" atomic insight from Mod, search Semantic Scholar to find a real published paper that supports the claim and attach a full citation. Insights that cannot be matched are marked Unverified. "Ongoing" and "Not done" insights pass through unchanged.

**Entry condition:** Mod completes successfully.

**Reads:**
- `pipeline/handoffs/handoff_mod.md`

**Actions:**
- Parses all `#### [Insight title]` blocks from Mod's handoff.
- For each **Done** insight: calls `search_semantic_scholar(query, limit=5)` using keywords extracted from the insight title and fact. Sleeps 1 s between calls to respect rate limits.
- Passes search results + insight to the LLM for citation matching.

**Writes:**
- `pipeline/handoffs/handoff_chompoo.md`

**Output schema (`handoff_chompoo.md`):**
```markdown
## Chompoo Handoff — Literature Verification

**Verified:** N / Done: M

### Verified Insights
#### [Insight title]
- **Fact:** [original fact from Mod]
- **Status:** Done
- **Citation:** Authors et al. (Year). Title. DOI/arXiv URL
- **Match confidence:** High / Medium
- **Notes:** [optional]

### Unverified Insights
#### [Insight title]
- **Fact:** [original fact]
- **Status:** Done
- **Citation:** Unverified — no supporting paper found
- **Search terms used:** [query sent to Semantic Scholar]

### Ongoing / Not Done Insights
#### [Insight title]
- **Fact:** [original fact]
- **Status:** Ongoing / Not done
- **Est. completion:** [year]
- **Confidence:** [original]
```

**Token budget:** ~1,500 tokens in, ~600 tokens out. Semantic Scholar API is free.

**Constraints:**
- Match confidence HIGH = title/abstract clearly supports the claim; MEDIUM = partial match.
- Only mark VERIFIED if confidence is HIGH or MEDIUM. Never invent citations.
- Do not search for or modify Ongoing / Not done insights.
- Report `chompoo_verified` (count of verified insights) and `chompoo_total_done` back to the orchestrator state.

---

### Nanny — Output Writer

**Role:** Produce the final deliverable in PK's chosen format and update Obsidian.

**Entry condition:** CP3 approved by PK with format selection.

**Reads:**
- `pipeline/handoffs/handoff_mod.md`
- `pipeline/handoffs/handoff_chompoo.md` (citations — marks ⚠ Unverified where absent)
- `pipeline/handoffs/handoff_nam.md`
- `pipeline/handoffs/handoff_cherry.md` (for sourcing)
- PK's format choice + notes from CP3

**Writes (depending on format):**
- `output/report_[run_id].md` — if Report selected
- `output/slides_[run_id].md` — if Slides selected (Markdown → PPTX-ready outline)
- `wiki/` updates — if Obsidian selected (index refresh, concept page links)

**Report structure:**
```markdown
# [Topic] — Research Brief
Date: [date] | Run: [run_id]

## Key Findings
## Knowledge Gaps
## Limitations
## Recommended Next Steps (Top 5)
## Atomic Insights (table)
## Sources
```

**Slides structure (one section = one slide):**
```markdown
# [Topic] — [Date]
---
## Slide 1: What We Know
## Slide 2: The Gap
## Slide 3: Key Findings (3 bullets max per slide)
## Slide 4–6: Top Directions
## Slide 7: Recommended Next Steps
## Slide 8: Open Questions
```

**Token budget:** ~1,200 tokens in, variable output.

**Constraints:**
- Slides: maximum 10 slides, 3 bullets per slide.
- Report: maximum 1,500 words.
- All claims must be traceable to `handoff_cherry.md` or existing KB entries. No new synthesis.
- Nanny does not interpret. It formats what Mod and Nam already produced.

---

## 6. Pipeline State Schema

File: `pipeline/pipeline_state.json`

```json
{
  "run_id": "2026-05-09T14:32:00",
  "pk_input": "What are the most efficient ML potential architectures for high-entropy alloys?",
  "status": "awaiting_cp2",
  "current_step": "nam_complete",
  "pk_direction_selection": null,
  "revision_count": 0,
  "checkpoint_history": {
    "cp1": { "presented": true, "approved": true, "edits": null },
    "cp2": { "presented": true, "approved": false, "edits": null },
    "cp3": { "presented": false, "approved": false, "edits": null }
  },
  "completed_agents": ["dao", "builder", "cherry", "nam"],
  "failed_sources": [],
  "notebook_id": "abc123",
  "output_format": null
}
```

**Status values:** `running` | `awaiting_cp1` | `awaiting_cp2` | `awaiting_cp3` | `awaiting_revision_decision` | `complete` | `cancelled` | `error`

---

## 7. Handoff File Index

All files live in `pipeline/handoffs/`. Cleared at the start of each new run.

| File | Written by | Read by |
|------|-----------|---------|
| `handoff_dao.md` | Dao | Builder, Cherry (gap only), Nam |
| `handoff_builder.md` | Builder | Cherry |
| `handoff_cherry.md` | Cherry | Nam, Som, Manao, Nanny |
| `handoff_nam.md` | Nam | Som, Manao, Mod |
| `handoff_som.md` | Som | Nam (revision), Mod |
| `handoff_manao.md` | Manao | Nam (revision), Mod |
| `handoff_mod.md` | Mod | Chompoo, Nanny |
| `handoff_chompoo.md` | Chompoo | Nanny |
| `handoff_nanny.md` | Nanny | Nam (PK feedback re-entry) |

---

## 8. Entry Points

| Scenario | Entry agent | Skip |
|----------|------------|------|
| New idea / question | Dao | — |
| Follow-up to existing run | Nam | Dao, Builder, Cherry |
| PK feedback after Nanny | Nam | All except Nam → Mod → Nanny |
| Re-run same question with new sources | Builder | Dao |
| Just update Obsidian | Nanny | All |

Entry point is set in `pipeline_state.json` → `current_step` before the orchestrator runs.

---

## 9. KB Write Rules (Mod only)

1. **Append, never overwrite.** Each new insight gets a date stamp.
2. **Conflict flagging.** If a new fact contradicts an existing KB entry, write it to `pipeline/handoffs/handoff_mod.md` under "Conflicts" — do not write it to the KB until PK resolves it.
3. **Topic routing.** Insights are written to the most specific matching wiki page. If no page exists, Mod creates one with a stub header.
4. **Concept page updates.** If an insight matches an existing `wiki/concepts/` page, Mod appends a "Compounding Evidence" block (same pattern as llm-wiki-framework).
5. **Index refresh.** After all writes, Mod appends new page titles to `wiki/index.md`.

---

## 10. Orchestrator Responsibilities

File: `pipeline/orchestrator.py`

- Reads `pipeline_state.json` on start — resumes from last saved state if interrupted.
- Launches each agent as a Claude Code subagent via the Agent tool.
- Launches Som and Manao with `run_in_background=True`, then waits for both.
- Presents checkpoints via `AskUserQuestion`.
- Writes `pipeline_state.json` after each step.
- Handles revision loop counter and soft notification on 2nd fail.
- Routes PK feedback back to Nam with a `correction_flag: true` field.
- Cleans `pipeline/handoffs/` at the start of each new run (not resume).

---

## 11. Agent Tool Access Summary

| Agent | Read | Write | CLI tools |
|-------|------|-------|-----------|
| Dao | `wiki/index.md`, `wiki/.vectors.json`, selective wiki pages | `handoff_dao.md` | `wiki_manager.py query` |
| Builder | `handoff_dao.md` | `handoff_builder.md` | `notebooklm` (create, source add) |
| Cherry | `handoff_dao.md`, `handoff_builder.md` | `handoff_cherry.md` | `notebooklm` (ask) |
| Nam | `handoff_dao.md`, `handoff_cherry.md`, `handoff_som.md`*, `handoff_manao.md`*, `handoff_nanny.md`* | `handoff_nam.md` | — |
| Som | `handoff_nam.md`, `handoff_cherry.md` | `handoff_som.md` | — |
| Manao | `handoff_nam.md`, `handoff_cherry.md`, selective wiki pages | `handoff_manao.md` | — |
| Mod | `handoff_nam.md`, `handoff_som.md`, `handoff_manao.md`, `wiki/index.md`, selective wiki pages | `handoff_mod.md`, `wiki/**` | `wiki_manager.py categorize` |
| Chompoo | `handoff_mod.md` | `handoff_chompoo.md` | Semantic Scholar API (via `utils.py`) |
| Nanny | `handoff_mod.md`, `handoff_chompoo.md`, `handoff_nam.md`, `handoff_cherry.md` | `output/**`, `wiki/index.md` | — |

*On revision or re-entry only.*

---

## 12. Naming & Language Convention

All agents are named after people (Thai names). When referring to them in code comments or logs, use the name only — no role suffix. E.g. `"Dao complete"` not `"Librarian Dao complete"`.

Run IDs use ISO 8601 format: `YYYY-MM-DDTHH:MM:SS`.

---

*Spec version: 0.2 — Fully implemented. All agents in `pipeline/agents/`, orchestrator in `pipeline/orchestrator.py`.*
