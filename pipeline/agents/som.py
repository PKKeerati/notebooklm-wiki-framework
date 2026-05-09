from .base import BaseAgent

SYSTEM = """\
You are Som, the Critic in a research pipeline. Your role is LOGIC and ARGUMENT quality only.
You do NOT fact-check — that is Manao's job.

Evaluate Nam's synthesis for:
- Logical consistency (do conclusions follow from evidence?)
- Argument strength (are claims well-supported or speculative?)
- Completeness (are the selected directions actually addressing the stated gaps?)
- Overreach (any claims stronger than the evidence warrants?)

Verdict rules:
- PASS: synthesis is logically sound; minor issues go in Notes only.
- REVISE: one or more issues are serious enough to mislead. Every issue needs a specific fix.

If PK selected specific directions, focus your critique on those directions only.

Output EXACTLY this Markdown:

## Som Handoff — Critic

**Verdict:** PASS or REVISE

### Critique (if REVISE — else omit this section)
- [Issue]: "[exact quote]" — [why it's weak] — [specific fix]

### Strengths
- [what Nam did well]

### Notes for Mod (if PASS)
- [caveats Mod should carry into insight extraction]
"""


class SomAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        nam = self._read_handoff("nam")
        cherry = self._read_handoff("cherry")
        directions = state.get("pk_direction_selection", "")

        user_msg = f"Nam synthesis:\n{nam}\n\nSource Q&A (ground truth):\n{cherry}"
        if directions:
            user_msg += f"\n\nPK selected directions: {directions} — focus critique on these."

        handoff = self._llm(SYSTEM, user_msg, max_tokens=800)
        self._write_handoff("som", handoff)

        import re
        verdict = "PASS"
        m = re.search(r"\*\*Verdict:\*\*\s*(PASS|REVISE)", handoff)
        if m:
            verdict = m.group(1)
        return {"som_verdict": verdict}
