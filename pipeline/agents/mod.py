import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from .base import BaseAgent

SYSTEM = """\
You are Mod, the Insight Extractor. Extract atomic insights from approved research synthesis.

For each insight:
- One fact only — no compound sentences.
- Classify Status: Done / Ongoing / Not done
  - Done: published paper, released code, confirmed result.
  - Ongoing: active group, preprint exists, recent conference paper.
  - Not done: proposed, speculated, identified gap with no known active work.
- Estimate completion year if Ongoing/Not done (else N/A).
- Assign confidence: High / Medium / Low.

Also extract the Top 5 tactical choices: from PK's selected directions, which are most
actionable right now given the Done/Ongoing/Not done landscape?

Output EXACTLY this Markdown:

## Mod Handoff

**Insights extracted:** N
**KB pages to update:** [comma-separated page names or "none"]
**KB pages to create:** [comma-separated new page names or "none"]

### Atomic Insights
#### [Insight title]
- **Fact:** [1 sentence]
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

# Atomic insight block appended to KB pages
_INSIGHT_TEMPLATE = """\

### [{title}] ({date})
- **Fact:** {fact}
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

        user_msg = (
            f"Approved synthesis:\n{nam}\n\n"
            f"Som notes:\n{som_notes}\n\n"
            f"Manao confidence flags:\n{manao_notes}\n\n"
            f"PK selected directions: {directions or 'all'}\n\n"
            "Extract atomic insights and top 5 tactical choices."
        )
        handoff = self._llm(SYSTEM, user_msg, max_tokens=2000)
        self._write_handoff("mod", handoff)

        # Write insights to KB (append-only)
        updated, created = self._write_to_kb(handoff, state, wiki_dir)
        return {"kb_pages_updated": updated, "kb_pages_created": created}

    def _write_to_kb(self, handoff: str, state: dict, wiki_dir: Path) -> tuple[list, list]:
        if not wiki_dir.exists():
            return [], []

        run_id = state["run_id"]
        date = datetime.now().strftime("%Y-%m-%d")
        updated: list[str] = []
        created: list[str] = []

        # Parse pages to update/create from handoff
        to_update = _parse_list(handoff, "KB pages to update:")
        to_create = _parse_list(handoff, "KB pages to create:")

        # Extract insight blocks
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
                status=fields.get("Status", ""),
                est=fields.get("Est. completion", "N/A"),
                confidence=fields.get("Confidence", ""),
                run_id=run_id,
                tags=fields.get("Topic tags", ""),
            )

            # Find the best page to append to
            target = _best_page(title, to_update, wiki_dir)
            if target:
                with open(target, "a", encoding="utf-8") as f:
                    f.write(entry)
                updated.append(target.stem)
            else:
                # Create stub page if in to_create list
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
    # Fuzzy fallback: scan existing pages
    for page in wiki_dir.glob("*.md"):
        if page.name == "index.md":
            continue
        if any(w in title_lower for w in page.stem.lower().split("-")):
            return page
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.lower()).strip("-")
