import json
import re
import time
from pathlib import Path
from .base import BaseAgent
from .utils import search_semantic_scholar, format_papers_for_llm, paper_url, paper_citation

# LLM only selects paper numbers and writes reasoning — never writes URLs.
# Code maps selections back to real URLs from search results.
SYSTEM = """\
You are Dao, the Librarian agent in a materials science / ML research pipeline.

You are given REAL papers retrieved from Semantic Scholar, numbered [1] to [N].
Your job:
1. Read the KB index — summarise what PK already knows (cite [[page titles]]).
2. State the gap precisely: sub-questions unanswered, benchmarks missing, comparisons not made.
3. Select the 8-12 most relevant papers. For each selected paper:
   - Reference it by NUMBER ONLY (e.g. [3]) — never copy or modify URLs.
   - State its priority: High / Medium / Low.
   - Write 2 sentences: what it shows, and what Cherry should extract for PK's question.

Output EXACTLY this Markdown — no preamble, no extra text:

## Dao Handoff

**PK's input:** {pk_input}
**Run ID:** {run_id}

### What we already know
[3-5 sentences citing [[page titles]] from the KB.]

### The gap
- [specific sub-question or missing benchmark]
- [repeat 3-5 bullets]

### Selected papers
| Ref | Priority | What it shows | Cherry should extract |
|-----|----------|--------------|----------------------|
| [1] | High | 1 sentence | 1 sentence |

### Notes for Builder
[Priority order. Any cautions about specific sources.]
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

        # Search Semantic Scholar with 3 targeted queries
        pk_input = state["pk_input"]
        print(f"  Searching Semantic Scholar...")
        words = [w for w in pk_input.lower().split() if len(w) > 4]
        queries = [
            pk_input,
            " ".join(words[:8]),
            "machine learning interatomic potential benchmark",
        ]

        all_papers: dict[str, dict] = {}
        seen_urls: set[str] = set()
        for q in queries:
            for p in search_semantic_scholar(q, limit=12):
                pid = p.get("paperId", "")
                url = paper_url(p)
                if pid and pid not in all_papers and url and url not in seen_urls:
                    all_papers[pid] = p
                    seen_urls.add(url)
            time.sleep(1)

        papers_list = list(all_papers.values())[:20]
        print(f"  Found {len(papers_list)} unique papers.")

        if not papers_list:
            # Fallback: no search results — LLM works from KB only
            papers_block = "[No search results — KB only. Do not propose any sources.]"
        else:
            papers_block = format_papers_for_llm(papers_list)

        user_msg = (
            f"PK's question: {pk_input}\n"
            f"Run ID: {state['run_id']}\n\n"
            f"KB index:\n{index_text or '[empty]'}\n\n"
            f"Existing wiki page titles: {', '.join(titles) or '[none]'}\n\n"
            f"Papers from Semantic Scholar (reference by number only — [1], [2], ...):\n{papers_block}\n\n"
            "Identify the gap and select the most relevant papers by number."
        )

        system = SYSTEM.replace("{pk_input}", pk_input).replace("{run_id}", state["run_id"])
        llm_output = self._llm(system, user_msg, max_tokens=2000)

        # Extract selected paper numbers from LLM output
        # Matches [1], [2], ... in the Selected papers table
        selected_refs = list(dict.fromkeys(
            int(m) for m in re.findall(r"\[(\d+)\]", llm_output)
            if 1 <= int(m) <= len(papers_list)
        ))

        # Build verified source table using real URLs from papers_list
        source_rows = ""
        if selected_refs:
            rows = []
            for ref in selected_refs:
                p = papers_list[ref - 1]
                url = paper_url(p)
                rows.append(f"| {ref} | {url} |")
            source_rows = "\n".join(rows)
        else:
            source_rows = "| — | No papers selected |"

        # Replace the LLM's Selected papers table with a verified URL table
        # and append a machine-readable source list for Builder
        source_block = (
            "\n### Verified source URLs (Builder reads this)\n"
            "| # | URL |\n|---|-----|\n"
            + source_rows
        )

        handoff = llm_output + source_block
        self._write_handoff("dao", handoff)
        return {}
