"""Sync wrapper around the async notebooklm-py client for pipeline agents.

Each public method spins up a fresh NotebookLMClient context from cached
auth (notebooklm login) and tears it down cleanly. No state is held
between calls — keeps the sync/async boundary simple and safe.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def _available() -> bool:
    try:
        import notebooklm  # noqa: F401
        return True
    except ImportError:
        return False


# ── Async implementations ─────────────────────────────────────────────────────

async def _create_notebook_async(title: str) -> str | None:
    from notebooklm import NotebookLMClient
    async with await NotebookLMClient.from_storage() as client:
        nb = await client.notebooks.create(title)
        return nb.id


async def _add_sources_async(
    notebook_id: str,
    urls: list[str],
    pdf_paths: list[Path],
) -> tuple[list[dict], list[dict]]:
    from notebooklm import NotebookLMClient
    async with await NotebookLMClient.from_storage() as client:
        loaded: list[dict] = []
        failed: list[dict] = []
        source_ids: list[str] = []

        async def _add_url(url: str) -> None:
            try:
                src = await client.sources.add_url(notebook_id, url)
                loaded.append({"source": url, "status": "COMPLETED", "source_id": src.id})
                source_ids.append(src.id)
            except Exception as e:
                failed.append({"source": url, "reason": str(e)[:120]})

        async def _add_pdf(pdf: Path) -> None:
            try:
                src = await client.sources.add_file(notebook_id, str(pdf))
                loaded.append({"source": str(pdf), "status": "COMPLETED", "source_id": src.id})
                source_ids.append(src.id)
            except Exception as e:
                failed.append({"source": str(pdf), "reason": str(e)[:120]})

        # URLs concurrently, PDFs sequentially (uploads can be large)
        await asyncio.gather(*(_add_url(u) for u in urls))
        for pdf in pdf_paths:
            await _add_pdf(pdf)

        # Block until NotebookLM finishes processing every source before Cherry queries
        if source_ids:
            try:
                await client.sources.wait_for_sources(notebook_id, source_ids, timeout=300)
            except Exception as e:
                print(f"  [NLM] source-wait warning: {e}", file=sys.stderr)

        return loaded, failed


async def _ask_async(notebook_id: str, question: str, mode: str) -> str:
    from notebooklm import NotebookLMClient
    from notebooklm._types.chat import ChatMode

    _mode_map = {
        "detailed": ChatMode.DETAILED,
        "concise": ChatMode.CONCISE,
        "default": ChatMode.DEFAULT,
        "learning_guide": ChatMode.LEARNING_GUIDE,
    }
    async with await NotebookLMClient.from_storage() as client:
        try:
            await client.chat.set_mode(notebook_id, _mode_map.get(mode, ChatMode.DETAILED))
        except Exception:
            pass  # mode setting is best-effort
        result = await client.chat.ask(notebook_id, question)
        answer = result.answer or ""
        if result.references:
            refs = "\n".join(
                f"  [{i + 1}] {r.title or getattr(r, 'url', None) or '?'}"
                for i, r in enumerate(result.references[:6])
            )
            answer += f"\n\n*Sources:*\n{refs}"
        return answer


async def _get_summary_async(notebook_id: str) -> str:
    from notebooklm import NotebookLMClient
    async with await NotebookLMClient.from_storage() as client:
        return await client.notebooks.get_summary(notebook_id) or ""


async def _generate_artifact_async(
    notebook_id: str, kind: str, output_path: Path
) -> bool:
    from notebooklm import NotebookLMClient
    from notebooklm.rpc.types import ReportFormat, SlideDeckFormat

    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with await NotebookLMClient.from_storage() as client:
        try:
            if kind == "report":
                status = await client.artifacts.generate_report(
                    notebook_id, report_format=ReportFormat.BRIEFING_DOC
                )
                if not status or status.is_failed:
                    return False
                final = await client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=300
                )
                if not final.is_complete:
                    return False
                await client.artifacts.download_report(
                    notebook_id, str(output_path), status.task_id
                )
                return True

            elif kind == "slides":
                status = await client.artifacts.generate_slide_deck(
                    notebook_id, slide_format=SlideDeckFormat.DETAILED_DECK
                )
                if not status or status.is_failed:
                    return False
                final = await client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=300
                )
                if not final.is_complete:
                    return False
                await client.artifacts.download_slide_deck(
                    notebook_id, str(output_path), status.task_id
                )
                return True

            elif kind == "mind_map":
                status = await client.artifacts.generate_mind_map(notebook_id)
                if not status or status.is_failed:
                    return False
                final = await client.artifacts.wait_for_completion(
                    notebook_id, status.task_id, timeout=300
                )
                if not final.is_complete:
                    return False
                await client.artifacts.download_mind_map(
                    notebook_id, str(output_path), status.task_id
                )
                return True

        except Exception as e:
            print(f"  [NLM] artifact({kind}) error: {e}", file=sys.stderr)
            return False

    return False


# ── Public sync facade ────────────────────────────────────────────────────────

class NLMClient:
    """Sync facade over NotebookLMClient for pipeline agents.

    Every method is safe to call even when notebooklm-py is not installed
    or auth has expired — it returns None/empty/False gracefully so agents
    can fall back to their KB-only path.
    """

    @staticmethod
    def available() -> bool:
        return _available()

    @staticmethod
    def create_notebook(title: str) -> str | None:
        """Create a notebook and return its ID, or None on failure."""
        if not _available():
            return None
        try:
            return asyncio.run(_create_notebook_async(title))
        except Exception as e:
            print(f"  [NLM] create_notebook: {e}", file=sys.stderr)
            return None

    @staticmethod
    def add_sources(
        notebook_id: str,
        urls: list[str],
        pdf_paths: list[Path] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """Add URLs and local PDFs to a notebook; wait for processing.

        Returns (loaded, failed) where each item is a dict with 'source',
        'status', and optionally 'source_id' or 'reason'.
        """
        if not notebook_id or not _available():
            return [], [{"source": u, "reason": "NLM unavailable"} for u in (urls or [])]
        try:
            return asyncio.run(
                _add_sources_async(notebook_id, urls or [], pdf_paths or [])
            )
        except Exception as e:
            print(f"  [NLM] add_sources: {e}", file=sys.stderr)
            return [], [{"source": u, "reason": str(e)[:80]} for u in (urls or [])]

    @staticmethod
    def ask(notebook_id: str, question: str, mode: str = "detailed") -> str:
        """Ask a question; returns answer text with inline citations."""
        if not notebook_id or not _available():
            return "[NotebookLM unavailable]"
        try:
            return asyncio.run(_ask_async(notebook_id, question, mode)) or "[no response]"
        except Exception as e:
            return f"[NLM ask error: {e}]"

    @staticmethod
    def get_notebook_summary(notebook_id: str) -> str:
        """Return the AI-generated notebook summary, or empty string."""
        if not notebook_id or not _available():
            return ""
        try:
            return asyncio.run(_get_summary_async(notebook_id))
        except Exception:
            return ""

    @staticmethod
    def generate_artifact(notebook_id: str, kind: str, output_path: Path) -> bool:
        """Generate and download a NotebookLM artifact.

        kind: 'report' | 'slides' | 'mind_map'
        Returns True on success, False on failure.
        """
        if not notebook_id or not _available():
            return False
        try:
            return asyncio.run(_generate_artifact_async(notebook_id, kind, output_path))
        except Exception as e:
            print(f"  [NLM] generate_artifact({kind}): {e}", file=sys.stderr)
            return False
