#!/usr/bin/env python3
"""
NotebookLM-Wiki Pipeline Orchestrator

Usage:
    python pipeline/orchestrator.py start "What are the best ML potentials for HEA?"
    python pipeline/orchestrator.py resume
    python pipeline/orchestrator.py status
    python pipeline/orchestrator.py reset
"""

import argparse
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

# Force UTF-8 I/O on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load API keys from ~/.bash_env if not already in environment
_bash_env = Path.home() / ".bash_env"
if _bash_env.exists():
    for _line in _bash_env.read_text().splitlines():
        if _line.startswith("export ") and "=" in _line:
            _k, _, _v = _line[len("export "):].partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

# Also load from .env in the project root
_dot_env = Path(__file__).parent.parent / ".env"
if _dot_env.exists():
    for _line in _dot_env.read_text().splitlines():
        if _line.strip() and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# Resolve imports whether run as script or module
sys.path.insert(0, str(Path(__file__).parent))

import anthropic
from agents.base import PIPELINE_LLM_BACKEND
from agents import (
    DaoAgent, BuilderAgent, CherryAgent, NamAgent,
    SomAgent, ManaoAgent, ModAgent, ChompooAgent, NannyAgent,
)

PIPELINE_DIR = Path(__file__).parent
STATE_FILE = PIPELINE_DIR / "pipeline_state.json"
HANDOFFS_DIR = PIPELINE_DIR / "handoffs"
PROJECT_ROOT = PIPELINE_DIR.parent


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def new_state(pk_input: str) -> dict:
    return {
        "run_id": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "pk_input": pk_input,
        "status": "running",
        "current_step": "start",
        "pk_direction_selection": None,
        "pk_output_format": None,
        "revision_count": 0,
        "som_verdict": None,
        "manao_verdict": None,
        "needs_revision": False,
        "checkpoint_history": {
            "cp1": {"presented": False, "approved": False},
            "cp2": {"presented": False, "approved": False},
            "cp3": {"presented": False, "approved": False},
        },
        "completed_agents": [],
        "failed_sources": [],
        "notebook_id": None,
        "output_files": [],
        "wiki_root": str(PROJECT_ROOT / "wiki"),
        "output_root": str(PROJECT_ROOT / "output"),
    }


# ── UI helpers ────────────────────────────────────────────────────────────────

def _sep(char: str = "─", width: int = 62) -> str:
    return char * width


def _banner(n: int, title: str) -> None:
    print(f"\n{_sep('═')}")
    print(f"  CHECKPOINT {n} — {title}")
    print(_sep("═"))


def _step(name: str, msg: str) -> None:
    print(f"\n▶  {name}: {msg}")


def _ok(msg: str) -> None:
    print(f"✓  {msg}")


def _warn(msg: str) -> None:
    print(f"⚠  {msg}", file=sys.stderr)


def _err(msg: str) -> None:
    print(f"✗  {msg}", file=sys.stderr)


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(self) -> None:
        if PIPELINE_LLM_BACKEND == "mistral":
            api_key = os.environ.get("MISTRAL_API_KEY")
            if not api_key:
                _err("MISTRAL_API_KEY not set. Export it and retry.")
                sys.exit(1)
            try:
                from mistralai import Mistral
            except ImportError:
                _err("mistralai not installed. Run: pip install mistralai")
                sys.exit(1)
            self.client = Mistral(api_key=api_key)
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                _err("ANTHROPIC_API_KEY not set. Export it and retry.")
                sys.exit(1)
            self.client = anthropic.Anthropic(api_key=api_key)
        HANDOFFS_DIR.mkdir(exist_ok=True)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self, state: dict) -> None:
        dispatch = {
            "start":                  self._step_dao,
            "dao_complete":           self._checkpoint_1,
            "cp1_approved":           self._step_builder,
            "builder_complete":       self._step_cherry,
            "cherry_complete":        self._step_nam,
            "nam_complete":           self._checkpoint_2,
            "cp2_approved":           self._step_review,
            "review_needs_revision":  self._step_nam_revision,
            "review_complete":        self._step_mod,
            "mod_complete":           self._step_chompoo,
            "chompoo_complete":       self._checkpoint_3,
            "cp3_approved":           self._step_nanny,
        }

        terminal = {"complete", "cancelled", "error", "paused", "awaiting_cp1", "awaiting_cp2", "awaiting_cp3"}

        while state["status"] not in terminal:
            fn = dispatch.get(state["current_step"])
            if fn is None:
                _err(f"Unknown step: {state['current_step']}")
                state["status"] = "error"
                break
            try:
                state = fn(state)
                save_state(state)
            except KeyboardInterrupt:
                print("\n\nPaused by user. Run 'resume' to continue.")
                state["status"] = "paused"
                save_state(state)
                return
            except Exception as exc:
                _err(f"Step '{state['current_step']}' failed: {exc}")
                state["status"] = "error"
                state["error"] = str(exc)
                save_state(state)
                raise

        if state["status"] == "complete":
            print(f"\n{_sep()}")
            print("  Pipeline complete.")
            print(_sep())

    # ── Agent steps ───────────────────────────────────────────────────────────

    def _step_dao(self, state: dict) -> dict:
        _step("Dao", "Scanning KB and identifying gap...")
        DaoAgent(self.client, PIPELINE_DIR).run(state)
        state["current_step"] = "dao_complete"
        state["completed_agents"].append("dao")
        return state

    def _step_builder(self, state: dict) -> dict:
        _step("Builder", "Creating NotebookLM notebook and loading sources...")
        result = BuilderAgent(self.client, PIPELINE_DIR).run(state)
        state.update(result)
        state["current_step"] = "builder_complete"
        state["completed_agents"].append("builder")
        if result.get("failed_sources"):
            _warn(f"{len(result['failed_sources'])} source(s) failed — pipeline continues.")
        return state

    def _step_cherry(self, state: dict) -> dict:
        _step("Cherry", "Shaping questions and querying NotebookLM...")
        CherryAgent(self.client, PIPELINE_DIR).run(state)
        state["current_step"] = "cherry_complete"
        state["completed_agents"].append("cherry")
        return state

    def _step_nam(self, state: dict) -> dict:
        _step("Nam", "Synthesising research and proposing directions...")
        NamAgent(self.client, PIPELINE_DIR).run(state)
        state["current_step"] = "nam_complete"
        if "nam" not in state["completed_agents"]:
            state["completed_agents"].append("nam")
        return state

    def _step_review(self, state: dict) -> dict:
        _step("Som + Manao", "Critic and fact audit running in parallel...")
        som_result: dict = {}
        manao_result: dict = {}
        exc_holder: list = [None, None]

        def _run_som():
            try:
                som_result.update(SomAgent(self.client, PIPELINE_DIR).run(state))
            except Exception as e:
                exc_holder[0] = e

        def _run_manao():
            try:
                manao_result.update(ManaoAgent(self.client, PIPELINE_DIR).run(state))
            except Exception as e:
                exc_holder[1] = e

        t1 = threading.Thread(target=_run_som, daemon=True)
        t2 = threading.Thread(target=_run_manao, daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()

        if exc_holder[0]:
            raise exc_holder[0]
        if exc_holder[1]:
            raise exc_holder[1]

        state.update(som_result)
        state.update(manao_result)
        for agent in ("som", "manao"):
            if agent not in state["completed_agents"]:
                state["completed_agents"].append(agent)

        sv = som_result.get("som_verdict", "PASS")
        mv = manao_result.get("manao_verdict", "PASS")
        _ok(f"Som: {sv}  |  Manao: {mv}")

        needs_revision = sv == "REVISE" or mv == "REVISE"

        if needs_revision:
            rev = state["revision_count"]
            if rev >= 2:
                _warn("Revision limit reached (2/2). Issues still flagged.")
                print(f"\n  {_sep()}")
                print("  A) Let Nam try once more")
                print("  B) Proceed to Mod anyway")
                print("  C) Abort pipeline")
                print(f"  {_sep()}")
                while True:
                    choice = input("  Choice [A/B/C]: ").strip().upper()
                    if choice == "A":
                        state["revision_count"] += 1
                        state["needs_revision"] = True
                        state["current_step"] = "review_needs_revision"
                        break
                    elif choice == "B":
                        state["needs_revision"] = False
                        state["current_step"] = "review_complete"
                        break
                    elif choice == "C":
                        state["status"] = "cancelled"
                        state["current_step"] = "cancelled"
                        break
            else:
                state["revision_count"] += 1
                state["needs_revision"] = True
                state["current_step"] = "review_needs_revision"
                print(f"  Routing back to Nam for revision {state['revision_count']}/2...")
        else:
            state["needs_revision"] = False
            state["current_step"] = "review_complete"

        return state

    def _step_nam_revision(self, state: dict) -> dict:
        _step("Nam", f"Revising synthesis (attempt {state['revision_count']}/2)...")
        NamAgent(self.client, PIPELINE_DIR).run(state)
        state["current_step"] = "cp2_approved"  # re-enter review loop
        return state

    def _step_mod(self, state: dict) -> dict:
        _step("Mod", "Extracting atomic insights and writing to KB...")
        result = ModAgent(self.client, PIPELINE_DIR).run(state)
        state.update(result)
        state["current_step"] = "mod_complete"
        state["completed_agents"].append("mod")
        updated = result.get("kb_pages_updated", [])
        created = result.get("kb_pages_created", [])
        if updated:
            _ok(f"KB pages updated: {', '.join(updated)}")
        if created:
            _ok(f"KB pages created: {', '.join(created)}")
        return state

    def _step_chompoo(self, state: dict) -> dict:
        _step("Chompoo", "Verifying insights against Semantic Scholar...")
        result = ChompooAgent(self.client, PIPELINE_DIR).run(state)
        state.update(result)
        state["current_step"] = "chompoo_complete"
        state["completed_agents"].append("chompoo")
        verified = result.get("chompoo_verified", 0)
        total = result.get("chompoo_total_done", 0)
        _ok(f"Citations verified: {verified}/{total}")
        return state

    def _step_nanny(self, state: dict) -> dict:
        _step("Nanny", "Writing output...")
        result = NannyAgent(self.client, PIPELINE_DIR).run(state)
        state.update(result)
        state["current_step"] = "nanny_complete"
        state["status"] = "complete"
        state["completed_agents"].append("nanny")

        # Auto-crystallize into wiki/concepts/ only when audit passed
        som_ok = state.get("som_verdict", "PASS") == "PASS"
        manao_ok = state.get("manao_verdict", "PASS") == "PASS"
        if som_ok and manao_ok:
            _step("Crystallize", "Auto-writing insights to wiki/concepts/...")
            try:
                sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
                from wiki_manager import WikiManager
                mgr = WikiManager()
                if hasattr(mgr, "crystallize"):
                    run_id = state["run_id"].replace(":", "-").replace("T", "_")
                    output_dir = PROJECT_ROOT / "output" / state["run_id"][:10]
                    research_path = output_dir / f"research_{run_id}.md"
                    if research_path.exists():
                        mgr.crystallize(str(research_path))
                        _ok("Crystallized into wiki/concepts/")
                    else:
                        _ok("wiki/concepts/ already updated by Mod")
            except Exception as e:
                _warn(f"Crystallize skipped: {e}")
        else:
            _warn("Audit verdict was REVISE — crystallize skipped. Review and run manually.")

        output_dir = PROJECT_ROOT / "output" / state["run_id"][:10]
        print(f"\n{_sep()}")
        print(f"  Pipeline complete.")
        print(f"  Output → {output_dir}/")
        for f in sorted(output_dir.glob("*.md")) if output_dir.exists() else []:
            print(f"    {f.name}")
        print(_sep())
        return state

    # ── Checkpoints ───────────────────────────────────────────────────────────

    def _checkpoint_1(self, state: dict) -> dict:
        handoff_text = (HANDOFFS_DIR / "handoff_dao.md").read_text(encoding="utf-8")
        choice = state.pop("_cp1_response", None)
        if choice is None:
            _banner(1, "Source Plan Approval")
            print(handoff_text)
            print(_sep())
            print("  Waiting for your response via 'respond' command.")
            print(_sep())
            state["status"] = "awaiting_cp1"
            return state

        choice = choice.strip().upper()
        _banner(1, "Source Plan Approval")
        if choice == "A":
            state["checkpoint_history"]["cp1"] = {"presented": True, "approved": True}
            state["current_step"] = "cp1_approved"
            _ok("Source plan approved.")
        elif choice.startswith("E"):
            edits = choice[1:].strip().lstrip(":").strip()
            state["source_edits"] = edits
            state["checkpoint_history"]["cp1"] = {"presented": True, "approved": True, "edits": edits}
            state["current_step"] = "cp1_approved"
            _ok(f"Source plan edited: {edits}")
        elif choice == "C":
            state["status"] = "cancelled"
            state["current_step"] = "cancelled"
            print("  Pipeline cancelled.")
        return state

    def _checkpoint_2(self, state: dict) -> dict:
        handoff_text = (HANDOFFS_DIR / "handoff_nam.md").read_text(encoding="utf-8")
        choice = state.pop("_cp2_response", None)
        if choice is None:
            _banner(2, "Direction Selection")
            print(handoff_text)
            print(_sep())
            print("  Examples:  '1,3'  |  'all'  |  '2: skip simulation part'")
            print("  Waiting for your response via 'respond' command.")
            print(_sep())
            state["status"] = "awaiting_cp2"
            return state

        _banner(2, "Direction Selection")
        state["pk_direction_selection"] = choice.strip()
        state["checkpoint_history"]["cp2"] = {"presented": True, "approved": True, "selection": choice}
        state["current_step"] = "cp2_approved"
        _ok(f"Selected: {choice}")
        return state

    def _checkpoint_3(self, state: dict) -> dict:
        handoff_text = (HANDOFFS_DIR / "handoff_mod.md").read_text(encoding="utf-8")
        choice = state.pop("_cp3_response", None)
        if choice is None:
            _banner(3, "Output Format")
            print(handoff_text)
            print(_sep())
            print("  A) Report only   B) Slides   C) Obsidian   D) Report+Obsidian")
            print("  E) All   F) Excalidraw   G) Report+Obsidian+Excalidraw   H) LaTeX")
            print("  Waiting for your response via 'respond' command.")
            print(_sep())
            state["status"] = "awaiting_cp3"
            return state

        fmt = choice.strip()
        if not fmt or fmt[0].upper() not in "ABCDEFGH":
            _err(f"Invalid format choice '{fmt}'. Use A/B/C/D/E.")
            state["status"] = "awaiting_cp3"
            return state

        _banner(3, "Output Format")
        state["pk_output_format"] = fmt
        state["checkpoint_history"]["cp3"] = {"presented": True, "approved": True, "format": fmt}
        state["current_step"] = "cp3_approved"
        _ok(f"Format: {fmt}")
        return state


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cmd_start(args: argparse.Namespace) -> None:
    orch = Orchestrator()
    state = new_state(args.question)

    # Clear handoffs from previous run
    for f in HANDOFFS_DIR.glob("handoff_*.md"):
        f.unlink()

    save_state(state)
    print(_sep())
    print(f"  Run ID:   {state['run_id']}")
    print(f"  Question: {state['pk_input']}")
    print(_sep())
    orch.run(state)


def _cmd_resume(_args: argparse.Namespace) -> None:
    state = load_state()
    if not state:
        _err("No saved run found. Use 'start' to begin.")
        sys.exit(1)
    if state["status"] == "complete":
        print("Last run is already complete. Use 'start' for a new run.")
        sys.exit(0)
    if state["status"].startswith("awaiting_"):
        cp = state["status"].replace("awaiting_", "").upper()
        print(f"  Pipeline is paused at {cp}. Use 'respond <choice>' to continue.")
        sys.exit(0)
    state["status"] = "running"
    print(_sep())
    print(f"  Resuming run: {state['run_id']}")
    print(f"  Question:     {state['pk_input']}")
    print(f"  From step:    {state['current_step']}")
    print(_sep())
    Orchestrator().run(state)


def _cmd_respond(args: argparse.Namespace) -> None:
    state = load_state()
    if not state:
        _err("No saved run found.")
        sys.exit(1)
    status = state.get("status", "")
    cp_map = {
        "awaiting_cp1": "_cp1_response",
        "awaiting_cp2": "_cp2_response",
        "awaiting_cp3": "_cp3_response",
    }
    key = cp_map.get(status)
    if not key:
        _err(f"Pipeline is not awaiting a checkpoint (status: {status}).")
        sys.exit(1)
    state[key] = args.choice
    state["status"] = "running"
    save_state(state)
    print(_sep())
    print(f"  Injecting response: {args.choice}")
    print(_sep())
    Orchestrator().run(state)


def _cmd_status(_args: argparse.Namespace) -> None:
    state = load_state()
    if not state:
        print("No run found.")
        return
    print(_sep())
    print(f"  Run ID:    {state['run_id']}")
    print(f"  Question:  {state['pk_input']}")
    print(f"  Status:    {state['status']}")
    print(f"  Step:      {state['current_step']}")
    print(f"  Done:      {', '.join(state['completed_agents']) or 'none'}")
    print(f"  Revisions: {state['revision_count']}")
    if state.get("error"):
        print(f"  Error:     {state['error']}")
    print(_sep())


def _cmd_reset(args: argparse.Namespace) -> None:
    if getattr(args, "yes", False):
        confirm = "y"
    elif sys.stdin.isatty():
        confirm = input("Reset deletes current state and all handoffs. Confirm? [y/N] ")
    else:
        _err("Reset requires --yes flag when running non-interactively.")
        sys.exit(1)
    if confirm.strip().lower() == "y":
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        for f in HANDOFFS_DIR.glob("handoff_*.md"):
            f.unlink()
        print("Reset complete.")
    else:
        print("Cancelled.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NotebookLM-Wiki Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python pipeline/orchestrator.py start \"Best ML potentials for HEA?\"\n"
            "  python pipeline/orchestrator.py resume\n"
            "  python pipeline/orchestrator.py status\n"
            "  python pipeline/orchestrator.py reset\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start a new pipeline run")
    p_start.add_argument("question", help="Research question or idea")
    p_start.set_defaults(func=_cmd_start)

    p_resume = sub.add_parser("resume", help="Resume the last paused/interrupted run")
    p_resume.set_defaults(func=_cmd_resume)

    p_status = sub.add_parser("status", help="Show current pipeline status")
    p_status.set_defaults(func=_cmd_status)

    p_reset = sub.add_parser("reset", help="Clear state and handoffs")
    p_reset.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    p_reset.set_defaults(func=_cmd_reset)

    p_respond = sub.add_parser("respond", help="Respond to a paused checkpoint")
    p_respond.add_argument("choice", help="Your checkpoint response (e.g. 'A', '1,3', 'D')")
    p_respond.set_defaults(func=_cmd_respond)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
