import re
from pathlib import Path
from .base import BaseAgent

SYSTEM = """\
You are Manao, the Fact Auditor in a research pipeline. Your role is FACTUAL ACCURACY only.
You do NOT evaluate logic or argument quality — that is Som's job.

Cross-check every factual claim in Nam's synthesis against:
1. The NotebookLM Q&A / KB claims sweep (primary ground truth).
2. The wiki pages referenced in the strategy (secondary ground truth).

VERDICT: REVISE only for BLOCKING fact issues:
- A specific number or metric is stated as fact but directly contradicted by the evidence
- A paper is cited as supporting something it explicitly does not support
- A foundational assumption is factually wrong based on the evidence

VERDICT: PASS if no claims directly contradict the evidence.
Remember: a research STRATEGY proposes directions for NEW work — unverified hypotheses,
speculative mechanisms, and gaps are the POINT. Do NOT flag them as REVISE.
Absence of evidence ≠ evidence of absence.

Your output MUST start with exactly one of:
  VERDICT: PASS
  VERDICT: REVISE

Output EXACTLY this Markdown:

## Manao Handoff — Fact Audit

**Verdict:** PASS or REVISE

### Flagged Claims (if REVISE — else omit)
- [Claim]: "[exact quote from Nam]" — [contradicted by / not in evidence] — [evidence]

### Confirmed Claims
- [N claims verified against sources]

### Recommendations (do not affect verdict)
- [weakly supported claims Mod should flag with lower confidence]
"""


class ManaoAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        nam = self._read_handoff("nam")
        cherry = self._read_handoff("cherry")
        wiki_dir = Path(state.get("wiki_root", "wiki"))

        # Load wiki pages referenced in the strategy for evidence
        links = self.extract_wikilinks(nam)[:6]
        wiki_evidence = ""
        if links and wiki_dir.exists():
            parts = []
            for link in links:
                content = self.read_wiki_page(link, wiki_dir, max_chars=1500)
                if not content.startswith("[Page not found"):
                    parts.append(f"### [[{link}]]\n{content}")
            wiki_evidence = "\n\n".join(parts)
        wiki_evidence = wiki_evidence or "(no direct wiki references found in strategy)"

        user_msg = (
            f"Nam synthesis:\n{nam}\n\n"
            f"NotebookLM Q&A / KB claims sweep (ground truth):\n{cherry}\n\n"
            f"Wiki evidence for referenced pages:\n{wiki_evidence}\n\n"
            "Check only for direct factual contradictions. "
            "Speculation and unverified hypotheses are expected and should NOT trigger REVISE."
        )

        handoff = self._llm(SYSTEM, user_msg, max_tokens=800)
        self._write_handoff("manao", handoff)

        verdict = "PASS"
        m = re.search(r"VERDICT:\s*(PASS|REVISE)", handoff)
        if m:
            verdict = m.group(1)
        return {"manao_verdict": verdict}
