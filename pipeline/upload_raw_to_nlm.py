"""One-time script: score raw/ PDFs and upload top-N to a given NLM notebook."""
from __future__ import annotations
import os
import sys
from pathlib import Path

# Run from project root or pipeline/
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from agents.raw_pdf_scorer import score_raw_pdfs
from notebooklm_client import NLMClient

NOTEBOOK_ID = "d1059e3c-f53c-44e9-9835-474bd78c9aa4"
RAW_DIR = PROJECT_ROOT / "raw"
WIKI_DIR = PROJECT_ROOT / "wiki"
TOP_N = 30
MIN_SCORE = 0.15

QUERY = (
    "What ML potentials best capture the Mg + H2 → MgH2 phase transition "
    "as observed in PCI isotherms, using GCMC/μNPT simulations with MLIP "
    "descriptors (MACE, NequIP, GAP, ACE)?"
)
DAO_HANDOFF = ""  # no Dao handoff available for one-off run

api_key = os.environ.get("MISTRAL_API_KEY")

print(f"Scoring raw/ PDFs (top {TOP_N}, min_score={MIN_SCORE})...")
scored = score_raw_pdfs(
    query=QUERY,
    dao_handoff=DAO_HANDOFF,
    wiki_dir=WIKI_DIR,
    raw_dir=RAW_DIR,
    top_n=TOP_N,
    min_score=MIN_SCORE,
    api_key=api_key,
)

if not scored:
    print("No PDFs scored above threshold — check raw/ directory.")
    sys.exit(0)

print(f"\nTop {len(scored)} PDFs selected:")
for pdf, score, reason in scored:
    print(f"  {score:.3f}  {pdf.name}  [{reason}]")

print(f"\nUploading to notebook {NOTEBOOK_ID}...")
pdfs = [p for p, _s, _r in scored]
loaded, failed = NLMClient.add_sources(NOTEBOOK_ID, [], pdfs)
print(f"  Loaded: {len(loaded)}  Failed: {len(failed)}")
if failed:
    for f in failed:
        print(f"  FAIL: {f}")
