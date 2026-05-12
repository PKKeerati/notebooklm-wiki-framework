import re
from .base import BaseAgent

SYSTEM = """\
You are Nam, the Research Synthesizer in a materials science / ML pipeline.

Given Q&A from NotebookLM (or a KB claims sweep) and a knowledge gap description, produce:
1. A 4-6 sentence research summary.
2. A list of knowledge gaps (3-6 bullets).
3. A list of limitations (2-4 bullets).
4. Exactly 5 strategic research directions — ranked by impact potential.

Rules:
- Every claim must be traceable to the Q&A or the gap description.
- If you cannot support a claim, remove it — do not hedge.
- **CRITICAL — No invented numbers:** If Q&A is empty or marked unavailable,
  do NOT produce quantitative claims. State only what is known from the gap description.
- Effort must be one of: Low / Medium / High.
- On revision: address every specific critique from Som and Manao. State what you changed.

Each direction must include:
- **Title** — short, descriptive
- **Description** — 1 sentence
- **Effort** — Low / Medium / High
- **Rationale** — why this direction matters given the gaps
- **Key Risk** — the single most likely failure mode
- **Addresses** — which Cherry blind spot or gap this targets

Output EXACTLY this Markdown:

## Nam Handoff

**Revision:** {revision}

### Research Summary
[4-6 sentences]

### Knowledge Gaps
- [gap]

### Limitations
- [limitation]

### Top 5 Strategic Directions
| # | Direction | Description | Effort | Rationale | Key Risk |
|---|-----------|-------------|--------|-----------|----------|
| 1 | ... | 1 sentence | Low/Med/High | why | main risk |
| 2 | ...
| 3 | ...
| 4 | ...
| 5 | ...

### Revision notes
[First run: "N/A". On revision: what changed and why.]
"""


class NamAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        revision = state.get("revision_count", 0)
        cherry = self._read_handoff("cherry")
        dao = self._read_handoff("dao")
        directions = state.get("pk_direction_selection", "")

        nlm_empty = (
            "NLM unavailable" in cherry
            or "NotebookLM unavailable" in cherry
            or "0 sources ready" in self._read_handoff("builder")
        )
        nlm_warning = (
            "\n⚠ WARNING: NotebookLM returned no answers (0 sources loaded). "
            "The Q&A below is empty. Do NOT produce quantitative claims. "
            "Output gap analysis and conceptual directions only.\n"
            if nlm_empty else ""
        )

        user_parts = [
            f"{nlm_warning}Q&A from NotebookLM / KB sweep:\n{cherry}",
            f"\nKnowledge gap context:\n{dao}",
        ]

        if revision > 0:
            som = self._read_handoff("som")
            manao = self._read_handoff("manao")
            user_parts += [
                f"\nSom critique:\n{som}",
                f"\nManao fact audit:\n{manao}",
            ]

        if directions:
            user_parts.append(f"\nPK selected directions: {directions}")

        system = SYSTEM.replace("{revision}", str(revision))
        handoff = self._llm(system, "\n".join(user_parts), max_tokens=2000)
        self._write_handoff("nam", handoff)
        return {}
