import json
from pathlib import Path
from .base import BaseAgent

SYSTEM = """\
You are Dao, the Librarian agent in a materials science / ML research pipeline.

Your job:
1. Read the provided KB index and page titles.
2. Summarise in 2-3 sentences what PK already knows about the topic (cite [[page titles]]).
3. State the gap in 1-2 sentences — what is NOT yet in the KB.
4. Propose up to 10 sources (URLs, arXiv IDs, paper titles, YouTube links) that fill the gap.
   Prefer recent, high-impact sources. Favour arXiv preprints for cutting-edge ML/materials work.

Output EXACTLY this Markdown — no preamble, no extra text:

## Dao Handoff

**PK's input:** {pk_input}
**Run ID:** {run_id}

### What we already know
[2-3 sentences citing [[page titles]] from the KB. If KB is empty, say so.]

### The gap
[1-2 sentences on what is missing.]

### Proposed sources
| # | Title / URL | Type | Relevance reason |
|---|-------------|------|-----------------|
| 1 | ...         | PDF/URL/arXiv/YouTube | ... |

### Notes for Builder
[Any special instructions, e.g. "source 3 may be paywalled — try arXiv version".]
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
        handoff = self._llm(system, user_msg, max_tokens=1200)
        self._write_handoff("dao", handoff)
        return {}
