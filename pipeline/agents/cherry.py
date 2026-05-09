import re
import subprocess
import sys
from .base import BaseAgent

SYSTEM = """\
You are Cherry, the Question Shaper in a materials science / ML research pipeline.

Given a knowledge gap description, generate 6-8 precise, non-overlapping questions
that will extract maximum information from a document set. Questions should:
- Target specific mechanisms, benchmarks, or comparisons
- Progress from foundational to cutting-edge
- End with one broad blind-spot sweep question

Output ONLY a numbered list of questions, nothing else.
Example:
1. What is the architectural difference between MACE and NequIP in how they handle many-body interactions?
2. ...
8. What important aspects of this topic were NOT covered by the above sources?
"""

COMPRESS_SYSTEM = """\
You are Cherry. Compress a NotebookLM answer to its essential points only.
- Keep specific numbers, method names, and key claims.
- Remove filler, hedging, and repetition.
- Maximum 5 bullet points.
Output only the bullets, no preamble.
"""


def _ask_notebooklm(notebook_id: str, question: str, timeout: int = 60) -> str:
    """Ask NotebookLM a question; return the answer text or an error string."""
    cmd = [sys.executable, "-m", "notebooklm", "ask", question]
    if notebook_id:
        cmd = [sys.executable, "-m", "notebooklm", "-n", notebook_id, "ask", question]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() or result.stderr.strip() or "[no response]"
    except subprocess.TimeoutExpired:
        return "[timed out]"
    except FileNotFoundError:
        return "[notebooklm not installed]"


class CherryAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        dao_handoff = self._read_handoff("dao")
        builder_handoff = self._read_handoff("builder")
        notebook_id = state.get("notebook_id") or ""
        nlm_available = "N/A" not in builder_handoff and notebook_id

        # Generate questions
        questions_raw = self._llm(SYSTEM, f"Knowledge gap:\n{dao_handoff}", max_tokens=600)
        questions = [
            re.sub(r"^\d+\.\s*", "", line).strip()
            for line in questions_raw.splitlines()
            if line.strip() and re.match(r"^\d+\.", line.strip())
        ]

        qa_blocks: list[str] = []
        blind_spots = "[NotebookLM unavailable — blind-spot sweep skipped]"

        if nlm_available:
            for i, q in enumerate(questions, 1):
                raw_answer = _ask_notebooklm(notebook_id, q)
                compressed = self._llm(
                    COMPRESS_SYSTEM,
                    f"Question: {q}\n\nAnswer:\n{raw_answer}",
                    max_tokens=300,
                )
                qa_blocks.append(f"**Q{i}:** {q}\n**A{i}:**\n{compressed}")

            # Blind-spot sweep is always last question
            blind_raw = _ask_notebooklm(
                notebook_id,
                f"What important aspects of the topic were NOT covered by the sources?",
            )
            blind_spots = self._llm(
                COMPRESS_SYSTEM,
                f"Question: blind-spot sweep\n\nAnswer:\n{blind_raw}",
                max_tokens=300,
            )
        else:
            # No NotebookLM — Cherry still shapes the Idea Card for Nam
            qa_blocks = [
                f"**Q{i}:** {q}\n**A{i}:** [NotebookLM unavailable — answer pending]"
                for i, q in enumerate(questions, 1)
            ]

        idea_card = self._llm(
            "Summarise the research intent in 3-5 sentences for a synthesis agent. "
            "Be specific about what is being compared, investigated, or built.",
            f"PK's question: {state['pk_input']}\n\nGap description:\n{dao_handoff}",
            max_tokens=300,
        )

        handoff = (
            f"## Cherry Handoff\n\n"
            f"**Notebook ID:** {notebook_id or 'N/A'}\n"
            f"**Questions asked:** {len(questions)}\n\n"
            f"### Idea Card\n{idea_card}\n\n"
            f"### Q&A\n\n" + "\n\n".join(qa_blocks) + "\n\n"
            f"### Blind Spots\n{blind_spots}\n\n"
            f"### Notes for Nam\n"
            f"{'NLM answers present — synthesise from Q&A.' if nlm_available else 'NLM unavailable — synthesise from idea card and gap description only.'}\n"
        )
        self._write_handoff("cherry", handoff)
        return {}
