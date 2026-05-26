import json
import re
import time
from pathlib import Path
from .base import BaseAgent
from .fah import FahAgent
from .utils import search_semantic_scholar, format_papers_for_llm, paper_url

# LLM selects papers by number only — never writes URLs.
# Code maps selections back to real URLs from search results.
SYSTEM = """\
You are Dao, the Librarian agent in a materials science / ML research pipeline.

You are given REAL papers retrieved from Semantic Scholar, numbered [1] to [N],
plus your existing KB (wiki pages and hub pages for domain context).

Your job:
1. Load hub context — note which research domains are active in the KB.
2. Read the KB index — summarise what PK already knows (cite [[page titles]]).
3. State the gap precisely: sub-questions unanswered, benchmarks missing, comparisons not made.
4. Select the 8-12 most relevant papers. For each:
   - Reference by NUMBER ONLY (e.g. [3]) — never copy or modify URLs.
   - State its priority: High / Medium / Low.
   - Write 2 sentences: what it shows, and what Cherry should extract for PK's question.
5. Propose a step-by-step workflow that addresses the gaps using the selected sources.
6. Output keyword groups for scoring local KB PDFs (see format below).

Output EXACTLY this Markdown — no preamble, no extra text:

## Dao Handoff

**PK's input:** {pk_input}
**Run ID:** {run_id}

### What we already know
[3-5 sentences citing [[page titles]] from the KB. Note domain hub coverage.]

### The gap
- [specific sub-question or missing benchmark]
- [repeat 3-5 bullets]

### Selected papers
| Ref | Priority | What it shows | Cherry should extract |
|-----|----------|--------------|----------------------|
| [1] | High | 1 sentence | 1 sentence |

### Notes for Builder
[Priority order. Any cautions about specific sources.]

### Proposed Workflow
1. [Step: tool/method — expected output]
2. ...

### Keyword Groups
[3-6 lines. Each line is one cluster of closely related technical terms relevant to PK's question.
Format: `- {high|medium|low}: term1, term2, term3, ...`
high   = core concepts / model names / material names directly in the question
medium = closely related methods, properties, or experimental techniques
low    = peripheral but plausibly co-cited terms
Example (do NOT copy — generate from the actual question):
- high: mace, nequip, gap, sevennet, machine learning potential, mlip, nnp
- high: mg, mgh2, magnesium hydride, mg-based alloy
- medium: pci, isotherm, desorption, plateau pressure, thermodynamic
- low: hydrogen storage, hydride formation, phase transition
Generate 3-6 groups, 4-10 terms each, covering the vocabulary PK's papers are likely to use.]
"""


class DaoAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        wiki_dir = Path(state.get("wiki_root", "wiki"))
        pk_input = state["pk_input"]

        # Fah: synthesize KB context before gap analysis and source search
        FahAgent(self.client, self.pipeline_dir).run(state)
        fah_synthesis = self._read_handoff("fah")

        # Graph search for relevant KB pages (still used for page-name listing)
        graph_results = self.graph_search(pk_input, wiki_dir, top_k=12, hops=2)
        if graph_results:
            existing_pages = "\n".join(
                f"- {name} (score: {score:.3f})" for name, score in graph_results
            )
        else:
            kw_results = self.keyword_search(pk_input, wiki_dir, top_k=12)
            existing_pages = "\n".join(f"- {name}" for name, _ in kw_results) or "(no relevant pages found)"

        # Also load page titles from vectors index
        titles: list[str] = []
        vector_path = wiki_dir / ".vectors.json"
        if vector_path.exists():
            try:
                data = json.loads(vector_path.read_text(encoding="utf-8"))
                titles = [v.get("title", k) for k, v in data.items()][:60]
            except Exception:
                pass

        # Search Semantic Scholar with 3 targeted queries
        print(f"  Searching Semantic Scholar...")
        words = [w for w in pk_input.lower().split() if len(w) > 4]
        # Third query: drop first word (often a verb) to widen scope
        queries = [
            pk_input,
            " ".join(words[:8]),
            " ".join(words[1:7]) if len(words) > 2 else pk_input,
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
            papers_block = "[No search results — KB only. Do not propose any sources.]"
        else:
            papers_block = format_papers_for_llm(papers_list)

        user_msg = (
            f"PK's question: {pk_input}\n"
            f"Run ID: {state['run_id']}\n\n"
            f"### Synthesized KB Context (from Fah):\n{fah_synthesis}\n\n"
            f"Most relevant KB pages (graph search):\n{existing_pages}\n\n"
            f"Existing wiki page titles: {', '.join(titles) or '[none]'}\n\n"
            f"Papers from Semantic Scholar (reference by number only — [1], [2], ...):\n{papers_block}\n\n"
            "Identify the gap, select papers by number, and propose a workflow."
        )

        system = SYSTEM.replace("{pk_input}", pk_input).replace("{run_id}", state["run_id"])
        llm_output = self._llm(system, user_msg, max_tokens=2500)

        # Extract selected paper numbers and map to real URLs
        selected_refs = list(dict.fromkeys(
            int(m) for m in re.findall(r"\[(\d+)\]", llm_output)
            if 1 <= int(m) <= len(papers_list)
        ))

        if selected_refs:
            rows = "\n".join(
                f"| {ref} | {paper_url(papers_list[ref - 1])} |"
                for ref in selected_refs
            )
        else:
            rows = "| — | No papers selected |"

        source_block = (
            "\n### Verified source URLs (Builder reads this)\n"
            "| # | URL |\n|---|-----|\n"
            + rows
        )

        handoff = llm_output + source_block
        self._write_handoff("dao", handoff)
        self.audit_log(Path(state.get("wiki_root", "wiki")), "Dao", "handoff_written",
                       f"{len(selected_refs)} sources selected for: {pk_input[:60]}")
        return {}
