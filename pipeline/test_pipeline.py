"""
Tests for all pipeline agents and helpers.

Run:
    python -m pytest pipeline/test_pipeline.py -v
    # or without pytest:
    python pipeline/test_pipeline.py

Structure:
    TestUtils          — utils.py pure functions
    TestBuilderHelpers — builder.py pure helpers (no LLM, no NLM)
    TestBuilderAgent   — BuilderAgent.run() with mocked NLMClient + LLM
    TestCherryAgent    — CherryAgent.run() with mocked NLMClient + LLM
    TestDaoAgent       — DaoAgent.run() with mocked Semantic Scholar + LLM
    TestNamAgent       — NamAgent.run() with mocked LLM
    TestSomAgent       — SomAgent.run() with mocked LLM
    TestManaoAgent     — ManaoAgent.run() with mocked LLM
    TestModAgent       — ModAgent.run() with mocked LLM
    TestChompooAgent   — ChompooAgent helpers + mocked LLM
    TestNannyAgent     — NannyAgent.run() with mocked LLM + NLMClient
    TestNLMClient      — NLMClient sync facade (mocked asyncio.run)
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Make pipeline/ importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_client():
    """Fake Anthropic client that returns a fixed LLM response."""
    client = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text="mock LLM response")]
    client.messages.create.return_value = resp
    return client


def _make_agent(cls, pipeline_dir: Path):
    return cls(_make_client(), pipeline_dir)


def _write_handoff(pipeline_dir: Path, name: str, content: str):
    hdir = pipeline_dir / "handoffs"
    hdir.mkdir(parents=True, exist_ok=True)
    (hdir / f"handoff_{name}.md").write_text(content, encoding="utf-8")


DAO_HANDOFF = """\
## Dao Handoff

**PK's input:** test question
**Run ID:** 2026-01-01T00:00:00

### What we already know
We know [[mace-paper]] and [[nequip-paper]] cover equivariant architectures.

### The gap
- Benchmark comparison on HEA systems is missing
- Transferability across compositions not studied

### Selected papers
| Ref | Priority | What it shows | Cherry should extract |
|-----|----------|--------------|----------------------|
| [1] | High | MACE benchmark | accuracy numbers |

### Notes for Builder
Use arXiv links.

### Verified source URLs (Builder reads this)
| # | URL |
|---|-----|
| 1 | https://arxiv.org/abs/2206.07697 |
| 2 | https://arxiv.org/abs/2101.03164 |
"""

BUILDER_HANDOFF = """\
## Builder Handoff

**Notebook ID:** abc123def456ghi789
**Run ID:** 2026-01-01T00:00:00

### NotebookLM Sources (from Semantic Scholar)
| # | Source | Status |
|---|--------|--------|
| 1 | https://arxiv.org/abs/2206.07697 | COMPLETED |

### NLM Web Research Sources (3 imported)
| URL | Title |
|-----|-------|
| https://arxiv.org/abs/2206.07697 | MACE paper |

### Failed sources
None

### Local Wiki Context
(no existing wiki pages found)

### Notes for Cherry
Query NotebookLM notebook `abc123def456ghi789` for Q&A.
"""

CHERRY_HANDOFF = """\
## Cherry Handoff

**Notebook ID:** abc123def456ghi789
**Questions asked:** 6
**Mode:** NotebookLM

### Idea Card
This research investigates ML potentials for MgH2.

### Q&A

**Q1:** What is the benchmark accuracy?
**A1:**
- MACE achieves 1.2 meV/atom MAE on MD17

### Blind Spots
- High-temperature behaviour not covered
"""

NAM_HANDOFF = """\
## Nam Handoff

**Revision:** 0

### Research Summary
ML potentials show promise for MgH2 modelling.

### Knowledge Gaps
- No HEA benchmark exists

### Limitations
- Limited training data

### Top 5 Strategic Directions
| # | Direction | Description | Effort | Rationale | Key Risk |
|---|-----------|-------------|--------|-----------|----------|
| 1 | MACE-MgH2 | Train MACE on MgH2 | Medium | Good baseline | Data quality |
| 2 | Transferability | Test cross-composition | High | Novel | Cost |
| 3 | Phonons | Compute phonon spectra | Medium | Validation | DFT errors |
| 4 | Defects | Include vacancy defects | High | Realistic | Convergence |
| 5 | MD | Long MD runs | Low | Dynamics | Stability |

### Revision notes
N/A
"""

MOD_HANDOFF = """\
## Mod Handoff

**Insights extracted:** 3
**KB pages to update:** mace-paper
**KB pages to create:** mgh2-mlp-benchmark

### Atomic Insights
#### MACE accuracy on MD17
- **Fact:** MACE achieves 1.2 meV/atom MAE on MD17.
- **Detail:** Benchmark result from 2022 paper.
- **Status:** Done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #ml-potentials #benchmark

#### MgH2 training gap
- **Fact:** No published MLP trained specifically on $MgH_2$ exists as of 2024.
- **Detail:** Gap identified from literature search.
- **Status:** Not done
- **Est. completion:** 2025
- **Confidence:** Medium
- **Topic tags:** #hydrogen-storage #ml-potentials

#### Transferability challenge
- **Fact:** Cross-composition transferability remains an open problem.
- **Detail:** Ongoing work at several groups.
- **Status:** Ongoing
- **Est. completion:** 2026
- **Confidence:** Medium
- **Topic tags:** #ml-potentials
"""


# ─────────────────────────────────────────────────────────────────────────────
# TestUtils
# ─────────────────────────────────────────────────────────────────────────────

class TestUtils(unittest.TestCase):

    def test_paper_url_arxiv_preferred(self):
        from agents.utils import paper_url
        paper = {"externalIds": {"ArXiv": "2206.07697", "DOI": "10.1234/x"}}
        self.assertEqual(paper_url(paper), "https://arxiv.org/abs/2206.07697")

    def test_paper_url_doi_fallback(self):
        from agents.utils import paper_url
        paper = {"externalIds": {"DOI": "10.1234/x"}}
        self.assertEqual(paper_url(paper), "https://doi.org/10.1234/x")

    def test_paper_url_open_access_fallback(self):
        from agents.utils import paper_url
        paper = {"externalIds": {}, "openAccessPdf": {"url": "https://example.com/paper.pdf"}}
        self.assertEqual(paper_url(paper), "https://example.com/paper.pdf")

    def test_paper_url_empty(self):
        from agents.utils import paper_url
        self.assertEqual(paper_url({}), "")

    def test_paper_citation_format(self):
        from agents.utils import paper_citation
        paper = {
            "authors": [{"name": "Smith"}, {"name": "Jones"}],
            "year": 2022,
            "title": "Test Paper",
            "externalIds": {"ArXiv": "2206.07697"},
        }
        citation = paper_citation(paper)
        self.assertIn("Smith et al.", citation)
        self.assertIn("2022", citation)
        self.assertIn("Test Paper", citation)
        self.assertIn("arxiv.org", citation)

    def test_extract_search_keywords_model_names(self):
        from agents.utils import extract_search_keywords
        kw = extract_search_keywords("MACE accuracy on MD17", "MACE achieves 1.2 meV/atom")
        self.assertIn("MACE", kw)

    def test_extract_search_keywords_material_terms(self):
        from agents.utils import extract_search_keywords
        kw = extract_search_keywords("HEA force field", "high entropy alloy MD simulation")
        self.assertTrue(len(kw) > 0)

    def test_extract_search_keywords_fallback(self):
        from agents.utils import extract_search_keywords
        kw = extract_search_keywords("Novel approach to something", "basic claim here")
        # Falls back to first 8 words of title
        self.assertIn("Novel", kw)

    @patch("agents.utils.urllib.request.urlopen")
    def test_search_semantic_scholar_returns_data(self, mock_urlopen):
        from agents.utils import search_semantic_scholar
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": [{"paperId": "abc", "title": "Test"}]}).encode()
        mock_urlopen.return_value.__enter__ = lambda s: mock_resp
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        results = search_semantic_scholar("test query", limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test")

    @patch("agents.utils.urllib.request.urlopen", side_effect=Exception("network error"))
    def test_search_semantic_scholar_returns_empty_on_error(self, _):
        from agents.utils import search_semantic_scholar
        results = search_semantic_scholar("test")
        self.assertEqual(results, [])

    @patch("agents.utils.urllib.request.urlopen")
    def test_search_semantic_scholar_uses_api_key(self, mock_urlopen):
        from agents.utils import search_semantic_scholar
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": []}).encode()
        mock_urlopen.return_value.__enter__ = lambda s: mock_resp
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        with patch.dict("os.environ", {"SEMANTIC_SCHOLAR_API_KEY": "test-key-123"}):
            search_semantic_scholar("test")
        req_obj = mock_urlopen.call_args[0][0]
        self.assertEqual(req_obj.get_header("X-api-key"), "test-key-123")


# ─────────────────────────────────────────────────────────────────────────────
# TestBuilderHelpers
# ─────────────────────────────────────────────────────────────────────────────

class TestBuilderHelpers(unittest.TestCase):

    def test_extract_sources_verified_section(self):
        from agents.builder import _extract_sources
        sources = _extract_sources(DAO_HANDOFF)
        self.assertIn("https://arxiv.org/abs/2206.07697", sources)
        self.assertIn("https://arxiv.org/abs/2101.03164", sources)

    def test_extract_sources_deduplicates(self):
        from agents.builder import _extract_sources
        handoff = DAO_HANDOFF + "\n| 3 | https://arxiv.org/abs/2206.07697 |\n"
        sources = _extract_sources(handoff)
        self.assertEqual(sources.count("https://arxiv.org/abs/2206.07697"), 1)

    def test_extract_sources_empty(self):
        from agents.builder import _extract_sources
        self.assertEqual(_extract_sources("no table here"), [])

    def test_url_to_pdf_stem_arxiv(self):
        from agents.builder import _url_to_pdf_stem
        self.assertEqual(_url_to_pdf_stem("https://arxiv.org/abs/2206.07697"), "2206.07697")

    def test_url_to_pdf_stem_generic(self):
        from agents.builder import _url_to_pdf_stem
        self.assertEqual(_url_to_pdf_stem("https://example.com/papers/mace.pdf"), "mace.pdf")

    def test_build_handoff_contains_notebook_id(self):
        from agents.builder import _build_handoff
        h = _build_handoff("run1", "nb123", [], [], [], "(no wiki)", [])
        self.assertIn("nb123", h)

    def test_build_handoff_web_sources_section(self):
        from agents.builder import _build_handoff
        web = [{"url": "https://example.com/paper", "title": "Some Paper"}]
        h = _build_handoff("run1", "nb123", [], [], [], "(no wiki)", web)
        self.assertIn("NLM Web Research Sources", h)
        self.assertIn("example.com/paper", h)

    def test_build_handoff_no_web_sources(self):
        from agents.builder import _build_handoff
        h = _build_handoff("run1", "nb123", [], [], [], "(no wiki)", [])
        self.assertIn("(none found)", h)

    def test_stub_handoff_contains_error(self):
        from agents.builder import _stub_handoff
        h = _stub_handoff("run1", ["https://a.com"], "auth failed", [], "(no wiki)")
        self.assertIn("auth failed", h)
        self.assertIn("N/A", h)


# ─────────────────────────────────────────────────────────────────────────────
# TestBuilderAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestBuilderAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self.tmp.name)
        _write_handoff(self.pipeline_dir, "dao", DAO_HANDOFF)

    def tearDown(self):
        self.tmp.cleanup()

    @patch("agents.builder.NLMClient.run_web_research", return_value=[])
    @patch("agents.builder.NLMClient.add_sources", return_value=([{"num": 1, "source": "https://arxiv.org/abs/2206.07697", "status": "COMPLETED"}], []))
    @patch("agents.builder.NLMClient.create_notebook", return_value="nb-test-123")
    def test_run_creates_notebook_and_writes_handoff(self, mock_create, mock_add, mock_web):
        from agents.builder import BuilderAgent
        agent = _make_agent(BuilderAgent, self.pipeline_dir)
        state = {
            "run_id": "2026-01-01T00:00:00",
            "pk_input": "test question",
            "wiki_root": str(self.pipeline_dir / "wiki"),
            "source_edits": "",
        }
        result = agent.run(state)
        self.assertEqual(result["notebook_id"], "nb-test-123")
        handoff_path = self.pipeline_dir / "handoffs" / "handoff_builder.md"
        self.assertTrue(handoff_path.exists())
        content = handoff_path.read_text(encoding="utf-8")
        self.assertIn("nb-test-123", content)

    @patch("agents.builder.NLMClient.create_notebook", return_value=None)
    def test_run_returns_skipped_when_nlm_fails(self, mock_create):
        from agents.builder import BuilderAgent
        agent = _make_agent(BuilderAgent, self.pipeline_dir)
        state = {
            "run_id": "2026-01-01T00:00:00",
            "pk_input": "test",
            "wiki_root": str(self.pipeline_dir / "wiki"),
            "source_edits": "",
        }
        result = agent.run(state)
        self.assertIsNone(result["notebook_id"])
        self.assertTrue(result.get("builder_skipped"))

    @patch("agents.builder.NLMClient.run_web_research", return_value=[{"url": "https://web.com/p", "title": "Web Paper"}])
    @patch("agents.builder.NLMClient.add_sources", return_value=([], []))
    @patch("agents.builder.NLMClient.create_notebook", return_value="nb-xyz")
    def test_run_calls_web_research_with_pk_input(self, mock_create, mock_add, mock_web):
        from agents.builder import BuilderAgent
        agent = _make_agent(BuilderAgent, self.pipeline_dir)
        state = {
            "run_id": "2026-01-01T00:00:00",
            "pk_input": "my research question",
            "wiki_root": str(self.pipeline_dir / "wiki"),
            "source_edits": "",
        }
        agent.run(state)
        mock_web.assert_called_once_with("nb-xyz", "my research question", max_sources=8)

    @patch("agents.builder.NLMClient.run_web_research", return_value=[])
    @patch("agents.builder.NLMClient.add_sources", return_value=([], []))
    @patch("agents.builder.NLMClient.create_notebook", return_value="nb-xyz")
    def test_source_edits_removes_sources(self, mock_create, mock_add, mock_web):
        from agents.builder import BuilderAgent
        agent = _make_agent(BuilderAgent, self.pipeline_dir)
        state = {
            "run_id": "2026-01-01T00:00:00",
            "pk_input": "test",
            "wiki_root": str(self.pipeline_dir / "wiki"),
            "source_edits": "remove 1",
        }
        agent.run(state)
        urls_passed = mock_add.call_args[0][1]
        self.assertNotIn("https://arxiv.org/abs/2206.07697", urls_passed)


# ─────────────────────────────────────────────────────────────────────────────
# TestCherryAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestCherryAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self.tmp.name)
        _write_handoff(self.pipeline_dir, "dao", DAO_HANDOFF)
        _write_handoff(self.pipeline_dir, "builder", BUILDER_HANDOFF)

    def tearDown(self):
        self.tmp.cleanup()

    @patch("agents.cherry.NLMClient.get_notebook_summary", return_value="NLM summary text")
    @patch("agents.cherry.NLMClient.ask", return_value="Mock NLM answer about MACE\n\n*Sources:*\n  [1] MACE paper")
    def test_run_nlm_available_writes_handoff(self, mock_ask, mock_summary):
        from agents.cherry import CherryAgent
        agent = _make_agent(CherryAgent, self.pipeline_dir)
        state = {
            "pk_input": "test question",
            "notebook_id": "abc123def456ghi789",
            "wiki_root": str(self.pipeline_dir / "wiki"),
        }
        agent.run(state)
        handoff = (self.pipeline_dir / "handoffs" / "handoff_cherry.md").read_text()
        self.assertIn("Cherry Handoff", handoff)
        self.assertIn("NotebookLM", handoff)

    @patch("agents.cherry.NLMClient.get_notebook_summary", return_value="")
    @patch("agents.cherry.NLMClient.ask", return_value="answer")
    def test_ask_called_with_detailed_mode(self, mock_ask, mock_summary):
        from agents.cherry import CherryAgent
        agent = _make_agent(CherryAgent, self.pipeline_dir)
        state = {
            "pk_input": "test question",
            "notebook_id": "abc123def456ghi789",
            "wiki_root": str(self.pipeline_dir / "wiki"),
        }
        agent.run(state)
        # Check that detailed mode was used for Q&A asks
        for c in mock_ask.call_args_list:
            if c[0][1] != "What important aspects of this topic were NOT covered by the sources?":
                self.assertEqual(c[0][2], "detailed")

    def test_run_fallback_when_no_notebook(self):
        from agents.cherry import CherryAgent
        agent = _make_agent(CherryAgent, self.pipeline_dir)
        state = {
            "pk_input": "test question",
            "notebook_id": "",
            "wiki_root": str(self.pipeline_dir / "wiki"),
        }
        # Should not raise even without NLM
        agent.run(state)
        handoff = (self.pipeline_dir / "handoffs" / "handoff_cherry.md").read_text()
        self.assertIn("Cherry Handoff", handoff)

    @patch("agents.cherry.NLMClient.get_notebook_summary", return_value="summary")
    @patch("agents.cherry.NLMClient.ask", return_value="answer")
    def test_notebook_summary_enriches_idea_card(self, mock_ask, mock_summary):
        from agents.cherry import CherryAgent
        agent = _make_agent(CherryAgent, self.pipeline_dir)
        # Capture the LLM user message for the idea card call
        captured_user_msgs = []
        original_llm = agent._llm
        def capturing_llm(system, user, **kwargs):
            captured_user_msgs.append(user)
            return "mock response"
        agent._llm = capturing_llm
        state = {
            "pk_input": "test question",
            "notebook_id": "abc123def456ghi789",
            "wiki_root": str(self.pipeline_dir / "wiki"),
        }
        agent.run(state)
        # The idea card call should include the summary
        idea_card_msgs = [m for m in captured_user_msgs if "NotebookLM notebook summary" in m]
        self.assertTrue(len(idea_card_msgs) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestDaoAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestDaoAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self.tmp.name)
        wiki_dir = self.pipeline_dir / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "index.md").write_text("# Index\n- [[mace-paper]]", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @patch("agents.dao.search_semantic_scholar")
    def test_run_writes_handoff_with_verified_urls(self, mock_search):
        from agents.dao import DaoAgent
        mock_search.return_value = [
            {"paperId": "p1", "title": "MACE paper", "authors": [{"name": "Batatia"}],
             "year": 2022, "externalIds": {"ArXiv": "2206.07697"}, "abstract": "test",
             "openAccessPdf": None},
        ]
        agent = _make_agent(DaoAgent, self.pipeline_dir)
        # Override LLM to return output that references [1]
        agent._llm = lambda s, u, **kw: (
            "## Dao Handoff\n\n**PK's input:** test\n**Run ID:** r1\n\n"
            "### What we already know\nWe know [[mace-paper]].\n\n"
            "### The gap\n- Gap 1\n\n### Selected papers\n| [1] | High | MACE | accuracy |\n\n"
            "### Notes for Builder\nUse arXiv.\n\n### Proposed Workflow\n1. Search"
        )
        state = {
            "run_id": "2026-01-01T00:00:00",
            "pk_input": "What is the best ML potential for MgH2?",
            "wiki_root": str(self.pipeline_dir / "wiki"),
        }
        agent.run(state)
        handoff = (self.pipeline_dir / "handoffs" / "handoff_dao.md").read_text()
        self.assertIn("Verified source URLs", handoff)
        self.assertIn("arxiv.org/abs/2206.07697", handoff)

    @patch("agents.dao.search_semantic_scholar", return_value=[])
    def test_run_handles_no_search_results(self, mock_search):
        from agents.dao import DaoAgent
        agent = _make_agent(DaoAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Dao Handoff\n\n**PK's input:** test\n**Run ID:** r1\n\n### The gap\n- Gap\n\n### Proposed Workflow\n1. Step"
        state = {
            "run_id": "2026-01-01T00:00:00",
            "pk_input": "test question",
            "wiki_root": str(self.pipeline_dir / "wiki"),
        }
        agent.run(state)
        handoff = (self.pipeline_dir / "handoffs" / "handoff_dao.md").read_text()
        self.assertIn("No papers selected", handoff)

    @patch("agents.dao.search_semantic_scholar")
    def test_run_fires_three_queries(self, mock_search):
        from agents.dao import DaoAgent
        mock_search.return_value = []
        agent = _make_agent(DaoAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Dao Handoff\n\n**PK's input:** test\n**Run ID:** r1\n"
        state = {
            "run_id": "2026-01-01T00:00:00",
            "pk_input": "What are the best models for hydrogen storage materials?",
            "wiki_root": str(self.pipeline_dir / "wiki"),
        }
        agent.run(state)
        self.assertEqual(mock_search.call_count, 3)


# ─────────────────────────────────────────────────────────────────────────────
# TestNamAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestNamAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self.tmp.name)
        _write_handoff(self.pipeline_dir, "dao", DAO_HANDOFF)
        _write_handoff(self.pipeline_dir, "cherry", CHERRY_HANDOFF)
        _write_handoff(self.pipeline_dir, "som", "## Som Handoff\n**Verdict:** PASS\n")
        _write_handoff(self.pipeline_dir, "manao", "## Manao Handoff\n**Verdict:** PASS\n")
        _write_handoff(self.pipeline_dir, "nanny", "")

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_writes_handoff(self):
        from agents.nam import NamAgent
        agent = _make_agent(NamAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: NAM_HANDOFF
        state = {
            "run_id": "2026-01-01T00:00:00",
            "pk_input": "test",
            "pk_direction_selection": "1,2",
            "revision_count": 0,
            "wiki_root": str(self.pipeline_dir / "wiki"),
        }
        agent.run(state)
        handoff = (self.pipeline_dir / "handoffs" / "handoff_nam.md").read_text()
        self.assertIn("Nam Handoff", handoff)

    def test_run_passes_revision_count(self):
        from agents.nam import NamAgent
        agent = _make_agent(NamAgent, self.pipeline_dir)
        captured = []
        def capture_llm(s, u, **kw):
            captured.append(u)
            return NAM_HANDOFF
        agent._llm = capture_llm
        state = {
            "run_id": "r1",
            "pk_input": "test",
            "pk_direction_selection": "1",
            "revision_count": 2,
            "wiki_root": str(self.pipeline_dir / "wiki"),
        }
        agent.run(state)
        self.assertTrue(any("revision" in m.lower() or "2" in m for m in captured))


# ─────────────────────────────────────────────────────────────────────────────
# TestSomAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestSomAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self.tmp.name)
        _write_handoff(self.pipeline_dir, "nam", NAM_HANDOFF)
        _write_handoff(self.pipeline_dir, "cherry", CHERRY_HANDOFF)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_pass_verdict(self):
        from agents.som import SomAgent
        agent = _make_agent(SomAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Som Handoff — Logic Audit\n\n**Verdict:** PASS\n\n### Strengths\n- Good logic\n"
        state = {"pk_input": "test", "pk_direction_selection": "1,2", "wiki_root": str(self.pipeline_dir / "wiki")}
        result = agent.run(state)
        self.assertEqual(result.get("som_verdict"), "PASS")

    def test_run_revise_verdict(self):
        from agents.som import SomAgent
        agent = _make_agent(SomAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Som Handoff — Logic Audit\n\nVERDICT: REVISE\n\n### Blocking Issues\n- Issue: contradiction\n"
        state = {"pk_input": "test", "pk_direction_selection": "1", "wiki_root": str(self.pipeline_dir / "wiki")}
        result = agent.run(state)
        self.assertEqual(result.get("som_verdict"), "REVISE")

    def test_run_writes_handoff(self):
        from agents.som import SomAgent
        agent = _make_agent(SomAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Som Handoff — Logic Audit\n\n**Verdict:** PASS\n"
        agent.run({"pk_input": "test", "pk_direction_selection": "1", "wiki_root": str(self.pipeline_dir / "wiki")})
        self.assertTrue((self.pipeline_dir / "handoffs" / "handoff_som.md").exists())


# ─────────────────────────────────────────────────────────────────────────────
# TestManaoAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestManaoAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self.tmp.name)
        _write_handoff(self.pipeline_dir, "nam", NAM_HANDOFF)
        _write_handoff(self.pipeline_dir, "cherry", CHERRY_HANDOFF)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_pass_verdict(self):
        from agents.manao import ManaoAgent
        agent = _make_agent(ManaoAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Manao Handoff — Fact Audit\n\n**Verdict:** PASS\n\n### Confirmed Claims\n- Claim 1\n"
        state = {"pk_input": "test", "pk_direction_selection": "1", "wiki_root": str(self.pipeline_dir / "wiki")}
        result = agent.run(state)
        self.assertEqual(result.get("manao_verdict"), "PASS")

    def test_run_revise_verdict(self):
        from agents.manao import ManaoAgent
        agent = _make_agent(ManaoAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Manao Handoff — Fact Audit\n\nVERDICT: REVISE\n\n### Flagged Claims\n- Bad claim\n"
        state = {"pk_input": "test", "pk_direction_selection": "1", "wiki_root": str(self.pipeline_dir / "wiki")}
        result = agent.run(state)
        self.assertEqual(result.get("manao_verdict"), "REVISE")

    def test_run_writes_handoff(self):
        from agents.manao import ManaoAgent
        agent = _make_agent(ManaoAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Manao Handoff — Fact Audit\n\n**Verdict:** PASS\n"
        agent.run({"pk_input": "test", "pk_direction_selection": "1", "wiki_root": str(self.pipeline_dir / "wiki")})
        self.assertTrue((self.pipeline_dir / "handoffs" / "handoff_manao.md").exists())


# ─────────────────────────────────────────────────────────────────────────────
# TestModAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestModAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self.tmp.name)
        _write_handoff(self.pipeline_dir, "nam", NAM_HANDOFF)
        _write_handoff(self.pipeline_dir, "cherry", CHERRY_HANDOFF)
        _write_handoff(self.pipeline_dir, "som", "## Som Handoff\n**Verdict:** PASS\n### Minor Notes\n- note\n")
        _write_handoff(self.pipeline_dir, "manao", "## Manao Handoff\n**Verdict:** PASS\n### Recommendations\n- rec\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_writes_handoff(self):
        from agents.mod import ModAgent
        agent = _make_agent(ModAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: MOD_HANDOFF
        wiki_dir = self.pipeline_dir / "wiki"
        wiki_dir.mkdir(parents=True)
        state = {
            "pk_input": "test",
            "run_id": "r1",
            "wiki_root": str(wiki_dir),
        }
        agent.run(state)
        self.assertTrue((self.pipeline_dir / "handoffs" / "handoff_mod.md").exists())

    def test_run_does_not_write_wiki_on_conflict(self):
        from agents.mod import ModAgent
        agent = _make_agent(ModAgent, self.pipeline_dir)
        # Return handoff that has a CONFLICT flag
        conflict_handoff = MOD_HANDOFF + "\n\n### Conflicts\n- CONFLICT: contradicts existing entry\n"
        agent._llm = lambda s, u, **kw: conflict_handoff
        wiki_dir = self.pipeline_dir / "wiki"
        wiki_dir.mkdir(parents=True)
        state = {"pk_input": "test", "run_id": "r1", "wiki_root": str(wiki_dir)}
        agent.run(state)
        # wiki/ should not have new content pages (audit log and index are ok)
        wiki_files = [
            f for f in wiki_dir.glob("*.md")
            if f.name != "index.md" and not f.name.startswith(".")
        ]
        self.assertEqual(len(wiki_files), 0)


# ─────────────────────────────────────────────────────────────────────────────
# TestChompooAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestChompooAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self.tmp.name)
        _write_handoff(self.pipeline_dir, "mod", MOD_HANDOFF)

    def tearDown(self):
        self.tmp.cleanup()

    def test_extract_done_insights_only(self):
        from agents.chompoo import _extract_done_insights
        insights = _extract_done_insights(MOD_HANDOFF)
        done = [i for i in insights if i["status"].lower() == "done"]
        ongoing = [i for i in insights if i["status"].lower() == "ongoing"]
        not_done = [i for i in insights if i["status"].lower() == "not done"]
        self.assertEqual(len(done), 1)
        self.assertEqual(len(ongoing), 1)
        self.assertEqual(len(not_done), 1)

    def test_extract_done_insights_fact_content(self):
        from agents.chompoo import _extract_done_insights
        insights = _extract_done_insights(MOD_HANDOFF)
        done = [i for i in insights if i["status"].lower() == "done"][0]
        self.assertIn("1.2 meV", done["fact"])

    @patch("agents.chompoo.search_semantic_scholar")
    def test_run_searches_only_done_insights(self, mock_search):
        from agents.chompoo import ChompooAgent
        mock_search.return_value = []
        agent = _make_agent(ChompooAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Chompoo Handoff — Literature Verification\n\n**Verified:** 0 / Done: 1\n"
        agent.run({})
        # Only 1 Done insight in MOD_HANDOFF
        self.assertEqual(mock_search.call_count, 1)

    @patch("agents.chompoo.search_semantic_scholar")
    def test_run_writes_handoff(self, mock_search):
        from agents.chompoo import ChompooAgent
        mock_search.return_value = [
            {"paperId": "p1", "title": "MACE paper", "authors": [{"name": "Batatia"}],
             "year": 2022, "externalIds": {"ArXiv": "2206.07697"}, "abstract": "MACE benchmark"}
        ]
        agent = _make_agent(ChompooAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "## Chompoo Handoff — Literature Verification\n\n**Verified:** 1 / Done: 1\n"
        result = agent.run({})
        self.assertTrue((self.pipeline_dir / "handoffs" / "handoff_chompoo.md").exists())
        self.assertIn("chompoo_total_done", result)


# ─────────────────────────────────────────────────────────────────────────────
# TestNannyAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestNannyAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self.tmp.name)
        for name, content in [
            ("mod", MOD_HANDOFF),
            ("chompoo", "## Chompoo Handoff\n**Verified:** 1 / Done: 1\n"),
            ("nam", NAM_HANDOFF),
            ("cherry", CHERRY_HANDOFF),
            ("dao", DAO_HANDOFF),
            ("som", "## Som Handoff\n**Verdict:** PASS\n"),
            ("manao", "## Manao Handoff\n**Verdict:** PASS\n"),
            ("builder", BUILDER_HANDOFF),
            ("nanny", ""),
        ]:
            _write_handoff(self.pipeline_dir, name, content)

    def tearDown(self):
        self.tmp.cleanup()

    def _base_state(self, fmt="A"):
        return {
            "run_id": "2026-01-01T00:00:00",
            "pk_input": "test question",
            "pk_output_format": fmt,
            "notebook_id": "",
            "wiki_root": str(self.pipeline_dir / "wiki"),
            "output_root": str(self.pipeline_dir / "output"),
        }

    def test_run_format_a_writes_report(self):
        from agents.nanny import NannyAgent
        agent = _make_agent(NannyAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "# Report\nContent here."
        result = agent.run(self._base_state("A"))
        report = next((f for f in result["output_files"] if "report.md" in f), None)
        self.assertIsNotNone(report)
        self.assertTrue(Path(report).exists())

    def test_run_format_b_writes_slides(self):
        from agents.nanny import NannyAgent
        agent = _make_agent(NannyAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "---\nmarp: true\n---\n# Slide 1"
        result = agent.run(self._base_state("B"))
        slides = next((f for f in result["output_files"] if "slides.md" in f), None)
        self.assertIsNotNone(slides)

    def test_run_writes_abstract(self):
        from agents.nanny import NannyAgent
        agent = _make_agent(NannyAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "Abstract content"
        agent.run(self._base_state("A"))
        output_dir = self.pipeline_dir / "output" / "2026-01-01"
        abstracts = list(output_dir.glob("abstract_*.md"))
        self.assertEqual(len(abstracts), 1)

    def test_run_writes_trace_folder(self):
        from agents.nanny import NannyAgent
        agent = _make_agent(NannyAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "content"
        agent.run(self._base_state("A"))
        output_dir = self.pipeline_dir / "output" / "2026-01-01"
        traces = list(output_dir.glob("trace_*/"))
        self.assertEqual(len(traces), 1)

    @patch("agents.nanny.NLMClient.generate_artifact", return_value=True)
    def test_run_generates_nlm_report_for_format_a(self, mock_gen):
        from agents.nanny import NannyAgent
        agent = _make_agent(NannyAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "content"
        state = self._base_state("A")
        state["notebook_id"] = "nb-test-123"
        agent.run(state)
        kinds_called = [c[0][1] for c in mock_gen.call_args_list]
        self.assertIn("report", kinds_called)

    @patch("agents.nanny.NLMClient.generate_artifact", return_value=True)
    def test_run_generates_nlm_slides_for_format_b(self, mock_gen):
        from agents.nanny import NannyAgent
        agent = _make_agent(NannyAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "content"
        state = self._base_state("B")
        state["notebook_id"] = "nb-test-123"
        agent.run(state)
        kinds_called = [c[0][1] for c in mock_gen.call_args_list]
        self.assertIn("slides", kinds_called)

    @patch("agents.nanny.NLMClient.generate_artifact", return_value=False)
    def test_nlm_artifact_failure_does_not_break_run(self, mock_gen):
        from agents.nanny import NannyAgent
        agent = _make_agent(NannyAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "content"
        state = self._base_state("A")
        state["notebook_id"] = "nb-test-123"
        result = agent.run(state)  # Should not raise
        self.assertIn("output_files", result)

    def test_run_skips_nlm_when_no_notebook_id(self):
        from agents.nanny import NannyAgent
        agent = _make_agent(NannyAgent, self.pipeline_dir)
        agent._llm = lambda s, u, **kw: "content"
        with patch("agents.nanny.NLMClient.generate_artifact") as mock_gen:
            agent.run(self._base_state("A"))  # notebook_id=""
            mock_gen.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# TestNLMClient
# ─────────────────────────────────────────────────────────────────────────────

class TestNLMClient(unittest.TestCase):

    @patch("notebooklm_client._available", return_value=False)
    def test_create_notebook_returns_none_when_unavailable(self, _):
        from notebooklm_client import NLMClient
        self.assertIsNone(NLMClient.create_notebook("test"))

    @patch("notebooklm_client._available", return_value=False)
    def test_add_sources_returns_empty_failed_when_unavailable(self, _):
        from notebooklm_client import NLMClient
        loaded, failed = NLMClient.add_sources("nb1", ["https://a.com"])
        self.assertEqual(loaded, [])
        self.assertEqual(len(failed), 1)
        self.assertIn("NLM unavailable", failed[0]["reason"])

    @patch("notebooklm_client._available", return_value=False)
    def test_ask_returns_unavailable_string(self, _):
        from notebooklm_client import NLMClient
        result = NLMClient.ask("nb1", "test question")
        self.assertIn("unavailable", result.lower())

    @patch("notebooklm_client._available", return_value=False)
    def test_get_notebook_summary_returns_empty(self, _):
        from notebooklm_client import NLMClient
        self.assertEqual(NLMClient.get_notebook_summary("nb1"), "")

    @patch("notebooklm_client._available", return_value=False)
    def test_generate_artifact_returns_false_when_unavailable(self, _):
        from notebooklm_client import NLMClient
        self.assertFalse(NLMClient.generate_artifact("nb1", "report", Path("/tmp/x.md")))

    @patch("notebooklm_client._available", return_value=False)
    def test_run_web_research_returns_empty_when_unavailable(self, _):
        from notebooklm_client import NLMClient
        self.assertEqual(NLMClient.run_web_research("nb1", "test query"), [])

    @patch("notebooklm_client.asyncio.run")
    @patch("notebooklm_client._available", return_value=True)
    def test_create_notebook_calls_asyncio_run(self, _, mock_run):
        from notebooklm_client import NLMClient
        mock_run.return_value = "nb-created-id"
        result = NLMClient.create_notebook("Test Notebook")
        self.assertEqual(result, "nb-created-id")
        mock_run.assert_called_once()

    @patch("notebooklm_client.asyncio.run", side_effect=Exception("auth failed"))
    @patch("notebooklm_client._available", return_value=True)
    def test_create_notebook_returns_none_on_exception(self, _, mock_run):
        from notebooklm_client import NLMClient
        result = NLMClient.create_notebook("test")
        self.assertIsNone(result)

    @patch("notebooklm_client.asyncio.run")
    @patch("notebooklm_client._available", return_value=True)
    def test_run_web_research_returns_list(self, _, mock_run):
        from notebooklm_client import NLMClient
        mock_run.return_value = [{"url": "https://example.com", "title": "Paper"}]
        result = NLMClient.run_web_research("nb1", "test query")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["url"], "https://example.com")

    @patch("notebooklm_client.asyncio.run", side_effect=Exception("network error"))
    @patch("notebooklm_client._available", return_value=True)
    def test_run_web_research_returns_empty_on_exception(self, _, mock_run):
        from notebooklm_client import NLMClient
        result = NLMClient.run_web_research("nb1", "test")
        self.assertEqual(result, [])


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
