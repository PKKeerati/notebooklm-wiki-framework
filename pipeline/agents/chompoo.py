import re
import time
from .base import BaseAgent
from .utils import search_semantic_scholar, paper_citation, extract_search_keywords

SYSTEM = """\
You are Chompoo, the Literature Verifier in a research pipeline.

Your job: for each "Done" atomic insight from Mod, find the real published paper that supports it,
using the Semantic Scholar search results provided.

Rules:
- If a matching paper is found: attach the full citation (authors, year, title, DOI or arXiv link).
- If no confident match: mark as "Unverified — no supporting paper found."
- Match confidence: HIGH = title/abstract clearly supports the claim; MEDIUM = partial match; LOW = tangential.
- Only mark VERIFIED if confidence is HIGH or MEDIUM.
- For "Ongoing" and "Not done" insights: pass through unchanged — do not search or modify.
- Do not invent citations. Only use papers from the provided search results.

Output EXACTLY this Markdown:

## Chompoo Handoff — Literature Verification

**Verified:** N / Done: M

### Verified Insights
#### [Insight title]
- **Fact:** [original fact from Mod]
- **Status:** Done
- **Citation:** Authors et al. (Year). Title. DOI/arXiv URL
- **Match confidence:** High / Medium
- **Notes:** [optional — what aspect of the paper supports the claim]

### Unverified Insights
#### [Insight title]
- **Fact:** [original fact from Mod]
- **Status:** Done
- **Citation:** Unverified — no supporting paper found
- **Search terms used:** [the query sent to Semantic Scholar]

### Ongoing / Not Done Insights
#### [Insight title]
- **Fact:** [original fact]
- **Status:** Ongoing / Not done
- **Est. completion:** [year]
- **Confidence:** [original]
"""




def _extract_done_insights(mod_handoff: str) -> list[dict]:
    """Parse Mod handoff and return list of Done insights with title and fact."""
    insights = []
    blocks = re.split(r"^#### ", mod_handoff, flags=re.MULTILINE)
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        title = lines[0].strip()
        fact_m = re.search(r"\*\*Fact:\*\*\s*(.+)", block)
        status_m = re.search(r"\*\*Status:\*\*\s*(.+)", block)
        est_m = re.search(r"\*\*Est\. completion:\*\*\s*(.+)", block)
        conf_m = re.search(r"\*\*Confidence:\*\*\s*(.+)", block)
        tags_m = re.search(r"\*\*Topic tags:\*\*\s*(.+)", block)
        insights.append({
            "title": title,
            "fact": fact_m.group(1).strip() if fact_m else "",
            "status": status_m.group(1).strip() if status_m else "",
            "est": est_m.group(1).strip() if est_m else "N/A",
            "confidence": conf_m.group(1).strip() if conf_m else "",
            "tags": tags_m.group(1).strip() if tags_m else "",
        })
    return insights


class ChompooAgent(BaseAgent):
    def run(self, state: dict) -> dict:
        mod_handoff = self._read_handoff("mod")
        insights = _extract_done_insights(mod_handoff)

        done_insights = [i for i in insights if i["status"].lower() == "done"]
        other_insights = [i for i in insights if i["status"].lower() != "done"]

        # Search Semantic Scholar for each Done insight using keyword extraction
        search_results: list[dict] = []
        for insight in done_insights:
            query = extract_search_keywords(insight["title"], insight["fact"])
            print(f"  Searching [{query[:50]}]...")
            papers = search_semantic_scholar(query, limit=5)
            search_results.append({"insight": insight, "papers": papers, "query": query})
            time.sleep(1)  # respect rate limit

        # Build user message for LLM
        search_block = ""
        for item in search_results:
            ins = item["insight"]
            papers = item["papers"]
            query = item.get("query", "")
            search_block += f"\n### Insight: {ins['title']}\n"
            search_block += f"Fact: {ins['fact']}\n"
            search_block += f"Search query used: {query}\n"
            if papers:
                search_block += "Search results:\n"
                for p in papers:
                    search_block += f"- {paper_citation(p)}\n"
                    if p.get("abstract"):
                        search_block += f"  Abstract (first 150 chars): {p['abstract'][:150]}...\n"
            else:
                search_block += "Search results: None found\n"

        other_block = ""
        for ins in other_insights:
            other_block += (
                f"\n### {ins['title']}\n"
                f"Status: {ins['status']}\n"
                f"Fact: {ins['fact']}\n"
                f"Est. completion: {ins['est']}\n"
                f"Confidence: {ins['confidence']}\n"
            )

        user_msg = (
            f"Done insights to verify (with Semantic Scholar results):\n{search_block}\n\n"
            f"Ongoing / Not Done insights (pass through unchanged):\n{other_block or 'None'}"
        )

        handoff = self._llm(SYSTEM, user_msg, max_tokens=2000)
        self._write_handoff("chompoo", handoff)

        verified = len(re.findall(r"Match confidence:", handoff))
        return {"chompoo_verified": verified, "chompoo_total_done": len(done_insights)}
