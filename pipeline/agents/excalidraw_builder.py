"""
Programmatic Excalidraw diagram builder for research session summaries.
Produces a valid .excalidraw JSON file — no LLM involved.

Layout (top → bottom):
  Title bar
  Research summary
  ─── Three columns ───────────────────────────────────
  Knowledge Gaps | Key Insights (confidence-coloured) | Top Directions
  ─────────────────────────────────────────────────────
  Proposed Workflow (numbered steps)
  Audit verdict badge
"""
import json
import re
import textwrap
import time
from pathlib import Path

# ── Colour palette ────────────────────────────────────────────────────────────
_TITLE_BG    = "#d8f3dc"
_TITLE_STR   = "#2d6a4f"
_SUMMARY_BG  = "#e8f4f8"
_SUMMARY_STR = "#1c7db5"
_GAP_BG      = "#fff2cc"
_GAP_STR     = "#b85c00"
_HIGH_BG     = "#d8f3dc"   # high confidence insight
_HIGH_STR    = "#2d6a4f"
_MED_BG      = "#fff2cc"   # medium confidence
_MED_STR     = "#b85c00"
_LOW_BG      = "#f8cecc"   # low confidence
_LOW_STR     = "#b85450"
_DIR_BG      = "#dae8fc"
_DIR_STR     = "#1c3d6b"
_FLOW_BG     = "#f3e8ff"
_FLOW_STR    = "#5a2d8f"
_PASS_BG     = "#d8f3dc"
_PASS_STR    = "#2d6a4f"
_REVISE_BG   = "#f8cecc"
_REVISE_STR  = "#b85450"
_ARROW_CLR   = "#364fc7"

# ── Geometry ──────────────────────────────────────────────────────────────────
_MARGIN      = 40
_COL_W       = 440
_COL_GAP     = 30
_BOX_PAD_Y   = 20
_FONT_SIZE   = 13
_TITLE_FONT  = 22
_HEAD_FONT   = 16
_LINE_H      = 1.35
_SEED        = 200_000


def _uid(n: int) -> str:
    return f"ex{_SEED + n:06d}"


def _wrap(text: str, width: int = 52) -> str:
    """Wrap text to width chars, join with newline."""
    return "\n".join(textwrap.wrap(text, width=width))


def _box_height(text: str, font_size: int = _FONT_SIZE, line_h: float = _LINE_H) -> int:
    lines = text.count("\n") + 1
    return max(60, int(lines * font_size * line_h) + _BOX_PAD_Y * 2)


def _rect(eid: int, x: int, y: int, w: int, h: int,
          bg: str, stroke: str, rough: int = 1, radius: bool = True,
          dashed: bool = False) -> dict:
    return {
        "id": _uid(eid), "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h, "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": 2,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": rough, "opacity": 100,
        "groupIds": [], "frameId": None,
        "roundness": {"type": 3} if radius else None,
        "seed": _SEED + eid, "version": 1, "versionNonce": _SEED + eid,
        "isDeleted": False,
        "boundElements": [{"type": "text", "id": _uid(eid + 1)}],
        "updated": int(time.time() * 1000), "link": None, "locked": False,
    }


def _text(eid: int, x: int, y: int, w: int, h: int,
          text: str, font_size: int = _FONT_SIZE,
          align: str = "center", color: str = "#1e1e1e",
          container: int | None = None) -> dict:
    cid = _uid(container) if container is not None else None
    return {
        "id": _uid(eid), "type": "text",
        "x": x, "y": y, "width": w, "height": h, "angle": 0,
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None,
        "seed": _SEED + eid, "version": 1, "versionNonce": _SEED + eid,
        "isDeleted": False, "boundElements": [],
        "updated": int(time.time() * 1000), "link": None, "locked": False,
        "text": text, "fontSize": font_size, "fontFamily": 2,
        "textAlign": align, "verticalAlign": "middle",
        "containerId": cid, "originalText": text, "lineHeight": _LINE_H,
    }


def _arrow(eid: int, x1: int, y1: int, dx: int, dy: int,
           color: str = _ARROW_CLR, dashed: bool = False) -> dict:
    return {
        "id": _uid(eid), "type": "arrow",
        "x": x1, "y": y1, "width": abs(dx), "height": abs(dy), "angle": 0,
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": 0, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": {"type": 2},
        "seed": _SEED + eid, "version": 1, "versionNonce": _SEED + eid,
        "isDeleted": False, "boundElements": [],
        "updated": int(time.time() * 1000), "link": None, "locked": False,
        "points": [[0, 0], [dx, dy]],
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": "arrow",
    }


# ── Parsers ───────────────────────────────────────────────────────────────────

def _section(text: str, heading: str) -> str:
    """Extract text under a markdown heading until the next heading."""
    pattern = rf"#{1,3}\s+{re.escape(heading)}[^\n]*\n(.*?)(?=\n#{1,3}\s|\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _bullets(text: str) -> list[str]:
    return [re.sub(r"^\s*[-*•]\s*\**", "", l).strip()
            for l in text.splitlines() if re.match(r"^\s*[-*•]", l)]


def _parse_insights(mod_handoff: str) -> list[dict]:
    """Extract #### insight blocks from Mod handoff."""
    insights = []
    blocks = re.findall(r"#### (.+?)\n((?:- \*\*.+?\n)+)", mod_handoff, re.MULTILINE)
    for title, block in blocks:
        fields = dict(re.findall(r"- \*\*(.+?):\*\* (.+)", block))
        insights.append({
            "title": title.strip()[:60],
            "fact": fields.get("Fact", "")[:120],
            "status": fields.get("Status", ""),
            "confidence": fields.get("Confidence", "Medium"),
        })
    return insights[:12]  # cap at 12


def _parse_directions(nam_handoff: str) -> list[str]:
    """Extract direction names from Nam table."""
    rows = re.findall(r"\|\s*\d+\s*\|\s*\*?\*?(.+?)\*?\*?\s*\|", nam_handoff)
    return [r.strip()[:70] for r in rows[:5]]


def _parse_workflow(dao_handoff: str) -> list[str]:
    """Extract numbered steps from Proposed Workflow section."""
    section = _section(dao_handoff, "Proposed Workflow")
    steps = re.findall(r"\d+\.\s+\*?\*?(.+?)(?:\n|$)", section)
    return [s.strip()[:80] for s in steps[:8]]


def _audit_verdict(som_handoff: str, manao_handoff: str) -> str:
    sv = "PASS" if "VERDICT: PASS" in som_handoff else "REVISE"
    mv = "PASS" if "VERDICT: PASS" in manao_handoff else "REVISE"
    if sv == "PASS" and mv == "PASS":
        return "PASS"
    return f"REVISE (Som:{sv} Manao:{mv})"


# ── Main builder ──────────────────────────────────────────────────────────────

def build(
    topic: str,
    nam_handoff: str,
    mod_handoff: str,
    dao_handoff: str,
    som_handoff: str,
    manao_handoff: str,
    run_id: str,
) -> dict:
    elements: list[dict] = []
    eid = 0  # sequential element ID counter

    total_w = _MARGIN * 2 + _COL_W * 3 + _COL_GAP * 2  # ≈1480
    cx = total_w // 2
    y = _MARGIN

    # ── Title ─────────────────────────────────────────────────────────────────
    title_text = _wrap(topic, width=80)
    sub_text = f"Run: {run_id[:10]}   ·   MLIP Research Brief"
    title_h = _box_height(title_text, _TITLE_FONT) + 30
    elements += [
        _rect(eid, _MARGIN, y, total_w - _MARGIN * 2, title_h,
              _TITLE_BG, _TITLE_STR, rough=0),
        _text(eid + 1, _MARGIN, y, total_w - _MARGIN * 2, title_h,
              f"{title_text}\n{sub_text}", _TITLE_FONT, color=_TITLE_STR, container=eid),
    ]
    eid += 2; y += title_h + _MARGIN

    # ── Research Summary ──────────────────────────────────────────────────────
    summary_raw = _section(nam_handoff, "Research Summary")
    summary_text = _wrap(summary_raw[:400], width=110)
    sum_h = _box_height(summary_text, _FONT_SIZE) + 10
    elements += [
        _rect(eid, _MARGIN, y, total_w - _MARGIN * 2, sum_h,
              _SUMMARY_BG, _SUMMARY_STR, rough=0),
        _text(eid + 1, _MARGIN, y, total_w - _MARGIN * 2, sum_h,
              summary_text, _FONT_SIZE, color=_SUMMARY_STR, container=eid),
    ]
    eid += 2; y += sum_h + _MARGIN

    # ── Section headers ───────────────────────────────────────────────────────
    col_xs = [_MARGIN, _MARGIN + _COL_W + _COL_GAP, _MARGIN + (_COL_W + _COL_GAP) * 2]
    headers = ["Knowledge Gaps", "Key Insights", "Top Directions"]
    header_colors = [(_GAP_BG, _GAP_STR), (_HIGH_BG, _HIGH_STR), (_DIR_BG, _DIR_STR)]

    for i, (cx_i, hdr, (hbg, hstr)) in enumerate(zip(col_xs, headers, header_colors)):
        elements += [
            _rect(eid, cx_i, y, _COL_W, 40, hbg, hstr, rough=0, radius=False),
            _text(eid + 1, cx_i, y, _COL_W, 40, hdr, _HEAD_FONT, color=hstr, container=eid),
        ]
        eid += 2
    y += 40 + 10

    # ── Three columns ─────────────────────────────────────────────────────────
    col_y = [y, y, y]

    # Column 1: Knowledge Gaps
    gaps = _bullets(_section(nam_handoff, "Knowledge Gaps"))[:7]
    for gap in gaps:
        txt = _wrap(gap, width=50)
        h = _box_height(txt)
        elements += [
            _rect(eid, col_xs[0], col_y[0], _COL_W, h, _GAP_BG, _GAP_STR),
            _text(eid + 1, col_xs[0], col_y[0], _COL_W, h, txt,
                  _FONT_SIZE, color=_GAP_STR, container=eid),
        ]
        eid += 2; col_y[0] += h + 8

    # Column 2: Key Insights (colour-coded by confidence)
    insights = _parse_insights(mod_handoff)
    conf_colours = {
        "high": (_HIGH_BG, _HIGH_STR),
        "medium": (_MED_BG, _MED_STR),
        "low": (_LOW_BG, _LOW_STR),
    }
    for ins in insights:
        conf_key = ins["confidence"].lower().split()[0] if ins["confidence"] else "medium"
        ibg, istr = conf_colours.get(conf_key, (_MED_BG, _MED_STR))
        inner = f"{_wrap(ins['title'], 46)}\n{_wrap(ins['fact'], 46)}\n[{ins['status']} · {ins['confidence']}]"
        h = _box_height(inner)
        elements += [
            _rect(eid, col_xs[1], col_y[1], _COL_W, h, ibg, istr),
            _text(eid + 1, col_xs[1], col_y[1], _COL_W, h, inner,
                  _FONT_SIZE - 1, color=istr, container=eid),
        ]
        eid += 2; col_y[1] += h + 8

    # Column 3: Top Directions
    directions = _parse_directions(nam_handoff)
    dir_rows = re.findall(
        r"\|\s*\d+\s*\|.*?\|\s*(.+?)\s*\|\s*(Low|Medium|High)\s*\|\s*(.+?)\s*\|",
        nam_handoff,
    )
    for i, direction in enumerate(directions):
        effort = dir_rows[i][1] if i < len(dir_rows) else ""
        risk = dir_rows[i][2][:60] if i < len(dir_rows) else ""
        inner = f"{i+1}. {_wrap(direction, 44)}"
        if effort:
            inner += f"\nEffort: {effort}"
        if risk:
            inner += f"\nRisk: {_wrap(risk, 44)}"
        h = _box_height(inner)
        elements += [
            _rect(eid, col_xs[2], col_y[2], _COL_W, h, _DIR_BG, _DIR_STR),
            _text(eid + 1, col_xs[2], col_y[2], _COL_W, h, inner,
                  _FONT_SIZE, color=_DIR_STR, container=eid),
        ]
        eid += 2; col_y[2] += h + 8

    y = max(col_y) + _MARGIN

    # ── Proposed Workflow ─────────────────────────────────────────────────────
    workflow = _parse_workflow(dao_handoff)
    if workflow:
        # Section header
        elements += [
            _rect(eid, _MARGIN, y, total_w - _MARGIN * 2, 40,
                  _FLOW_BG, _FLOW_STR, rough=0, radius=False),
            _text(eid + 1, _MARGIN, y, total_w - _MARGIN * 2, 40,
                  "Proposed Workflow", _HEAD_FONT, color=_FLOW_STR, container=eid),
        ]
        eid += 2; y += 40 + 10

        step_w = (total_w - _MARGIN * 2 - _COL_GAP * (len(workflow) - 1)) // len(workflow)
        sx = _MARGIN
        max_step_y = y
        for i, step in enumerate(workflow):
            txt = f"{i+1}. {_wrap(step, 28)}"
            h = _box_height(txt) + 10
            elements += [
                _rect(eid, sx, y, step_w, h, _FLOW_BG, _FLOW_STR),
                _text(eid + 1, sx, y, step_w, h, txt,
                      _FONT_SIZE - 1, color=_FLOW_STR, container=eid),
            ]
            if i < len(workflow) - 1:
                elements.append(
                    _arrow(eid + 2, sx + step_w, y + h // 2, _COL_GAP, 0)
                )
                eid += 3
            else:
                eid += 2
            sx += step_w + _COL_GAP
            max_step_y = max(max_step_y, y + h)
        y = max_step_y + _MARGIN

    # ── Audit verdict badge ───────────────────────────────────────────────────
    verdict = _audit_verdict(som_handoff, manao_handoff)
    is_pass = verdict == "PASS"
    vbg = _PASS_BG if is_pass else _REVISE_BG
    vstr = _PASS_STR if is_pass else _REVISE_STR
    vtxt = f"Audit Verdict: {verdict}"
    vh = 60
    vw = min(600, total_w - _MARGIN * 2)
    elements += [
        _rect(eid, cx - vw // 2, y, vw, vh, vbg, vstr, rough=0),
        _text(eid + 1, cx - vw // 2, y, vw, vh, vtxt, _HEAD_FONT, color=vstr, container=eid),
    ]
    eid += 2

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": "#ffffff",
        },
        "files": {},
    }


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
