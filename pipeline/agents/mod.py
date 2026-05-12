import json
import re
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional
from .base import BaseAgent

SYSTEM = """\
You are Mod, the Distiller. Extract atomic insights from approved research synthesis.

Rules:
- Each insight is a single verifiable fact or mechanism — no multi-claim paragraphs.
- Use LaTeX for all chemical formulas and equations (e.g., $MgH_2$, $\\Delta G$).
- Assign confidence based on evidence quality:
    High   = directly quoted from a cited source in the vault
    Medium = inferred from multiple converging sources or NLM Q&A
    Low    = plausible but speculative or uncited
- Any metric without a [[wikilink]] citation defaults to Medium or Low confidence.
- Classify Status: Done / Ongoing / Not done
    Done:     published paper, released code, confirmed result.
    Ongoing:  active group, preprint exists, recent conference paper.
    Not done: proposed, speculated, identified gap with no known active work.
- Extract ALL distinct insights (aim for 10-15) — do not truncate.
- Top 5 tactical choices: the most actionable directions given the Done/Ongoing/Not done landscape.

Output EXACTLY this Markdown:

## Mod Handoff

**Insights extracted:** N
**KB pages to update:** [comma-separated page names or "none"]
**KB pages to create:** [comma-separated new page names or "none"]

### Atomic Insights
#### [Insight title]
- **Fact:** [1 precise sentence — LaTeX-formatted]
- **Detail:** [2-3 sentences: mechanism, evidence, implications]
- **Status:** Done / Ongoing / Not done
- **Est. completion:** [year or N/A]
- **Confidence:** High / Medium / Low
- **Topic tags:** #tag1 #tag2

[repeat for each insight]

### Conflicts with existing KB
- [Describe any claim that contradicts an existing KB entry, or "None"]

### Top 5 tactical choices
| # | Direction | Status | Effort | Why now |
|---|-----------|--------|--------|---------|
| 1 | ...       | ...    | ...    | ...     |
"""

_INSIGHT_TEMPLATE = """\

### [{title}] ({date})
- **Fact:** {fact}
- **Detail:** {detail}
- **Status:** {status}
- **Est. completion:** {est}
- **Confidence:** {confidence}
- **Source run:** {run_id}
- **Topic tags:** {tags}
"""


class ModAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        nam = self._read_handoff("nam")
        som_notes = self._read_handoff("som")
        manao_notes = self._read_handoff("manao")
        directions = state.get("pk_direction_selection", "")
        wiki_dir = Path(state.get("wiki_root", "wiki"))
        topic = state.get("pk_input", "")

        user_msg = (
            f"**Topic:** {topic}\n\n"
            f"Approved synthesis:\n{nam}\n\n"
            f"Som notes:\n{som_notes}\n\n"
            f"Manao confidence flags:\n{manao_notes}\n\n"
            f"PK selected directions: {directions or 'all'}\n\n"
            "Extract all atomic insights and top 5 tactical choices. "
            "Downgrade confidence for anything flagged in the audit. "
            "Preserve LaTeX formatting. Be detailed in the Detail: field."
        )
        handoff = self._llm(SYSTEM, user_msg, max_tokens=3000)
        self._write_handoff("mod", handoff)

        # Persist insights to wiki/concepts/ (session-aware, stale-detecting)
        self._persist_to_wiki(handoff, topic, wiki_dir, state["run_id"])

        # Also append to relevant existing KB pages
        updated, created = self._write_to_kb(handoff, state, wiki_dir)
        self.audit_log(wiki_dir, "Mod", "insights_persisted",
                       f"topic={topic[:60]}, updated={len(updated)}, created={len(created)}")
        return {"kb_pages_updated": updated, "kb_pages_created": created}

    # ── wiki/concepts/ persistence ────────────────────────────────────────────

    def _persist_to_wiki(self, report: str, topic: str, wiki_dir: Path, run_id: str) -> None:
        """Write insights to wiki/concepts/<slug>-insights.md with stale detection."""
        if not wiki_dir.exists():
            return
        concepts_dir = wiki_dir / "concepts"
        concepts_dir.mkdir(exist_ok=True)

        slug = re.sub(r"[^\w-]", "-", topic.lower()).strip("-")[:50]
        out_path = concepts_dir / f"{slug}-insights.md"
        ts = datetime.now().strftime("%Y-%m-%d")

        stale_titles: list[str] = []
        if out_path.exists():
            existing_body = out_path.read_text(encoding="utf-8", errors="ignore")
            stale_titles = self._find_stale_insights(existing_body, report)
            if stale_titles:
                print(f"    ⚠  Marking {len(stale_titles)} stale insight(s): {stale_titles}")
                self.audit_log(wiki_dir, "Mod", "stale_insights", f"stale: {stale_titles}")

        if out_path.exists():
            existing_body = self._mark_stale(
                out_path.read_text(encoding="utf-8", errors="ignore"), stale_titles
            )
            content = existing_body.rstrip() + f"\n\n## Session {ts} (run: {run_id[:10]})\n\n{report}"
        else:
            frontmatter = {
                "title": f"Insights: {topic}",
                "type": "crystallized_insight",
                "last_updated": ts,
                "generated_by": "Mod",
            }
            content = (
                f"---\n{yaml.dump(frontmatter, sort_keys=False)}---\n\n"
                f"# Insights: {topic}\n\n"
                f"## Session {ts} (run: {run_id[:10]})\n\n{report}"
            )

        out_path.write_text(content, encoding="utf-8")
        print(f"    → concepts/{out_path.name}")

    def _find_stale_insights(self, old_body: str, new_report: str) -> list[str]:
        """LLM identifies old insight titles contradicted by new findings."""
        old_section = old_body[-3000:] if len(old_body) > 3000 else old_body
        system = (
            "You compare OLD research insights against NEW ones. "
            "Return ONLY a JSON array of old insight short titles (### headings) "
            "that are directly contradicted by the new report. "
            "If nothing is contradicted, return []. "
            'Example: ["Vacancy Effect on d-band", "OER Rate-limiting Step"]'
        )
        user = (
            f"**OLD insights (last 3000 chars):**\n{old_section}\n\n"
            f"**NEW insights:**\n{new_report[:3000]}"
        )
        try:
            raw = self._llm(system, user, max_tokens=300)
            match = re.search(r"\[.*?\]", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass
        return []

    def _mark_stale(self, body: str, stale_titles: list[str]) -> str:
        """Wrap stale insight blocks in a [!stale] callout."""
        if not stale_titles:
            return body
        lines = body.split("\n")
        result: list[str] = []
        in_stale = False
        for line in lines:
            if line.startswith("### "):
                title = line[4:].strip()
                in_stale = any(s.lower() in title.lower() for s in stale_titles)
                if in_stale:
                    result.append("> [!stale] Superseded")
            result.append(f"> {line}" if in_stale else line)
        return "\n".join(result)

    # ── Append to existing KB pages ───────────────────────────────────────────

    def _write_to_kb(self, handoff: str, state: dict, wiki_dir: Path) -> tuple[list, list]:
        if not wiki_dir.exists():
            return [], []

        run_id = state["run_id"]
        date = datetime.now().strftime("%Y-%m-%d")
        updated: list[str] = []
        created: list[str] = []

        to_update = _parse_list(handoff, "KB pages to update:")
        to_create = _parse_list(handoff, "KB pages to create:")

        # Parse insight blocks (#### heading + field lines)
        insight_blocks = re.findall(
            r"#### (.+?)\n((?:- \*\*.+?\n)+)",
            handoff,
            re.MULTILINE,
        )

        for title, block in insight_blocks:
            fields = dict(re.findall(r"- \*\*(.+?):\*\* (.+)", block))
            entry = _INSIGHT_TEMPLATE.format(
                title=title.strip(),
                date=date,
                fact=fields.get("Fact", ""),
                detail=fields.get("Detail", ""),
                status=fields.get("Status", ""),
                est=fields.get("Est. completion", "N/A"),
                confidence=fields.get("Confidence", ""),
                run_id=run_id,
                tags=fields.get("Topic tags", ""),
            )

            target = _best_page(title, to_update, wiki_dir)
            if target:
                with open(target, "a", encoding="utf-8") as f:
                    f.write(entry)
                updated.append(target.stem)
            else:
                page_name = _slug(title)
                if any(page_name in c for c in to_create):
                    page_path = wiki_dir / f"{page_name}.md"
                    page_path.write_text(
                        f"---\ntitle: {title}\ntype: concept\ncreated: {date}\n---\n"
                        f"# {title}\n{entry}",
                        encoding="utf-8",
                    )
                    created.append(page_name)

        return updated, created


def _parse_list(text: str, label: str) -> list[str]:
    m = re.search(rf"\*\*{re.escape(label)}\*\*\s*(.+)", text)
    if not m:
        return []
    raw = m.group(1).strip()
    return [x.strip() for x in raw.split(",") if x.strip() and x.strip().lower() != "none"]


def _best_page(title: str, candidates: list, wiki_dir: Path) -> Optional[Path]:
    title_lower = title.lower()
    for name in candidates:
        page = wiki_dir / f"{name}.md"
        if page.exists() and any(w in title_lower for w in name.lower().split()):
            return page
    for page in wiki_dir.glob("*.md"):
        if page.name == "index.md":
            continue
        if any(w in title_lower for w in page.stem.lower().split("-")):
            return page
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.lower()).strip("-")
