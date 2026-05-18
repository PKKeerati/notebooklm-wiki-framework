from __future__ import annotations
import os
import re
import yaml
from datetime import datetime
from pathlib import Path
from .base import BaseAgent
try:
    from ..notebooklm_client import NLMClient
    from .raw_pdf_scorer import score_raw_pdfs
except ImportError:
    from notebooklm_client import NLMClient  # type: ignore[no-redef]
    from agents.raw_pdf_scorer import score_raw_pdfs  # type: ignore[no-redef]

# Reads from Dao's "Verified source URLs" section — real URLs only, no LLM-invented IDs
_VERIFIED_URL_ROW = re.compile(r"^\|\s*\d+\s*\|\s*(https?://\S+)\s*\|", re.MULTILINE)

# Fallback: old-style table with possible bare arXiv IDs
_SOURCE_ROW = re.compile(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\S+\s*\|", re.MULTILINE)
_ARXIV_ID = re.compile(r"^arXiv:(\d{4}\.\d{4,5})", re.IGNORECASE)

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "raw"
LOG_DIR = PROJECT_ROOT / "log"


def _extract_sources(dao_handoff: str) -> list[str]:
    """Extract source URLs from Dao handoff — prefers verified section."""
    verified = _VERIFIED_URL_ROW.findall(dao_handoff)
    if verified:
        return list(dict.fromkeys(s.strip() for s in verified))
    sources = []
    seen: set[str] = set()
    for raw in _SOURCE_ROW.findall(dao_handoff):
        src = raw.strip()
        m = _ARXIV_ID.match(src)
        url = f"https://arxiv.org/abs/{m.group(1)}" if m else src
        if url not in seen and url.startswith("http"):
            sources.append(url)
            seen.add(url)
    return sources



def _url_to_pdf_stem(url: str) -> str:
    """Derive a candidate filename stem from a URL (arXiv ID or last path segment)."""
    arxiv_m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)", url, re.IGNORECASE)
    if arxiv_m:
        return arxiv_m.group(1)
    return url.rstrip("/").split("/")[-1].split("?")[0]


def _match_raw_pdf(url: str) -> Path | None:
    """Fuzzy-match a URL to a PDF in raw/ by stem similarity."""
    if not RAW_DIR.exists():
        return None
    stem = _url_to_pdf_stem(url).lower()
    for pdf in RAW_DIR.glob("*.pdf"):
        s = pdf.stem.lower()
        if stem[:10] in s or s[:10] in stem:
            return pdf
    return None


class BuilderAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        dao_handoff = self._read_handoff("dao")
        wiki_dir = Path(state.get("wiki_root", "wiki"))
        sources = _extract_sources(dao_handoff)

        # Apply PK's edits from CP1 if any
        edits = state.get("source_edits", "")
        if edits:
            removed_nums = {int(x.strip()) for x in re.findall(r"\b(\d+)\b", edits) if x.strip().isdigit()}
            sources = [s for i, s in enumerate(sources, 1) if i not in removed_nums]
            extra_urls = re.findall(r"https?://\S+", edits)
            sources.extend(extra_urls)

        run_id = state["run_id"]

        # ── Stage 1: Mistral OCR → log/ (ported from Repo B) ─────────────────
        ocr_results = self._extract_ocr(sources)
        self._auto_promote(wiki_dir)

        # ── Stage 2: Load wiki context for already-processed sources ──────────
        wiki_context = self._load_wiki_context(dao_handoff, wiki_dir)

        # ── Stage 3: NotebookLM (optional) ───────────────────────────────────
        notebook_id = ""
        loaded: list[dict] = []
        failed: list[dict] = []

        notebook_id = NLMClient.create_notebook(f"Research: {run_id[:10]}") or ""
        if not notebook_id:
            self._write_handoff("builder", _stub_handoff(run_id, sources, "NLM create failed", ocr_results, wiki_context))
            return {"notebook_id": None, "builder_skipped": True,
                    "failed_sources": [r["url"] for r in ocr_results if r["ocr"] == "failed"]}

        # Collect local PDFs matched to source URLs
        url_matched_pdfs = [
            Path(r["log"]) if r.get("log", "").endswith(".pdf") else _match_raw_pdf(r["url"])
            for r in ocr_results
            if r.get("pdf")
        ]
        url_matched_pdfs = [p for p in url_matched_pdfs if p and p.exists()]

        # ── Stage 3.5: Score raw/ KB PDFs and upload top-N ───────────────────
        top_n = state.get("raw_pdf_top_n", 30)
        min_score = state.get("raw_pdf_min_score", 0.15)
        api_key = os.environ.get("MISTRAL_API_KEY")
        print(f"  [Builder] Scoring raw/ PDFs for relevance (top {top_n})...")
        scored = score_raw_pdfs(
            query=state.get("pk_input", ""),
            dao_handoff=dao_handoff,
            wiki_dir=wiki_dir,
            raw_dir=RAW_DIR,
            top_n=top_n,
            min_score=min_score,
            api_key=api_key,
        )
        kb_pdfs = [p for p, _s, _r in scored]
        if kb_pdfs:
            print(f"  [Builder] Selected {len(kb_pdfs)} KB PDFs (top score: {scored[0][1]:.2f})")
        else:
            print("  [Builder] No KB PDFs met the relevance threshold.")

        # Merge URL-matched + KB-scored PDFs (deduplicate)
        seen_paths: set[Path] = set()
        all_pdfs: list[Path] = []
        for p in url_matched_pdfs + kb_pdfs:
            if p not in seen_paths:
                seen_paths.add(p)
                all_pdfs.append(p)

        clean_sources = [s.strip() for s in sources if s.strip()]
        loaded, failed = NLMClient.add_sources(notebook_id, clean_sources, all_pdfs)
        # Re-number for handoff display
        for i, item in enumerate(loaded, 1):
            item["num"] = i
        for i, item in enumerate(failed, 1):
            item["num"] = len(loaded) + i

        # ── Stage 4: NLM web research (supplements Semantic Scholar) ─────────
        pk_input = state.get("pk_input", "")
        print(f"  [Builder] Running NotebookLM web research on: {pk_input[:60]}...")
        web_sources = NLMClient.run_web_research(notebook_id, pk_input, max_sources=8)

        handoff = _build_handoff(run_id, notebook_id, loaded, failed, ocr_results, wiki_context, web_sources, scored)
        self._write_handoff("builder", handoff)
        return {"notebook_id": notebook_id, "failed_sources": [f["source"] for f in failed]}

    # ── Mistral OCR extraction ────────────────────────────────────────────────

    def _extract_ocr(self, sources: list[str]) -> list[dict]:
        """For each source URL, fuzzy-match to raw/ PDF and OCR if not cached."""
        import os
        api_key = os.environ.get("MISTRAL_API_KEY")
        results: list[dict] = []
        LOG_DIR.mkdir(exist_ok=True)

        for url in sources:
            pdf = _match_raw_pdf(url)
            entry: dict = {"url": url, "pdf": str(pdf) if pdf else None, "ocr": "no_pdf", "log": None}

            if not pdf:
                results.append(entry)
                continue

            log_path = LOG_DIR / f"{pdf.stem}.md"
            wiki_path = Path("wiki") / f"{pdf.stem}.md"  # relative — wiki_dir varies

            if log_path.exists():
                entry["ocr"] = "cached"
                entry["log"] = str(log_path)
                print(f"  [OCR cached] {pdf.name}")
                results.append(entry)
                continue
            if wiki_path.exists():
                entry["ocr"] = "cached/wiki"
                entry["log"] = str(wiki_path)
                results.append(entry)
                continue

            if not api_key:
                entry["ocr"] = "skipped (no MISTRAL_API_KEY)"
                results.append(entry)
                continue

            print(f"  [OCR] {pdf.name} ...", end="", flush=True)
            markdown = self._mistral_ocr(pdf, api_key)
            if markdown.startswith("Error"):
                entry["ocr"] = f"failed: {markdown[:80]}"
                print(" ✗")
            else:
                fm = {
                    "title": pdf.stem.replace("-", " "),
                    "type": "paper",
                    "sources": [f"raw/{pdf.name}"],
                    "extraction_method": "mistral-ocr-latest",
                    "last_updated": datetime.now().strftime("%Y-%m-%d"),
                }
                content = (
                    f"---\n{yaml.dump(fm, sort_keys=False, allow_unicode=True)}---\n\n"
                    f"# {pdf.stem}\n\n{markdown}"
                )
                log_path.write_text(content, encoding="utf-8")
                entry["ocr"] = "extracted"
                entry["log"] = str(log_path)
                print(f" ✓ ({len(markdown)} chars)")

            results.append(entry)
        return results

    def _mistral_ocr(self, pdf_path: Path, api_key: str) -> str:
        import requests
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            with open(pdf_path, "rb") as f:
                upload = requests.post(
                    "https://api.mistral.ai/v1/files",
                    headers=headers,
                    files={"file": (pdf_path.name, f, "application/pdf")},
                    data={"purpose": "ocr"},
                    timeout=60,
                )
                upload.raise_for_status()
            file_id = upload.json()["id"]

            url_resp = requests.get(
                f"https://api.mistral.ai/v1/files/{file_id}/url",
                headers=headers, timeout=30,
            )
            url_resp.raise_for_status()
            signed_url = url_resp.json()["url"]

            ocr_resp = requests.post(
                "https://api.mistral.ai/v1/ocr",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "model": "mistral-ocr-latest",
                    "document": {"type": "document_url", "document_url": signed_url},
                    "include_image_base64": False,
                },
                timeout=120,
            )
            ocr_resp.raise_for_status()
            pages = ocr_resp.json().get("pages", [])
            return "\n\n".join(p.get("markdown", "") for p in pages)
        except Exception as e:
            return f"Error: {e}"

    # ── Auto-promote log/ → wiki/ ─────────────────────────────────────────────

    def _auto_promote(self, wiki_dir: Path) -> None:
        """Promote new log/ files to wiki/ via wiki_manager's LLM structuring."""
        if not LOG_DIR.exists():
            return
        to_promote = [
            f for f in LOG_DIR.glob("*.md")
            if f.name != "log.md" and not (wiki_dir / f.name).exists()
        ]
        if not to_promote:
            return
        print(f"  [Builder] Auto-promoting {len(to_promote)} log/ file(s) to wiki/...")
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
            from wiki_manager import structure_with_llm, write_wiki_page, update_vectors
            for lf in to_promote:
                raw = lf.read_text(encoding="utf-8", errors="ignore")
                # Strip frontmatter to get body text for re-structuring
                body = re.sub(r"^---.*?---\s*", "", raw, count=1, flags=re.DOTALL).strip()
                try:
                    structured = structure_with_llm(body, lf.stem)
                    # Use a dummy pdf_path with the correct stem so the slug matches
                    page_path = write_wiki_page(structured, Path(f"raw/{lf.stem}.pdf"))
                    update_vectors(page_path, structured)
                    print(f"    → wiki/{page_path.name}")
                except Exception as e:
                    print(f"    ✗ {lf.name}: {e}")
        except Exception as e:
            print(f"  [Builder] Auto-promote skipped: {e}")

    # ── Wiki context loader ───────────────────────────────────────────────────

    def _load_wiki_context(self, dao_handoff: str, wiki_dir: Path) -> str:
        """Load snippet from wiki pages referenced by wikilinks in Dao's handoff."""
        links = self.extract_wikilinks(dao_handoff)[:8]
        parts = []
        for link in links:
            content = self.read_wiki_page(link, wiki_dir, max_chars=1200)
            if not content.startswith("[Page not found"):
                parts.append(f"### [[{link}]]\n{content}")
        return "\n\n---\n\n".join(parts) or "(no existing wiki pages found for referenced sources)"


# ── Handoff builders ──────────────────────────────────────────────────────────

def _build_handoff(
    run_id: str, notebook_id: str,
    loaded: list, failed: list,
    ocr_results: list, wiki_context: str,
    web_sources: list | None = None,
    scored_pdfs: list | None = None,
) -> str:
    ocr_ok = sum(1 for r in ocr_results if r["ocr"] in ("extracted", "cached", "cached/wiki"))
    nb_rows = "\n".join(
        f"| {s['num']} | {s['source'][:60]} | {s['status']} |" for s in loaded
    )
    fail_rows = "\n".join(f"- {f['source'][:60]} — {f['reason']}" for f in failed) or "None"
    ocr_rows = "\n".join(
        f"| {r['url'][:55]} | {r['ocr']} | {r['log'] or '—'} |"
        for r in ocr_results
    )
    web_rows = "\n".join(
        f"| {s['url'][:65]} | {s.get('title', '')[:50]} |"
        for s in (web_sources or [])
    ) or "| — | (none found) |"
    kb_rows = "\n".join(
        f"| {p.name[:60]} | {score:.2f} | {reason[:60]} |"
        for p, score, reason in (scored_pdfs or [])
    ) or "| — | — | (none selected) |"

    cherry_note = (
        f"Query NotebookLM notebook `{notebook_id}` for Q&A. "
        f"Also use Mistral OCR log/ files below for structured claims."
        if notebook_id
        else "NotebookLM unavailable. Use Mistral OCR extractions in log/ as primary source."
    )

    return (
        f"## Builder Handoff\n\n"
        f"**Notebook ID:** {notebook_id or 'N/A'}\n"
        f"**Run ID:** {run_id}\n\n"
        f"### Mistral OCR Results ({ocr_ok}/{len(ocr_results)} ready)\n"
        f"| URL | OCR Status | log/ Path |\n"
        f"|-----|-----------|----------|\n"
        f"{ocr_rows}\n\n"
        f"### NotebookLM Sources (from Semantic Scholar)\n"
        f"| # | Source | Status |\n"
        f"|---|--------|--------|\n"
        f"{nb_rows or '| — | (none loaded) | — |'}\n\n"
        f"### NLM Web Research Sources ({len(web_sources or [])} imported)\n"
        f"| URL | Title |\n"
        f"|-----|-------|\n"
        f"{web_rows}\n\n"
        f"### Raw KB PDFs uploaded ({len(scored_pdfs or [])} selected)\n"
        f"| File | Score | Signals |\n"
        f"|------|-------|--------|\n"
        f"{kb_rows}\n\n"
        f"### Failed sources\n{fail_rows}\n\n"
        f"### Local Wiki Context\n{wiki_context[:3000]}\n\n"
        f"### Notes for Cherry\n{cherry_note}\n"
    )


def _stub_handoff(run_id: str, sources: list, error: str, ocr_results: list, wiki_context: str) -> str:
    ocr_ok = sum(1 for r in ocr_results if r["ocr"] in ("extracted", "cached", "cached/wiki"))
    return (
        f"## Builder Handoff\n\n"
        f"**Notebook ID:** N/A (NotebookLM unavailable)\n"
        f"**Run ID:** {run_id}\n\n"
        f"### Error\n{error}\n\n"
        f"### Mistral OCR Results ({ocr_ok}/{len(ocr_results)} ready)\n"
        + "\n".join(
            f"- {r['url'][:60]} → {r['ocr']} ({r['log'] or 'no log'})"
            for r in ocr_results
        )
        + f"\n\n### Proposed sources (not loaded into NotebookLM)\n"
        + "\n".join(f"- {s}" for s in sources)
        + f"\n\n### Local Wiki Context\n{wiki_context[:3000]}\n\n"
        + "### Notes for Cherry\nNotebookLM unavailable — Cherry will use Mistral OCR log/ files and KB claims.\n"
    )
