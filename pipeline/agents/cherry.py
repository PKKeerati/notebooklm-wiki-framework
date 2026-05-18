import re
import yaml
from pathlib import Path
from .base import BaseAgent
from ..notebooklm_client import NLMClient

QUESTION_SYSTEM = """\
You are Cherry, the Question Shaper in a materials science / ML research pipeline.

Given a knowledge gap description, generate 6-8 precise, non-overlapping questions
that will extract maximum information from a document set. Question types:
- 2 foundational (establish baseline knowledge)
- 2 mechanistic (how/why things work)
- 2 gap-targeting (directly address the identified gaps)
- 1 blind-spot sweep (what important aspects were NOT covered?)
- 1 cross-domain (what can be borrowed from adjacent fields?)

Output ONLY a numbered list of questions, nothing else.
"""

COMPRESS_SYSTEM = """\
You are Cherry. Compress a NotebookLM answer to its essential points only.
- Keep specific numbers, method names, and key claims.
- Remove filler, hedging, and repetition.
- Maximum 5 bullet points.
Output only the bullets, no preamble.
"""

CLAIMS_SYSTEM = """\
You are a scientific summarizer. Extract exactly 5 bullet points from the paper excerpt
that are most relevant to the research topic. Each bullet: one precise fact or finding,
with any numbers preserved. Use LaTeX for formulas.
If the paper has nothing relevant, write: '- Not relevant to this topic.'
"""

SWEEP_SYSTEM = """\
You are Cherry, the adversarial Question Shaper. Two tasks:

TASK 1 — Q&A: Generate 6-8 research questions and answer each from the provided claims pool.
If an answer is not found, write 'Not found' — this confirms a gap and is valuable.
Question types: 2 foundational, 2 mechanistic, 2 gap-targeting, 1 blind-spot, 1 cross-domain.

TASK 2 — Critique: Adversarially evaluate the research direction:
- Which analogies from other systems may NOT transfer?
- Which quantitative claims have no evidence in the claims pool?
- What experimental/computational evidence is completely absent?
- What single finding would falsify the entire approach?

Output:
## Q&A
### Q1: ...
- bullet answers (max 5 per question)

## Unverified Claims
## Dangerous Analogies
## Missing Evidence
## Critical Questions
## Verdict (1-2 sentences: the single most critical risk)
"""

_KEEP_SECTIONS = re.compile(
    r"^#{1,3}\s+.*?(abstract|introduction|result|finding|discussion|conclusion|summary|outlook|implication)",
    re.IGNORECASE,
)
_SKIP_SECTIONS = re.compile(
    r"^#{1,3}\s+.*?(method|experimental|computational|calculation|reference|acknowledgement|supporting|appendix|author contribution)",
    re.IGNORECASE,
)



class CherryAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        dao_handoff = self._read_handoff("dao")
        builder_handoff = self._read_handoff("builder")
        notebook_id = state.get("notebook_id") or ""
        wiki_dir = Path(state.get("wiki_root", "wiki"))
        pk_input = state["pk_input"]

        nlm_available = bool(
            notebook_id
            and "N/A" not in builder_handoff
            and "unavailable" not in builder_handoff.lower()[:200]
        )

        # Generate questions from the gap description
        questions_raw = self._llm(QUESTION_SYSTEM, f"Knowledge gap:\n{dao_handoff}", max_tokens=600)
        questions = [
            re.sub(r"^\d+\.\s*", "", line).strip()
            for line in questions_raw.splitlines()
            if line.strip() and re.match(r"^\d+\.", line.strip())
        ]

        qa_blocks: list[str] = []
        blind_spots = ""

        if nlm_available:
            # Primary path: query NotebookLM in detailed mode (includes inline citations)
            for i, q in enumerate(questions, 1):
                raw_answer = NLMClient.ask(notebook_id, q, mode="detailed")
                compressed = self._llm(
                    COMPRESS_SYSTEM,
                    f"Question: {q}\n\nAnswer:\n{raw_answer}",
                    max_tokens=300,
                )
                qa_blocks.append(f"**Q{i}:** {q}\n**A{i}:**\n{compressed}")

            blind_raw = NLMClient.ask(
                notebook_id,
                "What important aspects of this topic were NOT covered by the sources?",
                mode="concise",
            )
            blind_spots = self._llm(
                COMPRESS_SYSTEM,
                f"Question: blind-spot sweep\n\nAnswer:\n{blind_raw}",
                max_tokens=300,
            )
        else:
            # Fallback path: structured claims pool from wiki + log/ summarization
            claims = self._load_claims_pool(pk_input, dao_handoff, builder_handoff, wiki_dir)
            if claims:
                claims_text = self._format_claims(claims)
                sweep_result = self._llm(
                    SWEEP_SYSTEM,
                    f"**Research Direction (Dao):**\n{dao_handoff}\n\n"
                    f"**Evidence Pool ({len(claims)} structured claims):**\n{claims_text}\n\n"
                    "Answer each question from the claims pool. Mark 'Not found' when evidence is absent.",
                    max_tokens=2000,
                )
                qa_blocks = [sweep_result]
                blind_spots = "[KB-only mode — blind spots from claims sweep above]"
            else:
                qa_blocks = [
                    f"**Q{i}:** {q}\n**A{i}:** [NotebookLM unavailable — answer pending]"
                    for i, q in enumerate(questions, 1)
                ]
                blind_spots = "[NotebookLM unavailable — no claims pool found in KB]"

        # Idea card for Nam — enriched with NotebookLM's own notebook summary if available
        nlm_summary = NLMClient.get_notebook_summary(notebook_id) if nlm_available else ""
        idea_card = self._llm(
            "Summarise the research intent in 3-5 sentences for a synthesis agent. "
            "Be specific about what is being compared, investigated, or built.",
            f"PK's question: {pk_input}\n\nGap description:\n{dao_handoff}"
            + (f"\n\nNotebookLM notebook summary:\n{nlm_summary}" if nlm_summary else ""),
            max_tokens=300,
        )

        handoff = (
            f"## Cherry Handoff\n\n"
            f"**Notebook ID:** {notebook_id or 'N/A'}\n"
            f"**Questions asked:** {len(questions)}\n"
            f"**Mode:** {'NotebookLM' if nlm_available else 'KB claims pool'}\n\n"
            f"### Idea Card\n{idea_card}\n\n"
            f"### Q&A\n\n" + "\n\n".join(qa_blocks) + "\n\n"
            f"### Blind Spots\n{blind_spots or '[none identified]'}\n\n"
            f"### Notes for Nam\n"
            f"{'NLM answers present — synthesise from Q&A.' if nlm_available else 'NLM unavailable — synthesise from KB claims sweep and idea card.'}\n"
        )
        self._write_handoff("cherry", handoff)
        return {}

    # ── Claims pool (KB-only fallback) ────────────────────────────────────────

    def _load_claims_pool(
        self, topic: str, dao_report: str, builder_context: str, wiki_dir: Path
    ) -> list[dict]:
        """Load structured claims from wiki YAML frontmatter or log/ summaries."""
        wiki_pages = self._relevant_wiki_pages(topic, dao_report, builder_context, wiki_dir)
        claims: list[dict] = []
        for page_path in wiki_pages[:10]:
            page_claims = self._read_page_claims(page_path)
            for c in page_claims:
                c["source"] = page_path.stem
            claims.extend(page_claims)

        if claims:
            print(f"  [Cherry] {len(claims)} claims loaded from {len(wiki_pages)} wiki pages")
            return claims

        # Fallback: log/ files
        log_dir = wiki_dir.parent / "log"
        if not log_dir.exists():
            log_dir = wiki_dir.parent.parent / "log"
        if log_dir.exists():
            print("  [Cherry] No wiki claims — falling back to log/ summarization")
            return self._fallback_log_summaries(topic, builder_context, log_dir)

        return []

    def _read_page_claims(self, page_path: Path) -> list[dict]:
        """Extract claims[] from YAML frontmatter of a wiki page."""
        try:
            content = page_path.read_text(encoding="utf-8", errors="ignore")
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if match:
                fm = yaml.safe_load(match.group(1))
                if isinstance(fm, dict):
                    return fm.get("claims", [])
        except Exception:
            pass
        return []

    def _relevant_wiki_pages(
        self, topic: str, dao_report: str, builder_context: str, wiki_dir: Path
    ) -> list[Path]:
        """Wiki pages relevant to the topic, prioritising those referenced in builder/dao."""
        stems: set[str] = set()
        for text in (dao_report, builder_context):
            for name in re.findall(r"\[\[([^\]|]+)\]\]", text):
                stems.add(re.sub(r"[\s_]+", "-", name.lower()))
            for name in re.findall(r"wiki/([^\s|/]+?)\.md", text):
                stems.add(name)

        pages: list[Path] = []
        for stem in stems:
            p = wiki_dir / f"{stem}.md"
            if p.exists():
                pages.append(p)

        if not pages:
            results = self.semantic_search(topic, wiki_dir, top_k=10)
            for name, _ in results:
                p = wiki_dir / name
                if p.exists():
                    pages.append(p)

        if not pages:
            pages = [
                p for p in sorted(wiki_dir.glob("*.md"))
                if p.name not in ("index.md",) and "hub" not in p.name
            ][-10:]

        return pages

    def _format_claims(self, claims: list[dict]) -> str:
        by_cat: dict[str, list] = {}
        for c in claims:
            cat = c.get("category", "RESULT")
            by_cat.setdefault(cat, []).append(c)

        lines = []
        for cat in ["RESULT", "TABLE", "MECHANISM", "METHOD", "COMPARISON"]:
            if cat not in by_cat:
                continue
            lines.append(f"\n### {cat}")
            for c in by_cat[cat]:
                src = c.get("source", "")
                conf = float(c.get("confidence", 0.9))
                lines.append(f"- [{src}] {c.get('fact', '')} (conf={conf:.2f})")
        return "\n".join(lines) or "(no structured claims available)"

    def _fallback_log_summaries(
        self, topic: str, builder_context: str, log_dir: Path
    ) -> list[dict]:
        """Per-paper LLM summarization when wiki has no promoted claims."""
        log_files = self._collect_log_files(builder_context, log_dir)
        all_claims: list[dict] = []
        for lf in log_files[:8]:
            print(f"  [Cherry] summarizing {lf.name} ...", end="", flush=True)
            raw = lf.read_text(encoding="utf-8", errors="ignore")
            body = re.sub(r"^---.*?---\s*", "", raw, count=1, flags=re.DOTALL).strip()
            excerpt = self._extract_key_sections(body)
            bullets = self._one_paper_summary(lf.stem, excerpt, topic)
            for line in bullets.split("\n"):
                line = line.strip().lstrip("- ").strip()
                if len(line) > 10:
                    all_claims.append({
                        "fact": line, "confidence": 0.8,
                        "category": "RESULT", "source": lf.stem,
                    })
            print(" ✓")
        return all_claims

    def _extract_key_sections(self, markdown: str, char_limit: int = 10_000) -> str:
        lines = markdown.split("\n")
        in_keep, in_skip = False, False
        kept: list[str] = []
        total = 0
        for line in lines:
            if _SKIP_SECTIONS.match(line):
                in_skip, in_keep = True, False
                continue
            if _KEEP_SECTIONS.match(line):
                in_skip, in_keep = False, True
                kept.append(line)
                total += len(line)
                continue
            if not in_skip and (in_keep or total == 0):
                kept.append(line)
                total += len(line)
            if total >= char_limit:
                break
        result = "\n".join(kept).strip()
        if len(result) < 500:
            head = markdown[:4_000]
            tail = markdown[-2_000:] if len(markdown) > 6_000 else ""
            result = head + ("\n\n[...]\n\n" + tail if tail else "")
        return result[:char_limit]

    def _one_paper_summary(self, title: str, excerpt: str, topic: str) -> str:
        user = f"**Topic:** {topic}\n\n**Paper: {title}**\n\n{excerpt[:8_000]}"
        try:
            return self._llm(CLAIMS_SYSTEM, user, max_tokens=500)
        except Exception as e:
            return f"- Summary failed: {e}"

    def _collect_log_files(self, builder_context: str, log_dir: Path) -> list[Path]:
        referenced = re.findall(r"log/([^\s|]+?\.md)", builder_context)
        files = [log_dir / name for name in referenced if (log_dir / name).exists()]
        if not files and log_dir.exists():
            files = [f for f in sorted(log_dir.glob("*.md")) if f.name != "log.md"][-8:]
        return files
