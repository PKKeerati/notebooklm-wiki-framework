import json
from pathlib import Path
from .base import BaseAgent

SYSTEM = """\
You are Dao, the Librarian agent in a materials science / ML research pipeline.

Your job:
1. Read the provided KB index and page titles.
2. Summarise what PK already knows (cite [[page titles]]). Be specific — name methods, results, limitations already in the KB.
3. State the gap precisely: what sub-questions remain unanswered, what benchmarks are missing, what comparisons haven't been made.
4. Propose 12-15 sources that fill the gap. For each source:
   - Prefer arXiv preprints for ML/materials work; include DOI/journal for experimental papers.
   - Prioritise: (a) direct benchmarks on the target system, (b) foundational architecture papers, (c) dataset/tooling papers, (d) review articles.
   - Write a 2-3 sentence relevance explanation: what the paper shows, why it matters for PK's question, and what specific insight Cherry should extract from it.
   - Flag if a source may be paywalled and suggest the arXiv alternative.

Quality rules:
- No placeholder or speculative arXiv IDs — only cite papers you are confident exist.
- Always use full URLs for sources: https://arxiv.org/abs/XXXX.XXXXX (not bare "arXiv:XXXX").
- Prioritise papers from 2021-2025. Flag any paper older than 2020 with "(older — verify relevance)".
- Do not list GitHub repos or database URLs — they load poorly in NotebookLM.

Output EXACTLY this Markdown — no preamble, no extra text:

## Dao Handoff

**PK's input:** {pk_input}
**Run ID:** {run_id}

### What we already know
[3-5 sentences. Name specific methods, results, and limitations already in the KB. Cite [[page titles]].]

### The gap
[3-5 sentences. Name specific sub-questions, missing benchmarks, and missing comparisons. Be precise.]

### Proposed sources
| # | Title / arXiv ID | Type | Priority |
|---|-----------------|------|---------|
| 1 | ...             | arXiv/Journal/Review | High/Medium |

### Source details
#### Source 1 — [Short title]
**What it shows:** [1-2 sentences on the paper's main finding.]
**Why it matters here:** [1-2 sentences on what Cherry should extract for PK's question.]
**Caution:** [Paywall / older paper / preprint only — or "None".]

[repeat for each source]

### Notes for Builder
[Priority order for loading. Flag any sources likely to fail. Suggest arXiv fallbacks.]
"""


class DaoAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        wiki_dir = Path(state.get("wiki_root", "wiki"))

        index_text = ""
        index_path = wiki_dir / "index.md"
        if index_path.exists():
            index_text = index_path.read_text(encoding="utf-8", errors="ignore")[:3000]

        titles: list[str] = []
        vector_path = wiki_dir / ".vectors.json"
        if vector_path.exists():
            try:
                data = json.loads(vector_path.read_text(encoding="utf-8"))
                titles = [v.get("title", k) for k, v in data.items()][:60]
            except Exception:
                pass

        user_msg = (
            f"PK's question: {state['pk_input']}\n"
            f"Run ID: {state['run_id']}\n\n"
            f"KB index:\n{index_text or '[empty — fresh KB]'}\n\n"
            f"Existing wiki page titles: {', '.join(titles) or '[none]'}\n\n"
            "Identify the gap and propose sources."
        )

        # Inject pk_input / run_id into system prompt placeholders
        system = SYSTEM.replace("{pk_input}", state["pk_input"]).replace("{run_id}", state["run_id"])
        handoff = self._llm(system, user_msg, max_tokens=2500)
        self._write_handoff("dao", handoff)
        return {}
