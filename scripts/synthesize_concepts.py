#!/usr/bin/env python3
"""
Concept synthesizer: gathers findings from wiki pages and writes an
expert-level 'State of the Art' synthesis for each concept.

Usage:
    python scripts/synthesize_concepts.py --concept "MACE" --keywords "MACE equivariant GNN"
    python scripts/synthesize_concepts.py --all      # synthesize all hub concepts

Requires: MISTRAL_API_KEY  (or LLM_BACKEND=gemini with GEMINI_API_KEY)
"""
import argparse
import os
import re
import sys
import yaml
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
WIKI_DIR = PROJECT_ROOT / "wiki"
CONCEPTS_DIR = WIKI_DIR / "concepts"

# ── Load env ─────────────────────────────────────────────────────────────────

_bash_env = Path.home() / ".bash_env"
if _bash_env.exists():
    for _line in _bash_env.read_text().splitlines():
        if _line.startswith("export ") and "=" in _line:
            _k, _, _v = _line[len("export "):].partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

_dot_env = PROJECT_ROOT / ".env"
if _dot_env.exists():
    for _line in _dot_env.read_text().splitlines():
        if _line.strip() and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(prompt: str) -> str:
    backend = os.environ.get("LLM_BACKEND", "mistral")

    if backend == "mistral":
        import requests
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise EnvironmentError("MISTRAL_API_KEY not set.")
        resp = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": os.environ.get("MISTRAL_MODEL", "mistral-large-latest"),
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    if backend == "gemini":
        import requests
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY not set.")
        model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    if backend == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    raise EnvironmentError(f"Unknown LLM_BACKEND: {backend}")


# ── Synthesis ─────────────────────────────────────────────────────────────────

def synthesize_concept(concept_name: str, keywords: list[str]) -> None:
    print(f"Synthesizing: {concept_name}...")
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)

    raw_findings: list[str] = []
    sources: list[str] = []

    for f in sorted(WIKI_DIR.glob("*.md")):
        if f.name in ("index.md",) or "hub" in f.name or "concepts" in str(f.parts):
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        if f"[[{concept_name}]]" in content or any(kw.lower() in content.lower() for kw in keywords):
            sources.append(f.stem)
            m = re.search(r"### .*?Key Findings(.*?)(?:###|$)", content, re.DOTALL | re.IGNORECASE)
            if m:
                raw_findings.append(f"SOURCE [[{f.stem}]]:\n{m.group(1).strip()}")
            else:
                # Fallback: take first 1500 chars of body
                body = re.sub(r"^---.*?---\s*", "", content, count=1, flags=re.DOTALL).strip()
                raw_findings.append(f"SOURCE [[{f.stem}]]:\n{body[:1500]}")

    if not raw_findings:
        print(f"  No data found for '{concept_name}' — skipping.")
        return

    compiled = "\n\n".join(raw_findings)
    if len(compiled) > 15_000:
        compiled = compiled[:15_000] + "\n... (truncated)"

    prompt = (
        f"You are a senior materials scientist / ML researcher.\n"
        f"Below are findings from multiple papers regarding: {concept_name}\n\n"
        "TASK: Write a cohesive, expert-level 'State of the Art' summary.\n"
        "- Do NOT just list papers. Synthesize trends and contradictions.\n"
        "- Use LaTeX for all formulas and units.\n"
        "- Keep the tone academic and precise.\n\n"
        "OUTPUT FORMAT (Markdown only):\n"
        "## Overview\n"
        "## Current Trends\n"
        "## Quantitative Comparison\n"
        "## Open Questions\n"
        "## Strategic Outlook\n\n"
        f"FINDINGS:\n{compiled}"
    )

    synthesis_md = _call_llm(prompt)

    ts = datetime.now().strftime("%Y-%m-%d")
    fm = {
        "title": f"{concept_name} — State of the Art",
        "type": "synthesis",
        "concept": concept_name,
        "sources": sources[:30],
        "last_updated": ts,
        "generated_by": "synthesize_concepts.py",
    }
    content = (
        f"---\n{yaml.dump(fm, sort_keys=False, allow_unicode=True)}---\n\n"
        f"# {concept_name}: State of the Art\n\n"
        f"{synthesis_md}\n\n"
        f"---\n## Integrated Sources\n"
        + "".join(f"- [[{s}]]\n" for s in sources[:30])
    )

    slug = re.sub(r"[^\w-]", "-", concept_name.lower()).strip("-")
    output_path = CONCEPTS_DIR / f"{slug}-synthesis.md"
    output_path.write_text(content, encoding="utf-8")
    print(f"  → {output_path.relative_to(PROJECT_ROOT)}")


def _concepts_from_hubs() -> dict[str, list[str]]:
    """Extract concept names from hub pages."""
    concepts: dict[str, list[str]] = {}
    for hub in sorted(WIKI_DIR.glob("hub-*.md")):
        content = hub.read_text(encoding="utf-8", errors="ignore")
        links = re.findall(r"\[\[([^\]|]+)\]\]", content)
        if links:
            name = hub.stem.replace("hub-", "").replace("-", " ").title()
            concepts[name] = links[:5]
    return concepts


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--concept", help="Concept name to synthesize")
    parser.add_argument("--keywords", nargs="+", default=[],
                        help="Keywords to search for in wiki pages")
    parser.add_argument("--all", action="store_true",
                        help="Synthesize all concepts from hub pages")
    args = parser.parse_args()

    if args.all:
        concepts = _concepts_from_hubs()
        if not concepts:
            print("No hub pages found. Run 'wiki-manager make-hubs' first.")
            sys.exit(1)
        for name, kws in concepts.items():
            synthesize_concept(name, kws)
    elif args.concept:
        synthesize_concept(args.concept, args.keywords or [args.concept])
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
