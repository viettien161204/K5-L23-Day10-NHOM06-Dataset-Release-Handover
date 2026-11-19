#!/usr/bin/env python3
"""Validator cho Day 10 Lab (chi dung thu vien chuan Python + scripts/pngutil.py).

Chi doc thu muc <delivery> duoc truyen vao. Khong doc _private/, data_source/,
khong dung mang.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pngutil  # noqa: E402


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def load_classes(path: Path) -> dict[int, str]:
    classes: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cid_str, name = line.split(maxsplit=1)
        classes[int(cid_str)] = name
    return classes


def load_jobs(path: Path) -> dict[str, dict[str, str]]:
    jobs: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            jobs[row["job_id"]] = row
    return jobs


def count_mask_pixels(mask_path: Path) -> dict[int, int]:
    _, _, pixels = pngutil.read_rgb(mask_path)
    counts: dict[int, int] = {}
    for i in range(0, len(pixels), 3):
        sid = pixels[i] + (pixels[i + 1] << 8) + (pixels[i + 2] << 16)
        if sid:
            counts[sid] = counts.get(sid, 0) + 1
    return counts


def check_rules(delivery: Path) -> list[dict[str, str]]:
    found: list[tuple[str, str]] = []

    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))
    metadata = json.loads((delivery / "metadata.json").read_text(encoding="utf-8"))
    panoptic = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    classes = load_classes(delivery / "classes.txt")
    jobs = load_jobs(delivery / "jobs.csv")

    valid_class_ids = set(classes.keys())
    valid_cat_ids = {c["id"] for c in panoptic["categories"]}

    img_sizes: dict[str, tuple[int, int]] = {}
    for img_info in panoptic["images"]:
        stem = Path(img_info["file_name"]).stem
        img_sizes[stem] = (int(img_info["width"]), int(img_info["height"]))

    # 1. File checks: missing_image, wrong_hash
    # 2. Detection label checks: invalid_class, bbox_out_of_bounds, duplicate_box
    for img_id, item in manifest["items"].items():
        img_path = delivery / item["image"]
        lbl_path = delivery / item["label"]
        msk_path = delivery / item["mask"]

        if not img_path.is_file():
            found.append(("missing_image", img_id))

        hash_mismatch = False
        for file_path, expected_key in (
            (img_path, "image_sha256"),
            (lbl_path, "label_sha256"),
            (msk_path, "mask_sha256"),
        ):
            if file_path.is_file() and sha256_file(file_path) != item[expected_key]:
                hash_mismatch = True
                break
        if hash_mismatch:
            found.append(("wrong_hash", img_id))

        if lbl_path.is_file():
            w_img, h_img = img_sizes.get(img_id, (1, 1))
            boxes: list[tuple[int, float, float, float, float]] = []
            has_invalid_cls = False
            has_oob = False

            for raw_line in lbl_path.read_text(encoding="utf-8").splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                parts = raw_line.split()
                if len(parts) < 5:
                    has_invalid_cls = True
                    continue
                try:
                    cid = int(parts[0])
                    xc, yc, bw, bh = map(float, parts[1:5])
                except ValueError:
                    has_invalid_cls = True
                    continue

                if cid not in valid_class_ids:
                    has_invalid_cls = True

                if (
                    bw <= 0.0
                    or bh <= 0.0
                    or (xc - bw / 2.0) < -1e-6
                    or (yc - bh / 2.0) < -1e-6
                    or (xc + bw / 2.0) > 1.0 + 1e-6
                    or (yc + bh / 2.0) > 1.0 + 1e-6
                ):
                    has_oob = True

                boxes.append((cid, xc * w_img, yc * h_img, bw * w_img, bh * h_img))

            if has_invalid_cls:
                found.append(("invalid_class", img_id))
            if has_oob:
                found.append(("bbox_out_of_bounds", img_id))

            has_dup = False
            for i in range(len(boxes)):
                ci, xi, yi, wi, hi = boxes[i]
                for j in range(i + 1, len(boxes)):
                    cj, xj, yj, wj, hj = boxes[j]
                    if ci != cj:
                        continue
                    if (
                        abs(wi - wj) <= 2.5
                        and abs(hi - hj) <= 2.5
                        and abs(xi - xj) <= 3.5
                        and abs(yi - yj) <= 3.5
                    ):
                        has_dup = True
                        break
                if has_dup:
                    break
            if has_dup:
                found.append(("duplicate_box", img_id))

    # 3. Metadata checks: scene_leak, guideline_mismatch
    scene_splits: dict[str, set[str]] = defaultdict(set)
    for meta in metadata["items"]:
        img_id = meta["image"]
        scene_id = meta["scene_id"]
        scene_splits[scene_id].add(meta["split"])

        job = jobs.get(meta["job_id"])
        if job and meta["guideline_version"] != job["guideline"]:
            found.append(("guideline_mismatch", img_id))

    for scene_id, splits in scene_splits.items():
        if len(splits) > 1:
            found.append(("scene_leak", scene_id))

    # 4. Panoptic checks: invalid_category_id, thing_overlap
    for ann in panoptic["annotations"]:
        img_id = Path(ann["file_name"]).stem
        segments = ann["segments_info"]

        if any(seg["category_id"] not in valid_cat_ids for seg in segments):
            found.append(("invalid_category_id", img_id))

        item = manifest["items"].get(img_id)
        if not item:
            continue
        msk_path = delivery / item["mask"]
        if not msk_path.is_file():
            continue

        px_counts = count_mask_pixels(msk_path)
        if any(seg["area"] > px_counts.get(seg["id"], 0) for seg in segments):
            found.append(("thing_overlap", img_id))

    # Deduplicate while preserving order
    seen: set[tuple[str, str]] = set()
    errors: list[dict[str, str]] = []
    for err_type, target in found:
        if (err_type, target) not in seen:
            seen.add((err_type, target))
            errors.append({"type": err_type, "target": target})
    return errors


def bbox_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    return inter / (area_a + area_b - inter + 1e-12)


def find_candidates(delivery: Path, rule_errors: list[dict[str, str]]) -> list[dict[str, object]]:
    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))
    panoptic = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    classes = load_classes(delivery / "classes.txt")

    cat_by_id = {c["id"]: c for c in panoptic["categories"]}
    img_sizes: dict[str, tuple[int, int]] = {}
    for img_info in panoptic["images"]:
        stem = Path(img_info["file_name"]).stem
        img_sizes[stem] = (int(img_info["width"]), int(img_info["height"]))

    ann_by_img = {Path(ann["file_name"]).stem: ann for ann in panoptic["annotations"]}
    rule_error_imgs = {e["target"] for e in rule_errors if e["type"] != "scene_leak"}

    candidates: list[dict[str, object]] = []

    for img_id, item in manifest["items"].items():
        if img_id in rule_error_imgs:
            continue
        lbl_path = delivery / item["label"]
        msk_path = delivery / item["mask"]
        ann = ann_by_img.get(img_id)
        if not lbl_path.is_file() or not msk_path.is_file() or not ann:
            continue

        w_img, h_img = img_sizes.get(img_id, (0, 0))
        if w_img <= 0 or h_img <= 0:
            continue
        img_area = float(w_img * h_img)

        # Load YOLO boxes in pixel coords
        boxes: list[dict[str, object]] = []
        for raw_line in lbl_path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            parts = raw_line.split()
            cid = int(parts[0])
            xc, yc, bw, bh = map(float, parts[1:5])
            x1 = (xc - bw / 2.0) * w_img
            y1 = (yc - bh / 2.0) * h_img
            x2 = (xc + bw / 2.0) * w_img
            y2 = (yc + bh / 2.0) * h_img
            boxes.append({
                "idx": len(boxes),
                "class_name": classes[cid],
                "bbox": (x1, y1, x2, y2),
                "area": max(1.0, (x2 - x1) * (y2 - y1)),
            })

        # Keep non-crowd thing segments
        segs: dict[int, dict[str, object]] = {}
        for seg in ann["segments_info"]:
            cat = cat_by_id.get(seg["category_id"])
            if not cat or cat.get("isthing", 0) != 1 or seg.get("iscrowd", 0) == 1:
                continue
            sx, sy, sw, sh = seg["bbox"]
            segs[seg["id"]] = {
                "id": seg["id"],
                "class_name": cat["name"],
                "bbox": (float(sx), float(sy), float(sx + sw), float(sy + sh)),
                "area": int(seg["area"]),
            }

        if not segs and not boxes:
            continue

        # Count pixel overlaps between segments and boxes
        _, _, pixels = pngutil.read_rgb(msk_path)
        seg_px: dict[int, int] = defaultdict(int)
        overlap: dict[tuple[int, int], int] = defaultdict(int)  # (box_idx, seg_id) -> px

        # Pre-filter candidate boxes per segment by bbox intersection
        seg_cand_boxes: dict[int, list[dict[str, object]]] = {}
        for sid, s in segs.items():
            sb = s["bbox"]
            seg_cand_boxes[sid] = [b for b in boxes if bbox_iou(b["bbox"], sb) > 0.0]

        for y in range(h_img):
            row_off = y * w_img * 3
            for x in range(w_img):
                p = row_off + x * 3
                sid = pixels[p] + (pixels[p + 1] << 8) + (pixels[p + 2] << 16)
                if sid not in segs:
                    continue
                seg_px[sid] += 1
                for b in seg_cand_boxes[sid]:
                    bx1, by1, bx2, by2 = b["bbox"]
                    if bx1 <= x < bx2 and by1 <= y < by2:
                        overlap[(b["idx"], sid)] += 1

        img_cands: list[dict[str, object]] = []
        merged_sids: set[int] = set()
        swapped_sids: set[int] = set()
        swapped_boxes: set[int] = set()

        # Map each box to its primary same-class segment (highest pixel overlap)
        box_best_same_seg: dict[int, int] = {}
        for b in boxes:
            best_s = None
            best_ov = 0
            for sid, s in segs.items():
                if b["class_name"] != s["class_name"]:
                    continue
                ov = overlap.get((b["idx"], sid), 0)
                if ov > best_ov:
                    best_ov = ov
                    best_s = sid
            if best_s is not None:
                box_best_same_seg[b["idx"]] = best_s

        # 1. instance_merge: 1 segment is the primary match for >= 2 boxes of the same class
        for sid, s in segs.items():
            total = seg_px.get(sid, 0)
            if total < 800:
                continue
            same_boxes = [
                b for b in seg_cand_boxes[sid]
                if b["class_name"] == s["class_name"]
                and box_best_same_seg.get(b["idx"]) == sid
                and overlap.get((b["idx"], sid), 0) / total >= 0.15
                and overlap.get((b["idx"], sid), 0) / b["area"] >= 0.35
            ]
            if len(same_boxes) >= 2:
                merged_sids.add(sid)
                img_cands.append({
                    "image": img_id,
                    "type": "instance_merge",
                    "detail": f"segment {s['class_name']} ({total}px) phu {len(same_boxes)} box cung lop",
                    "bbox": s["bbox"],
                })

        # Best same-class match for each box & segment (to avoid false swaps)
        box_has_same = set()
        seg_has_same = set()
        for b in boxes:
            for sid, s in segs.items():
                if b["class_name"] != s["class_name"]:
                    continue
                total = max(1, seg_px.get(sid, 0))
                if overlap.get((b["idx"], sid), 0) / total >= 0.35 or bbox_iou(b["bbox"], s["bbox"]) >= 0.35:
                    box_has_same.add(b["idx"])
                    seg_has_same.add(sid)

        # 2. class_swap / category_swap: strong overlap, different class
        for b in boxes:
            if b["idx"] in box_has_same or b["area"] / img_area < 0.004:
                continue
            best_sid = None
            best_iou = 0.0
            for sid, s in segs.items():
                if sid in seg_has_same or b["class_name"] == s["class_name"]:
                    continue
                total = seg_px.get(sid, 0)
                if total < 800:
                    continue
                frac = overlap.get((b["idx"], sid), 0) / total
                iou = bbox_iou(b["bbox"], s["bbox"])
                if frac >= 0.55 and iou >= 0.45 and iou > best_iou:
                    best_iou = iou
                    best_sid = sid
            if best_sid is not None:
                s = segs[best_sid]
                swapped_sids.add(best_sid)
                swapped_boxes.add(b["idx"])
                img_cands.append({
                    "image": img_id,
                    "type": "class_swap_or_category_swap",
                    "detail": f"det={b['class_name']} vs pan={s['class_name']} (iou={best_iou:.2f})",
                    "bbox": b["bbox"],
                    "det_class": b["class_name"],
                    "pan_class": s["class_name"],
                })

        # 3. bbox_drift: same class match, but significant mask outside box or low IoU
        for b in boxes:
            if b["idx"] in swapped_boxes or b["area"] / img_area < 0.004:
                continue
            best_sid = None
            best_score = 0.0
            for sid, s in segs.items():
                if sid in merged_sids or b["class_name"] != s["class_name"]:
                    continue
                total = seg_px.get(sid, 0)
                if total < 400:
                    continue
                frac = overlap.get((b["idx"], sid), 0) / total
                iou = bbox_iou(b["bbox"], s["bbox"])
                if (frac >= 0.25 or iou >= 0.20) and iou > best_score:
                    best_score = iou
                    best_sid = sid
            if best_sid is not None:
                s = segs[best_sid]
                total = seg_px[best_sid]
                frac = overlap.get((b["idx"], best_sid), 0) / total
                iou = bbox_iou(b["bbox"], s["bbox"])
                if frac < 0.65 and iou < 0.60:
                    img_cands.append({
                        "image": img_id,
                        "type": "bbox_drift",
                        "detail": f"{b['class_name']} mask_in_box={frac:.2f} iou={iou:.2f}",
                        "bbox": b["bbox"],
                        "pan_bbox": s["bbox"],
                    })

        # 4. missing_box: large thing segment with no matching same-class box
        for sid, s in segs.items():
            if sid in merged_sids or sid in swapped_sids or sid in seg_has_same:
                continue
            total = seg_px.get(sid, 0)
            if total < 1500 or total / img_area < 0.005:
                continue
            img_cands.append({
                "image": img_id,
                "type": "missing_box",
                "detail": f"pan={s['class_name']} ({total}px) khong co box detection",
                "bbox": s["bbox"],
            })

        candidates.extend(img_cands)

    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Day 10 Lab Validator")
    parser.add_argument("delivery", type=Path, help="Thu muc delivery v1")
    parser.add_argument("--out", type=Path, required=True, help="File errors.json dau ra")
    parser.add_argument("--candidates", type=Path, default=None, help="File candidates.json (Pha 2)")
    args = parser.parse_args()

    errors = check_rules(args.delivery)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"errors": errors}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.candidates is not None:
        cands = find_candidates(args.delivery, errors)
        args.candidates.parent.mkdir(parents=True, exist_ok=True)
        args.candidates.write_text(json.dumps({"candidates": cands}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
