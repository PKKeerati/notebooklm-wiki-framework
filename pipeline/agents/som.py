from .base import BaseAgent
import re

SYSTEM = """\
You are Som, the Logic Auditor in a research pipeline. Your role is LOGIC and ARGUMENT quality only.
You do NOT fact-check — that is Manao's job.

VERDICT: REVISE only if you find BLOCKING issues — ones that would make a direction
fundamentally unworkable or self-contradictory:
- A direction directly contradicts another (not a sequential dependency — a real contradiction)
- An effort estimate is so wrong it would mislead resource planning (e.g., "Low" for a 3-year project)
- A direction is entirely disconnected from the stated gaps
- An unfalsifiable claim is the CORE of a direction (not a minor hedge)

VERDICT: PASS if the strategy is logically coherent overall, even if imperfect.
Research strategies are inherently provisional — minor hedging, sequential dependencies,
and open-ended risks are NORMAL and should NOT trigger REVISE.

If PK selected specific directions, focus critique on those directions only.

Your output MUST start with exactly one of:
  VERDICT: PASS
  VERDICT: REVISE

Output EXACTLY this Markdown:

## Som Handoff — Logic Audit

**Verdict:** PASS or REVISE

### Blocking Issues (if REVISE — else omit)
- [Issue]: "[exact quote]" — [why it's blocking] — [specific fix required]

### Strengths
- [what Nam did well]

### Minor Notes (do not affect verdict)
- [non-blocking observations for Mod to carry forward]
"""


class SomAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        nam = self._read_handoff("nam")
        cherry = self._read_handoff("cherry")
        directions = state.get("pk_direction_selection", "")

        user_msg = f"Nam synthesis:\n{nam}\n\nSource Q&A / KB sweep (ground truth):\n{cherry}"
        if directions:
            user_msg += f"\n\nPK selected directions: {directions} — focus on these."

        handoff = self._llm(SYSTEM, user_msg, max_tokens=800)
        self._write_handoff("som", handoff)

        verdict = "PASS"
        m = re.search(r"VERDICT:\s*(PASS|REVISE)", handoff)
        if m:
            verdict = m.group(1)
        return {"som_verdict": verdict}
