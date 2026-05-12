import re
import subprocess
import sys
from .base import BaseAgent

# Reads from Dao's "Verified source URLs" section — real URLs only, no LLM-invented IDs
_VERIFIED_URL_ROW = re.compile(r"^\|\s*\d+\s*\|\s*(https?://\S+)\s*\|", re.MULTILINE)

# Fallback: old-style table with possible bare arXiv IDs
_SOURCE_ROW = re.compile(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\S+\s*\|", re.MULTILINE)
_ARXIV_ID = re.compile(r"^arXiv:(\d{4}\.\d{4,5})", re.IGNORECASE)


def _extract_sources(dao_handoff: str) -> list[str]:
    """Extract source URLs from Dao handoff — prefers verified section."""
    # Try verified section first (new Dao format)
    verified = _VERIFIED_URL_ROW.findall(dao_handoff)
    if verified:
        return list(dict.fromkeys(s.strip() for s in verified))  # deduplicate
    # Fallback to old format with arXiv ID normalisation
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


class BuilderAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        dao_handoff = self._read_handoff("dao")
        sources = _extract_sources(dao_handoff)

        # Apply PK's edits from CP1 if any
        edits = state.get("source_edits", "")
        if edits:
            removed_nums = {int(x.strip()) for x in re.findall(r"\b(\d+)\b", edits) if x.strip().isdigit()}
            sources = [s for i, s in enumerate(sources, 1) if i not in removed_nums]
            extra_urls = re.findall(r"https?://\S+", edits)
            sources.extend(extra_urls)

        run_id = state["run_id"]
        notebook_id = ""
        loaded: list[dict] = []
        failed: list[dict] = []

        # Create notebook
        rc, stdout, stderr = _run_notebooklm("create", f"Research: {run_id[:10]}")
        if rc != 0:
            # NotebookLM unavailable — write stub handoff and continue
            self._write_handoff("builder", _stub_handoff(run_id, sources, stderr))
            return {"notebook_id": None, "builder_skipped": True}

        # Extract notebook ID from output (format: "Created notebook: <id>")
        id_match = re.search(r"([a-f0-9\-]{20,})", stdout)
        if id_match:
            notebook_id = id_match.group(1)
            _run_notebooklm("use", notebook_id)

        # Add sources one by one; track pass/fail
        for i, src in enumerate(sources, 1):
            src = src.strip()
            if not src:
                continue
            rc, out, err = _run_notebooklm("source", "add", src, timeout=180)
            if rc == 0:
                loaded.append({"num": i, "source": src, "status": "COMPLETED"})
            else:
                failed.append({"num": i, "source": src, "reason": err or "unknown error"})

        handoff = _build_handoff(run_id, notebook_id, loaded, failed)
        self._write_handoff("builder", handoff)
        return {"notebook_id": notebook_id, "failed_sources": [f["source"] for f in failed]}


def _build_handoff(run_id: str, notebook_id: str, loaded: list, failed: list) -> str:
    rows = "\n".join(
        f"| {s['num']} | {s['source'][:60]} | {s['status']} |"
        for s in loaded
    )
    fail_rows = "\n".join(f"- {f['source'][:60]} — {f['reason']}" for f in failed) or "None"

    return (
        f"## Builder Handoff\n\n"
        f"**Notebook ID:** {notebook_id or 'N/A'}\n"
        f"**Run ID:** {run_id}\n\n"
        f"### Sources loaded\n"
        f"| # | Source | Status |\n"
        f"|---|--------|--------|\n"
        f"{rows}\n\n"
        f"### Failed sources\n{fail_rows}\n\n"
        f"### Notes for Cherry\n"
        f"{len(loaded)} sources ready. {len(failed)} failed and excluded.\n"
    )


def _stub_handoff(run_id: str, sources: list, error: str) -> str:
    return (
        f"## Builder Handoff\n\n"
        f"**Notebook ID:** N/A (NotebookLM unavailable)\n"
        f"**Run ID:** {run_id}\n\n"
        f"### Error\n{error}\n\n"
        f"### Proposed sources (not loaded)\n"
        + "\n".join(f"- {s}" for s in sources)
        + "\n\n### Notes for Cherry\nNotebookLM unavailable — Cherry will skip NLM queries.\n"
    )
