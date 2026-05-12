import json
import time
from pathlib import Path
from .base import BaseAgent
from .utils import search_semantic_scholar, format_papers_for_llm, paper_url

SYSTEM = """\
You are Dao, the Librarian agent in a materials science / ML research pipeline.

You are given REAL papers retrieved from Semantic Scholar. Your job:
1. Read the KB index and page titles — summarise what PK already knows.
2. State the gap precisely: what sub-questions remain unanswered, what benchmarks are missing.
3. Select the 10-12 most relevant papers from the search results provided.
   - Prioritise: (a) direct benchmarks on the target system, (b) foundational architecture papers,
     (c) dataset/tooling papers, (d) review articles.
   - For each selected paper, write a 2-3 sentence explanation: what it shows, why it matters,
     what specific insight Cherry should extract.
   - Use the exact URL provided in the search results — do not modify or invent URLs.

Quality rules:
- Only select from the provided search results — do not invent or add papers not in the list.
- Each URL must appear only once. Never repeat the same URL in multiple rows.
- Do not list GitHub repos or database URLs.
- Flag paywalled papers and prefer the open-access/arXiv URL when available.

Output EXACTLY this Markdown — no preamble, no extra text:

## Dao Handoff

**PK's input:** {pk_input}
**Run ID:** {run_id}

### What we already know
[3-5 sentences. Name specific methods, results, and limitations already in the KB. Cite [[page titles]].]

### The gap
[3-5 bullet points. Name specific sub-questions, missing benchmarks, and missing comparisons.]

### Proposed sources
| # | URL | Priority |
|---|-----|---------|
| 1 | https://... | High/Medium |

### Source details
#### Source 1 — [Paper title]
**What it shows:** [1-2 sentences on the paper's main finding.]
**Why it matters here:** [1-2 sentences on what Cherry should extract for PK's question.]
**Caution:** [Paywall / older paper / preprint only — or "None".]

[repeat for each source]

### Notes for Builder
[Priority order for loading. Flag any sources likely to fail.]
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

        # Search Semantic Scholar with targeted queries derived from PK's question
        pk_input = state["pk_input"]
        print(f"  Searching Semantic Scholar...")

        # Build 3 queries: specific, broad architecture, broad application
        words = pk_input.lower().split()
        queries = [
            pk_input,                                          # exact question
            " ".join(w for w in words if len(w) > 4)[:80],   # key words only
            "machine learning interatomic potential benchmark",
        ]

        all_papers: dict[str, dict] = {}
        seen_urls: set[str] = set()
        for q in queries:
            results = search_semantic_scholar(q, limit=12)
            for p in results:
                pid = p.get("paperId", "")
                url = paper_url(p)
                if pid and pid not in all_papers and url and url not in seen_urls:
                    all_papers[pid] = p
                    seen_urls.add(url)
            time.sleep(1)

        papers_list = list(all_papers.values())[:20]
        papers_block = format_papers_for_llm(papers_list) if papers_list else "[No search results — KB only]"
        print(f"  Found {len(papers_list)} unique real papers from Semantic Scholar.")

        user_msg = (
            f"PK's question: {pk_input}\n"
            f"Run ID: {state['run_id']}\n\n"
            f"KB index:\n{index_text or '[empty — fresh KB]'}\n\n"
            f"Existing wiki page titles: {', '.join(titles) or '[none]'}\n\n"
            f"Real papers from Semantic Scholar (select from these only):\n{papers_block}\n\n"
            "Identify the gap and select the most relevant sources."
        )

        system = SYSTEM.replace("{pk_input}", pk_input).replace("{run_id}", state["run_id"])
        handoff = self._llm(system, user_msg, max_tokens=2500)
        self._write_handoff("dao", handoff)
        return {}


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
