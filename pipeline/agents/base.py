from pathlib import Path
import anthropic

MODEL = "claude-sonnet-4-6"


class BaseAgent:
    def __init__(self, client: anthropic.Anthropic, pipeline_dir: Path):
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
        """Call Claude with prompt caching on the system prompt."""
        resp = self.client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    def run(self, state: dict) -> dict:
        raise NotImplementedError
