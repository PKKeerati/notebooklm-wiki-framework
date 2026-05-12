#!/usr/bin/env python3
"""
Auto-pilot: run the pipeline in non-interactive batch mode.

Usage:
    python scripts/auto_pilot.py --runs 5
    python scripts/auto_pilot.py --topic "MLIP for hydrogen storage" --runs 1
    python scripts/auto_pilot.py --topics-file topics.txt --runs 3

In auto mode (no --topic), asks Mistral to generate a research question
based on the hub pages in your wiki.

Requires:
    MISTRAL_API_KEY  (or ANTHROPIC_API_KEY)
    PIPELINE_LLM_BACKEND (defaults to "anthropic")
"""
import argparse
import json
import os
import subprocess
import sys
import time
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PIPELINE_SCRIPT = PROJECT_ROOT / "pipeline" / "orchestrator.py"
WIKI_DIR = PROJECT_ROOT / "wiki"

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


# ── Topic generation ─────────────────────────────────────────────────────────

def _mistral_topic(hubs: list[str]) -> str:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        return "What are the most promising directions in ML interatomic potentials?"
    hub_names = ", ".join(hubs[:10]) or "materials science"
    prompt = (
        f"Based on these research hubs: {hub_names}, "
        "suggest one highly specific, complex research question for a materials scientist / "
        "ML potentials researcher to investigate. Return ONLY the question, no preamble."
    )
    try:
        resp = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "mistral-small-latest",
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip().strip('"')
    except Exception as e:
        print(f"  [AutoPilot] Topic generation failed: {e} — using fallback topic.")
        return "What are the most promising directions in ML interatomic potentials?"


def _get_hub_names() -> list[str]:
    if not WIKI_DIR.exists():
        return []
    return [f.stem for f in sorted(WIKI_DIR.glob("hub-*.md"))]


def _load_topics_file(path: str) -> list[str]:
    return [l.strip() for l in Path(path).read_text().splitlines()
            if l.strip() and not l.startswith("#")]


# ── Pipeline runner ───────────────────────────────────────────────────────────

def run_batch(topics: list[str], cooldown: int = 10) -> None:
    for i, topic in enumerate(topics, 1):
        print(f"\n{'=' * 60}")
        print(f"  AUTO-PILOT MISSION {i}/{len(topics)}")
        print(f"  {topic}")
        print("=" * 60)

        # Reset previous state
        subprocess.run(
            [sys.executable, str(PIPELINE_SCRIPT), "reset", "--yes"],
            cwd=PROJECT_ROOT,
        )

        # Start new run — inject approvals for all three checkpoints automatically
        # by pre-seeding the state with auto-approved responses
        state = {
            "run_id": "",  # will be set by start
            "_auto_pilot": True,
            "_cp1_response": "A",   # approve source plan
            "_cp2_response": "all", # select all directions
            "_cp3_response": "D",   # report + Obsidian
        }
        state_file = PROJECT_ROOT / "pipeline" / "pipeline_state.json"

        # Start the pipeline (it will read pre-seeded state after Dao runs)
        proc = subprocess.run(
            [sys.executable, str(PIPELINE_SCRIPT), "start", topic],
            cwd=PROJECT_ROOT,
        )
        if proc.returncode != 0:
            print(f"  [AutoPilot] Mission {i} failed — continuing to next.")

        if i < len(topics):
            print(f"\n  Cooling down {cooldown}s before next mission...")
            time.sleep(cooldown)

    print(f"\n{'=' * 60}")
    print(f"  AUTO-PILOT COMPLETE — {len(topics)} missions run.")
    print("=" * 60)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", help="Single research question to run")
    parser.add_argument("--topics-file", help="File with one topic per line")
    parser.add_argument("--runs", type=int, default=3,
                        help="Number of auto-generated topics to run (default: 3)")
    parser.add_argument("--cooldown", type=int, default=10,
                        help="Seconds between missions (default: 10)")
    args = parser.parse_args()

    if args.topic:
        topics = [args.topic]
    elif args.topics_file:
        topics = _load_topics_file(args.topics_file)
        if not topics:
            print("Error: topics file is empty.")
            sys.exit(1)
    else:
        print(f"Generating {args.runs} research questions from hub pages...")
        hubs = _get_hub_names()
        topics = [_mistral_topic(hubs) for _ in range(args.runs)]
        for i, t in enumerate(topics, 1):
            print(f"  {i}. {t}")

    run_batch(topics, cooldown=args.cooldown)


if __name__ == "__main__":
    main()
