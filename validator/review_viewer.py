#!/usr/bin/env python3
"""Cong cu ho tro xem anh ung vien (Pham Lam Anh).

Sinh file HTML tuong tac de 5 thanh vien mo bang trinh duyet, xem ro box
detection (do) va bbox panoptic (xanh) tren anh goc, roi ghi review_log.csv.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

MEMBERS = [
    "Nguyen Viet Tien",
    "Nguyen Minh Duc",
    "Lam Trung Hieu",
    "Pham Lam Anh",
    "Pham Thanh Tung",
]


def build_gallery(delivery: Path, candidates_path: Path, out_html: Path) -> None:
    cands = json.loads(candidates_path.read_text(encoding="utf-8"))["candidates"]
    panoptic = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    sizes = {
        Path(im["file_name"]).stem: (int(im["width"]), int(im["height"]))
        for im in panoptic["images"]
    }

    cards: list[str] = []
    for idx, c in enumerate(cands):
        img_id = c["image"]
        w, h = sizes.get(img_id, (640, 480))
        reviewer = MEMBERS[idx % len(MEMBERS)]
        img_rel = f"delivery/images/{img_id}.jpg"
        bx1, by1, bx2, by2 = c.get("bbox", [0, 0, 0, 0])
        pan_box = c.get("pan_bbox")

        svg_rects = (
            f'<rect x="{bx1:.1f}" y="{by1:.1f}" width="{bx2-bx1:.1f}" height="{by2-by1:.1f}" '
            f'fill="none" stroke="#ff3b30" stroke-width="2.5"/>'
        )
        if pan_box:
            px1, py1, px2, py2 = pan_box
            svg_rects += (
                f'<rect x="{px1:.1f}" y="{py1:.1f}" width="{px2-px1:.1f}" height="{py2-py1:.1f}" '
                f'fill="none" stroke="#00e5ff" stroke-width="2" stroke-dasharray="5,3"/>'
            )

        cards.append(
            f"""
            <div class="card">
              <div class="meta">
                <b>#{idx+1} [{html.escape(reviewer)}]</b> &mdash;
                <code>{html.escape(img_id)}</code> |
                <span class="badge">{html.escape(str(c["type"]))}</span>
              </div>
              <div class="detail">{html.escape(str(c.get("detail", "")))}</div>
              <div class="img-wrap">
                <svg viewBox="0 0 {w} {h}" class="overlay">
                  <image href="{img_rel}" width="{w}" height="{h}"/>
                  {svg_rects}
                </svg>
              </div>
            </div>
            """
        )

    page = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Review Gallery ({len(cands)} candidates)</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #111827; color: #f3f4f6; margin: 20px; }}
  h1 {{ font-size: 20px; }}
  .legend {{ margin-bottom: 16px; font-size: 14px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 16px; }}
  .card {{ background: #1f2937; border: 1px solid #374151; border-radius: 8px; padding: 12px; }}
  .meta {{ font-size: 14px; margin-bottom: 4px; }}
  .detail {{ font-size: 13px; color: #9ca3af; margin-bottom: 8px; }}
  .badge {{ background: #7c3aed; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
  .overlay {{ width: 100%; height: auto; border-radius: 4px; display: block; }}
</style>
</head>
<body>
  <h1>Review Gallery &mdash; {len(cands)} ung vien</h1>
  <div class="legend">
    <span style="color:#ff3b30;">&#9632; Box chinh (Detection / ung vien)</span> &nbsp;|&nbsp;
    <span style="color:#00e5ff;">&#9632; Box Panoptic (neu co)</span>
  </div>
  <div class="grid">
    {"".join(cards)}
  </div>
</body>
</html>
"""
    out_html.write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinh trang HTML xem anh ung vien")
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build_gallery(args.delivery, args.candidates, args.out)


if __name__ == "__main__":
    main()
