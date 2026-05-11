import os
import time
from pathlib import Path

ANTHROPIC_MODEL = "claude-sonnet-4-6"
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
PIPELINE_LLM_BACKEND = os.environ.get("PIPELINE_LLM_BACKEND", "anthropic")


class BaseAgent:
    def __init__(self, client, pipeline_dir: Path):
        self.client = client
        self.pipeline_dir = pipeline_dir
        self.handoffs_dir = pipeline_dir / "handoffs"

    def _read_handoff(self, name: str) -> str:
        path = self.handoffs_dir / f"handoff_{name}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _write_handoff(self, name: str, content: str):
        self.handoffs_dir.mkdir(exist_ok=True)
        (self.handoffs_dir / f"handoff_{name}.md").write_text(content, encoding="utf-8")

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
                    wait = 60 * (attempt + 1)
                    print(f"  Rate limited — waiting {wait}s before retry {attempt + 1}/3...")
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("Mistral rate limit exceeded after 3 retries.")

    def run(self, state: dict) -> dict:
        raise NotImplementedError
