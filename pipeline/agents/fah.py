from pathlib import Path
from .base import BaseAgent

SYSTEM = """\
You are Fah, the KB Synthesizer in a materials science / ML research pipeline.
Your job: given relevant wiki pages, synthesize what is already known about PK's research question.
You write a compact, accurate handoff that replaces raw index browsing for downstream agents.

Rules:
- Cite pages using [[page-slug|Title]] notation inline.
- Extract only facts present in the provided pages — do not speculate.
- If the KB has no relevant pages, say so explicitly in every section.

Output EXACTLY this Markdown — no preamble, no extra text:

## Fah KB Synthesis

### What we already know
[3–5 sentences synthesizing existing KB knowledge relevant to the question.
Cite [[slug|Title]] inline. If no relevant pages: "(KB has no coverage of this topic yet)"]

### Covered sub-topics
- [[slug|Title]] — one sentence on what this page contributes to the question
[one bullet per relevant page, up to 10; omit section if KB is empty]

### Knowledge gaps
- [specific sub-question, benchmark, or comparison not covered by any KB page]
[3–5 bullets; or "(cannot assess — KB has no relevant pages)" if empty]
"""


class FahAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        pk_input = state["pk_input"]
        wiki_dir = Path(state.get("wiki_root", "wiki"))

        print("  Fah: synthesizing KB context...")

        # Find relevant pages via graph search → keyword fallback
        results = self.graph_search(pk_input, wiki_dir, top_k=10, hops=2)
        if not results:
            results = self.keyword_search(pk_input, wiki_dir, top_k=10)

        if not results:
            synthesis = (
                "## Fah KB Synthesis\n\n"
                "### What we already know\n"
                "(KB has no relevant pages for this question.)\n\n"
                "### Knowledge gaps\n"
                "- Entire topic area is new — no existing KB coverage.\n"
            )
            self._write_handoff("fah", synthesis)
            return {}

        # Read page bodies
        pages_block = ""
        for fname, score in results:
            stem = Path(fname).stem
            body = self.read_wiki_page(stem, wiki_dir, max_chars=2500)
            pages_block += f"\n\n---\n### [[{stem}]]\n{body}"

        user_msg = (
            f"PK's research question: {pk_input}\n\n"
            f"Relevant KB pages:\n{pages_block}"
        )

        synthesis = self._llm(SYSTEM, user_msg, max_tokens=1000)
        self._write_handoff("fah", synthesis)
        return {}
