import re
from datetime import datetime
from pathlib import Path
from .base import BaseAgent

REPORT_SYSTEM = """\
You are Nanny, the Output Writer. Write a clean research brief from the provided synthesis.

Rules:
- Maximum 1500 words.
- All claims must come from the handoffs — no new synthesis.
- Use Markdown with clear headers.
- End with a sources section listing the run's source list from Dao's handoff.

Structure:
# [Topic] — Research Brief
*[date] | Run: [run_id]*

## Key Findings
## Knowledge Gaps
## Limitations
## Recommended Next Steps (Top 5 from Mod)
## Atomic Insights (table: Fact | Status | Confidence | Citation)
  - Use citations from Chompoo. Mark unverified claims as ⚠ Unverified.
## Sources
"""

SLIDES_SYSTEM = """\
You are Nanny, the Output Writer. Write a slide deck outline (Markdown, PPTX-ready).

Rules:
- Maximum 10 slides.
- Maximum 3 bullets per slide.
- No prose — bullets only.
- Each slide = one ## heading followed by bullets.

Structure:
# [Topic] — [date]
## Slide 1: What We Know
## Slide 2: The Gap
## Slide 3-6: Key Findings (one finding per slide)
## Slide 7: Top Directions
## Slide 8: Recommended Next Steps
## Slide 9: Open Questions
## Slide 10: Sources
"""


class NannyAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        mod = self._read_handoff("mod")
        chompoo = self._read_handoff("chompoo")
        nam = self._read_handoff("nam")
        cherry = self._read_handoff("cherry")
        dao = self._read_handoff("dao")

        fmt_raw = (state.get("pk_output_format") or "A").upper()
        fmt = fmt_raw[0]  # First char: A/B/C/D/E
        pk_notes = fmt_raw[2:].strip() if len(fmt_raw) > 1 else ""  # After "A: notes"

        run_id = state["run_id"]
        date = datetime.now().strftime("%Y-%m-%d")
        output_dir = Path(state.get("output_root", "output")) / run_id[:10]
        output_dir.mkdir(parents=True, exist_ok=True)

        context = (
            f"Run ID: {run_id}\nDate: {date}\n"
            f"PK notes: {pk_notes}\n\n"
            f"Chompoo verified citations:\n{chompoo}\n\n"
            f"Mod handoff:\n{mod}\n\n"
            f"Nam synthesis:\n{nam}\n\n"
            f"Source list (from Dao):\n{dao}"
        )

        written: list[str] = []

        if fmt in ("A", "D", "E"):
            report = self._llm(REPORT_SYSTEM, context, max_tokens=2500)
            path = output_dir / "report.md"
            path.write_text(report, encoding="utf-8")
            written.append(str(path))

        if fmt in ("B", "E"):
            slides = self._llm(SLIDES_SYSTEM, context, max_tokens=1500)
            path = output_dir / "slides.md"
            path.write_text(slides, encoding="utf-8")
            written.append(str(path))

        if fmt in ("C", "D", "E"):
            self._update_obsidian(state, mod, nam, date)
            written.append("wiki/ (Obsidian updated)")

        handoff = (
            f"## Nanny Handoff\n\n"
            f"**Run ID:** {run_id}\n"
            f"**Format:** {fmt}\n\n"
            f"### Files written\n"
            + "\n".join(f"- {w}" for w in written)
            + "\n"
        )
        self._write_handoff("nanny", handoff)

        print(f"\n  Output written to: {output_dir}")
        for w in written:
            print(f"    {w}")

        return {"output_files": written}

    def _update_obsidian(self, state: dict, mod: str, nam: str, date: str) -> None:
        wiki_dir = Path(state.get("wiki_root", "wiki"))
        index_path = wiki_dir / "index.md"
        if not index_path.exists():
            return

        run_id = state["run_id"]
        entry = f"\n- **{date}** run `{run_id[:10]}` — {state['pk_input'][:80]}\n"

        current = index_path.read_text(encoding="utf-8")
        if "## Recent Runs" not in current:
            current += "\n## Recent Runs\n"
        current += entry
        index_path.write_text(current, encoding="utf-8")
