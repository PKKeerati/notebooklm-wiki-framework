import re
import sys
from datetime import datetime
from pathlib import Path
from .base import BaseAgent
try:
    from ..notebooklm_client import NLMClient
except ImportError:
    from notebooklm_client import NLMClient  # type: ignore[no-redef]

# Force UTF-8 I/O on Windows so ✓/✗ and other Unicode chars print correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPORT_SYSTEM = """\
You are Nanny, the Output Writer. Write a comprehensive technical research brief.

Rules:
- All claims must come from the handoffs — no new synthesis.
- Do NOT summarize or truncate — write full paragraphs for every section.
- Mark claims without Chompoo citations as ⚠ Unverified.
- Preserve all LaTeX formatting.

Structure:
# [Topic] — Research Brief
*[date] | Run: [run_id]*

## Abstract
(5-7 sentences: what was investigated, key findings, implications)

## Key Findings
(One subsection per insight: full explanation 3-5 sentences, mechanistic context, evidence basis + confidence)

## Knowledge Gaps

## Limitations

## Recommended Next Steps
(Top 5 from Mod — concrete experimental/computational actions)

## Atomic Insights
(table: Fact | Status | Confidence | Citation — cite from Chompoo, mark ⚠ Unverified where absent)

## Sources
"""

SLIDES_SYSTEM = """\
You are Nanny, the Output Writer. Write a Marp slide deck.

YAML front matter: marp: true, theme: gaia, size: 16:9, paginate: true.
Slides separated by ---. Max 6 bullets per slide. No prose.

Structure:
1. Title slide — research question + date
2. What We Know — top 3-5 KB facts as tight bullets
3. The Gap — top 3-5 gaps as tight bullets
4. Key Findings (one slide per insight, 5-7 bullets fully explained)
5. Audit Verdict — Som/Manao results + top flags
6. Top Directions — all 5 directions, one line each
7. Recommended Next Steps — 3-5 concrete actions
8. Open Questions — speculative insights reframed as testable questions
9. Sources
"""

OBSIDIAN_SYSTEM = """\
You are Nanny, the Output Writer. Format as Obsidian-ready Markdown.

Requirements:
- YAML frontmatter: type: brief, date, tags, summary (2-3 sentences)
- All materials/concepts as [[wikilinks]]
- High-confidence findings in > [!important] callouts with full paragraph explanations
- Speculative items in > [!warning] callouts with reasoning
- A Mermaid diagram of the main mechanistic pathway
- ## References section listing all [[wikilinks]] cited

Be comprehensive — every insight gets its own callout block with full context.
"""

LATEX_SYSTEM = """\
You are Nanny, the Output Writer. Produce a complete, compilable LaTeX research report.

Requirements:
- Use documentclass{article} with packages: geometry, hyperref, amsmath, amssymb, booktabs, graphicx, xcolor, parskip, microtype
- geometry: a4paper, margin=2.5cm
- Title block: \\title, \\author{Research Pipeline}, \\date
- All formulas in proper LaTeX math mode (inline $...$ or display \\[ ... \\])
- Use \\section, \\subsection for structure
- Atomic insights table: booktabs style with columns Insight | Confidence | Status
- Mark unverified claims with \\textcolor{red}{$\\dagger$}
- End with a \\begin{thebibliography} block

Structure:
\\section{Abstract}
\\section{Key Findings}  (one \\subsection per insight)
\\section{Knowledge Gaps}
\\section{Limitations}
\\section{Recommended Next Steps}
\\section{Atomic Insights}  (booktabs table)
\\section{References}

Output ONLY valid LaTeX — no markdown, no code fences.
"""

ABSTRACT_SYSTEM = """\
Write a concise research brief (~400 words). Sections:
1. Research Question (1 sentence)
2. Key Gaps (top 3-5, one sentence each)
3. Blind Spots (top 2-3, one sentence each)
4. Research Directions (all 5, one line each)
5. Audit Verdict (PASS/FAIL + top flag)
6. Key Insights (top 3-5, one sentence each)
7. Recommended Next Steps (3 bullets)
No paragraphs. Tight bullets throughout.
"""


class NannyAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        mod = self._read_handoff("mod")
        chompoo = self._read_handoff("chompoo")
        nam = self._read_handoff("nam")
        cherry = self._read_handoff("cherry")
        dao = self._read_handoff("dao")
        som = self._read_handoff("som")
        manao = self._read_handoff("manao")

        fmt_raw = (state.get("pk_output_format") or "A").upper()
        fmt = fmt_raw[0]
        pk_notes = fmt_raw[2:].strip() if len(fmt_raw) > 1 else ""

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

        if fmt in ("A", "D", "E", "G"):
            report = self._llm(REPORT_SYSTEM, context, max_tokens=3000)
            path = output_dir / "report.md"
            path.write_text(report, encoding="utf-8")
            written.append(str(path))

        if fmt in ("H", "E"):
            latex = self._llm(LATEX_SYSTEM, context, max_tokens=4000)
            path = output_dir / "report.tex"
            path.write_text(latex, encoding="utf-8")
            written.append(str(path))

        if fmt in ("B", "E"):
            slides = self._llm(SLIDES_SYSTEM, context, max_tokens=2000)
            path = output_dir / "slides.md"
            path.write_text(slides, encoding="utf-8")
            written.append(str(path))

        if fmt in ("C", "D", "E", "G"):
            self._update_obsidian(state, mod, nam, date, output_dir)
            written.append("wiki/ (Obsidian updated)")

        if fmt in ("F", "E", "G"):
            try:
                from .excalidraw_builder import build, write as excalidraw_write
                diagram = build(
                    topic=state["pk_input"],
                    nam_handoff=nam,
                    mod_handoff=mod,
                    dao_handoff=dao,
                    som_handoff=som,
                    manao_handoff=manao,
                    run_id=run_id,
                )
                ex_path = output_dir / "summary.excalidraw"
                excalidraw_write(ex_path, diagram)
                written.append(str(ex_path))
            except Exception as e:
                print(f"  ⚠ Excalidraw build failed: {e}")

        # NotebookLM native artifacts (complement Claude output)
        notebook_id = state.get("notebook_id") or ""
        if notebook_id:
            nlm_written = self._generate_nlm_artifacts(notebook_id, output_dir, fmt)
            written.extend(nlm_written)

        # Archive: full mission file with all agent handoffs
        ts = run_id.replace(":", "-").replace("T", "_")
        mission_path = output_dir / f"research_{ts}.md"
        mission_path.write_text(
            self._build_mission(state["pk_input"], ts, context, som, manao, mod, chompoo),
            encoding="utf-8",
        )
        written.append(str(mission_path))

        # Trace folder: preserve each agent's handoff for this session
        trace_dir = output_dir / f"trace_{ts}"
        trace_dir.mkdir(parents=True, exist_ok=True)
        for agent_name in ("dao", "builder", "cherry", "nam", "som", "manao", "mod", "chompoo", "nanny"):
            content = self._read_handoff(agent_name)
            if content:
                (trace_dir / f"handoff_{agent_name}.md").write_text(content, encoding="utf-8")

        # Abstract: condensed version
        all_handoffs = ""
        for agent_name, label in [
            ("dao",    "[Dao] Discovery & Gap Analysis"),
            ("cherry", "[Cherry] Blind-Spot Sweep"),
            ("nam",    "[Nam] Strategic Roadmap"),
            ("mod",    "[Mod] Atomic Insights"),
        ]:
            content = self._read_handoff(agent_name)
            if content:
                all_handoffs += f"\n\n### {label}\n{content[:2500]}"
        abstract_output = self._llm(
            ABSTRACT_SYSTEM,
            f"**Research Topic:** {state['pk_input']}\n\n{all_handoffs}",
            max_tokens=800,
        )
        abstract_path = output_dir / f"abstract_{ts}.md"
        abstract_path.write_text(abstract_output, encoding="utf-8")

        handoff = (
            f"## Nanny Handoff\n\n"
            f"**Run ID:** {run_id}\n"
            f"**Format:** {fmt}\n\n"
            f"### Files written\n"
            + "\n".join(f"- {w}" for w in written)
            + f"\n- {abstract_path} (condensed abstract)\n"
            + f"- {trace_dir}/ (agent handoff trace)\n"
        )
        self._write_handoff("nanny", handoff)

        print(f"\n  Output written to: {output_dir}")
        for w in written:
            print(f"    {w}")
        print(f"    {abstract_path}")

        return {"output_files": written}

    def _generate_nlm_artifacts(
        self, notebook_id: str, output_dir: Path, fmt: str
    ) -> list[str]:
        """Generate NotebookLM native artifacts alongside Claude output.

        fmt A/D/E/G → briefing report
        fmt B/E     → slide deck
        fmt F/E/G   → mind map JSON
        """
        written: list[str] = []

        if fmt in ("A", "D", "E", "G"):
            path = output_dir / "report_nlm.md"
            print("  [NLM] Generating briefing report...", end="", flush=True)
            if NLMClient.generate_artifact(notebook_id, "report", path):
                written.append(str(path))
                print(" ✓")
            else:
                print(" ✗ (skipped)")

        if fmt in ("B", "E"):
            path = output_dir / "slides_nlm.html"
            print("  [NLM] Generating slide deck...", end="", flush=True)
            if NLMClient.generate_artifact(notebook_id, "slides", path):
                written.append(str(path))
                print(" ✓")
            else:
                print(" ✗ (skipped)")

        if fmt in ("F", "E", "G"):
            path = output_dir / "mindmap_nlm.json"
            print("  [NLM] Generating mind map...", end="", flush=True)
            if NLMClient.generate_artifact(notebook_id, "mind_map", path):
                written.append(str(path))
                print(" ✓")
            else:
                print(" ✗ (skipped)")

        return written

    def _update_obsidian(
        self, state: dict, mod: str, nam: str, date: str, output_dir: Path
    ) -> None:
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

        # Also write an Obsidian brief page
        obsidian_report = self._llm(
            OBSIDIAN_SYSTEM,
            f"Run ID: {run_id}\nDate: {date}\n\nMod insights:\n{mod}\n\nNam synthesis:\n{nam}",
            max_tokens=2000,
        )
        brief_path = wiki_dir / f"brief-{run_id[:10]}.md"
        brief_path.write_text(obsidian_report, encoding="utf-8")
        print(f"    → {brief_path}")

    def _build_mission(
        self, topic: str, ts: str, context: str,
        som: str, manao: str, mod: str, chompoo: str,
    ) -> str:
        sections = [f"# Research Mission: {topic}\n\n"]
        for agent_name, label in [
            ("dao",    "[Dao] Discovery & Gap Analysis"),
            ("builder","[Builder] Source Environment"),
            ("cherry", "[Cherry] Blind-Spot Sweep"),
            ("nam",    "[Nam] Strategic Roadmap"),
            ("som",    "[Som] Logic Audit"),
            ("manao",  "[Manao] Fact Audit"),
            ("mod",    "[Mod] Atomic Insights"),
            ("chompoo","[Chompoo] Citation Verification"),
        ]:
            content = self._read_handoff(agent_name)
            if content:
                sections.append(f"---\n\n### {label}\n\n{content}\n\n")
        return "".join(sections)
