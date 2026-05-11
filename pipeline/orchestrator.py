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

# Resolve imports whether run as script or module
sys.path.insert(0, str(Path(__file__).parent))

import anthropic
from agents.base import PIPELINE_LLM_BACKEND
from agents import (
    DaoAgent, BuilderAgent, CherryAgent, NamAgent,
    SomAgent, ManaoAgent, ModAgent, NannyAgent,
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
            "mod_complete":           self._checkpoint_3,
            "cp3_approved":           self._step_nanny,
        }

        terminal = {"complete", "cancelled", "error", "paused"}

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

    def _step_nanny(self, state: dict) -> dict:
        _step("Nanny", "Writing output...")
        result = NannyAgent(self.client, PIPELINE_DIR).run(state)
        state.update(result)
        state["current_step"] = "nanny_complete"
        state["status"] = "complete"
        state["completed_agents"].append("nanny")
        return state

    # ── Checkpoints ───────────────────────────────────────────────────────────

    def _checkpoint_1(self, state: dict) -> dict:
        handoff_text = (HANDOFFS_DIR / "handoff_dao.md").read_text(encoding="utf-8")
        _banner(1, "Source Plan Approval")
        print(handoff_text)
        print(_sep())
        print("  A) Approve as-is")
        print("  E) Edit source list (remove numbers or paste extra URLs)")
        print("  C) Cancel")
        print(_sep())

        while True:
            choice = input("\n  Your choice: ").strip().upper()
            if choice == "A":
                state["checkpoint_history"]["cp1"] = {"presented": True, "approved": True}
                state["current_step"] = "cp1_approved"
                _ok("Source plan approved.")
                return state
            elif choice == "E":
                edits = input("  Edits (e.g. 'remove 2,4' or paste URLs): ").strip()
                state["source_edits"] = edits
                state["checkpoint_history"]["cp1"] = {"presented": True, "approved": True, "edits": edits}
                state["current_step"] = "cp1_approved"
                _ok("Source plan edited.")
                return state
            elif choice == "C":
                state["status"] = "cancelled"
                state["current_step"] = "cancelled"
                print("  Pipeline cancelled.")
                return state

    def _checkpoint_2(self, state: dict) -> dict:
        handoff_text = (HANDOFFS_DIR / "handoff_nam.md").read_text(encoding="utf-8")
        _banner(2, "Direction Selection")
        print(handoff_text)
        print(_sep())
        print("  Select directions to pursue.")
        print("  Examples:  '1,3'  |  'all'  |  '2: skip simulation part'")
        print(_sep())

        while True:
            choice = input("\n  Your selection: ").strip()
            if choice:
                state["pk_direction_selection"] = choice
                state["checkpoint_history"]["cp2"] = {"presented": True, "approved": True, "selection": choice}
                state["current_step"] = "cp2_approved"
                _ok(f"Selected: {choice}")
                return state
            print("  Please enter at least one direction.")

    def _checkpoint_3(self, state: dict) -> dict:
        handoff_text = (HANDOFFS_DIR / "handoff_mod.md").read_text(encoding="utf-8")
        _banner(3, "Output Format")
        print(handoff_text)
        print(_sep())
        print("  A) Report only (Markdown)")
        print("  B) Slides outline (Markdown / PPTX-ready)")
        print("  C) Obsidian update only")
        print("  D) Report + Obsidian")
        print("  E) All of the above")
        print("\n  Add notes after a colon, e.g. 'D: max 8 slides'")
        print(_sep())

        while True:
            choice = input("\n  Your choice: ").strip()
            if choice and choice[0].upper() in "ABCDE":
                state["pk_output_format"] = choice
                state["checkpoint_history"]["cp3"] = {"presented": True, "approved": True, "format": choice}
                state["current_step"] = "cp3_approved"
                _ok(f"Format: {choice}")
                return state
            print("  Please enter A, B, C, D, or E.")


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
    state["status"] = "running"
    print(_sep())
    print(f"  Resuming run: {state['run_id']}")
    print(f"  Question:     {state['pk_input']}")
    print(f"  From step:    {state['current_step']}")
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


def _cmd_reset(_args: argparse.Namespace) -> None:
    confirm = input("Reset deletes current state and all handoffs. Confirm? [y/N] ")
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
    p_reset.set_defaults(func=_cmd_reset)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
