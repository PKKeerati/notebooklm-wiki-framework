from __future__ import annotations
import os
import re
import json
import time
import requests
from pathlib import Path

ANTHROPIC_MODEL = "claude-sonnet-4-6"
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
PIPELINE_LLM_BACKEND = os.environ.get("PIPELINE_LLM_BACKEND", "anthropic")

_MISTRAL_CHAT = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_EMBED = "https://api.mistral.ai/v1/embeddings"


class BaseAgent:
    def __init__(self, client, pipeline_dir: Path):
        self.client = client
        self.pipeline_dir = pipeline_dir
        self.handoffs_dir = pipeline_dir / "handoffs"
        self._vectors_cache: dict | None = None

    # ── Handoff I/O ───────────────────────────────────────────────────────────

    def _read_handoff(self, name: str) -> str:
        path = self.handoffs_dir / f"handoff_{name}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _write_handoff(self, name: str, content: str):
        self.handoffs_dir.mkdir(exist_ok=True)
        (self.handoffs_dir / f"handoff_{name}.md").write_text(content, encoding="utf-8")

    # ── LLM dispatch ──────────────────────────────────────────────────────────

    def _llm(self, system: str, user: str, max_tokens: int = 2000) -> str:
        if PIPELINE_LLM_BACKEND == "mistral":
            return self._llm_mistral(system, user, max_tokens)
        return self._llm_anthropic(system, user, max_tokens)

    def _llm_anthropic(self, system: str, user: str, max_tokens: int = 2000) -> str:
        """Call Claude with prompt caching on the system prompt."""
        resp = self.client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    def _llm_mistral(self, system: str, user: str, max_tokens: int = 2000) -> str:
        sleep_s = int(os.environ.get("MISTRAL_SLEEP", "2"))
        for attempt in range(4):
            try:
                resp = self.client.chat.complete(
                    model=MISTRAL_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=max_tokens,
                )
                time.sleep(sleep_s)
                return resp.choices[0].message.content
            except Exception as e:
                if "429" in str(e) or "rate_limited" in str(e).lower():
                    import random
                    wait = 60 * (attempt + 1) + random.uniform(0, 10)
                    print(f"  Rate limited — waiting {wait:.0f}s before retry {attempt + 1}/3...")
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("Mistral rate limit exceeded after 3 retries.")

    # ── KB vector search ──────────────────────────────────────────────────────

    def _load_vectors(self, wiki_dir: Path) -> dict:
        if self._vectors_cache is None:
            vector_file = wiki_dir / ".vectors.json"
            if vector_file.exists():
                try:
                    self._vectors_cache = json.loads(vector_file.read_text(encoding="utf-8"))
                except Exception:
                    self._vectors_cache = {}
            else:
                self._vectors_cache = {}
        return self._vectors_cache

    def _embed(self, text: str) -> list[float]:
        """Embed text via Mistral API. Returns [] if unavailable."""
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            return []
        try:
            resp = requests.post(
                _MISTRAL_EMBED,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "mistral-embed", "input": text[:4096]},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except Exception:
            return []

    def semantic_search(self, query: str, wiki_dir: Path, top_k: int = 10) -> list[tuple[str, float]]:
        """Cosine-similarity search over .vectors.json. Falls back to keyword_search."""
        try:
            import numpy as np
            vectors = self._load_vectors(wiki_dir)
            if not vectors:
                return []
            q_vec = self._embed(query)
            if not q_vec:
                return []
            q = np.array(q_vec, dtype=float)
            scores = []
            for fname, data in vectors.items():
                v = np.array(data["vector"], dtype=float)
                score = float(np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v) + 1e-9))
                scores.append((fname, score))
            return sorted(scores, key=lambda x: x[1], reverse=True)[:top_k]
        except Exception:
            return []

    def graph_search(self, query: str, wiki_dir: Path, top_k: int = 12, hops: int = 2) -> list[tuple[str, float]]:
        """
        Multi-hop graph search: cosine similarity + wikilink traversal.
        Pages reachable from highly-relevant seeds get a connectivity bonus
        (0.30 for hop-1, 0.15 for hop-2) so adjacent pages surface even
        without direct keyword matches.
        """
        try:
            import numpy as np
            vectors = self._load_vectors(wiki_dir)
            if not vectors:
                return self.semantic_search(query, wiki_dir, top_k)

            q_vec = self._embed(query)
            if not q_vec:
                return self.keyword_search(query, wiki_dir, top_k)
            q = np.array(q_vec, dtype=float)

            base: dict[str, float] = {}
            for fname, data in vectors.items():
                v = np.array(data["vector"], dtype=float)
                base[fname] = float(np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v) + 1e-9))

            bonus: dict[str, float] = {f: 0.0 for f in base}
            seeds = sorted(base, key=lambda f: base[f], reverse=True)[:20]
            visited: set[str] = set(seeds)
            frontier: set[str] = set(seeds)

            for hop in range(1, hops + 1):
                decay = 0.30 / hop
                next_frontier: set[str] = set()
                for fname in frontier:
                    page = wiki_dir / fname
                    if not page.exists():
                        continue
                    content = page.read_text(encoding="utf-8", errors="ignore")
                    for link in self.extract_wikilinks(content):
                        linked = f"{link}.md"
                        if linked in base:
                            bonus[linked] = max(bonus[linked], decay * base[fname])
                            if linked not in visited:
                                next_frontier.add(linked)
                                visited.add(linked)
                frontier = next_frontier
                if not frontier:
                    break

            combined = {f: base[f] + bonus[f] for f in base}
            return sorted(combined.items(), key=lambda x: x[1], reverse=True)[:top_k]

        except Exception:
            return self.semantic_search(query, wiki_dir, top_k)

    def keyword_search(self, query: str, wiki_dir: Path, top_k: int = 10) -> list[tuple[str, float]]:
        """Simple term-frequency fallback search."""
        if not wiki_dir.exists():
            return []
        terms = set(query.lower().split())
        results = []
        for f in wiki_dir.glob("*.md"):
            if f.name == "index.md":
                continue
            content = f.read_text(encoding="utf-8", errors="ignore").lower()
            hits = sum(1 for t in terms if t in content)
            if hits:
                results.append((f.name, float(hits)))
        return sorted(results, key=lambda x: x[1], reverse=True)[:top_k]

    # ── Wiki helpers ──────────────────────────────────────────────────────────

    def read_wiki_page(self, name: str, wiki_dir: Path, max_chars: int = 2500) -> str:
        """Load a wiki page by stem or filename, with fuzzy fallback."""
        slug = re.sub(r"[\s_]+", "-", name)
        candidates = [
            wiki_dir / name,
            wiki_dir / f"{name}.md",
            wiki_dir / f"{slug}.md",
        ]
        for path in candidates:
            if path.exists():
                return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        # Partial stem match
        matches = [p for p in wiki_dir.glob("*.md") if name.split("-")[0].lower() in p.name.lower()]
        if matches:
            return matches[0].read_text(encoding="utf-8", errors="ignore")[:max_chars]
        return f"[Page not found: {name}]"

    @staticmethod
    def extract_wikilinks(text: str) -> list[str]:
        return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", text)

    # ── Audit trail ───────────────────────────────────────────────────────────

    @staticmethod
    def audit_log(wiki_dir: Path, agent: str, operation: str, details: str) -> None:
        from datetime import datetime
        log_path = wiki_dir / ".audit-log.md"
        if log_path.parent.exists():
            if not log_path.exists():
                log_path.write_text(
                    "# Audit Trail\n\n"
                    "| Timestamp | Agent | Operation | Details |\n"
                    "|-----------|-------|-----------|---------|",
                    encoding="utf-8",
                )
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            safe = details.replace("|", "∣").replace("\n", " ")[:120]
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n| {ts} | {agent} | {operation} | {safe} |")

    def run(self, state: dict) -> dict:
        raise NotImplementedError
