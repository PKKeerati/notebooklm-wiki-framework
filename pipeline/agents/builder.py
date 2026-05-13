from __future__ import annotations
import re
import subprocess
import sys
import yaml
from datetime import datetime
from pathlib import Path
from .base import BaseAgent

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


def _run_notebooklm(*args: str, timeout: int = 300) -> tuple[int, str, str]:
    """Run notebooklm CLI; return (returncode, stdout, stderr)."""
    cmd = [sys.executable, "-m", "notebooklm", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return 1, "", "notebooklm not installed — run: pip install notebooklm"
    except subprocess.TimeoutExpired:
        return 1, "", f"notebooklm timed out after {timeout}s"


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

        rc, stdout, stderr = _run_notebooklm("create", f"Research: {run_id[:10]}")
        if rc != 0:
            self._write_handoff("builder", _stub_handoff(run_id, sources, stderr, ocr_results, wiki_context))
            return {"notebook_id": None, "builder_skipped": True,
                    "failed_sources": [r["url"] for r in ocr_results if r["ocr"] == "failed"]}

        id_match = re.search(r"([a-f0-9\-]{20,})", stdout)
        if id_match:
            notebook_id = id_match.group(1)
            _run_notebooklm("use", notebook_id)

        for i, src in enumerate(sources, 1):
            src = src.strip()
            if not src:
                continue
            rc, out, err = _run_notebooklm("source", "add", src, timeout=180)
            if rc == 0:
                loaded.append({"num": i, "source": src, "status": "COMPLETED"})
            else:
                failed.append({"num": i, "source": src, "reason": err or "unknown error"})

        handoff = _build_handoff(run_id, notebook_id, loaded, failed, ocr_results, wiki_context)
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
        f"### NotebookLM Sources\n"
        f"| # | Source | Status |\n"
        f"|---|--------|--------|\n"
        f"{nb_rows or '| — | (none loaded) | — |'}\n\n"
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
