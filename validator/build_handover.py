#!/usr/bin/env python3
"""Dong goi lo ban giao v2 (Pha 4) va truy vet ticket (Pha 5) - Pham Thanh Tung."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

DET_REWORK_TYPES = {
    "missing_image",
    "invalid_class",
    "bbox_out_of_bounds",
    "duplicate_box",
    "class_swap",
    "bbox_drift",
    "missing_box",
}
PAN_ONLY_TYPES = {
    "invalid_category_id",
    "thing_overlap",
    "category_swap",
    "instance_merge",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def is_valid_jpeg(path: Path) -> bool:
    if not path.is_file():
        return False
    data = path.read_bytes()
    return len(data) > 4 and data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"


def load_classes(path: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cid, name = line.strip().split(maxsplit=1)
            out[int(cid)] = name
    return out


def loading_class(path: Path) -> dict[int, str]:
    """Doc file classes (moi dong: '<id> <ten>') va tra ve dict {id: ten}."""
    return load_classes(path)


def build_v2_and_trace(run_dir: Path) -> None:
    delivery = run_dir / "delivery"
    errors_data = json.loads((run_dir / "errors.json").read_text(encoding="utf-8"))["errors"]
    release_info = json.loads((delivery / "release.json").read_text(encoding="utf-8"))
    release_id = release_info["release_id"]

    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]
    metadata_items = json.loads((delivery / "metadata.json").read_text(encoding="utf-8"))["items"]
    classes = load_classes(delivery / "classes.txt")

    jobs: dict[str, dict[str, str]] = {}
    with (delivery / "jobs.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            jobs[row["job_id"]] = row

    meta_by_img = {m["image"]: m for m in metadata_items}

    # Phan loai loi
    rework_imgs: dict[str, str] = {}
    pan_imgs: list[tuple[str, str]] = []
    wrong_hash_imgs: list[str] = []
    guideline_fix_imgs: list[str] = []
    leak_scenes: list[str] = []

    for err in errors_data:
        etype, target = err["type"], err["target"]
        if etype in DET_REWORK_TYPES:
            rework_imgs[target] = etype
        elif etype == "wrong_hash":
            img_path = delivery / manifest[target]["image"]
            if is_valid_jpeg(img_path):
                wrong_hash_imgs.append(target)
            else:
                rework_imgs[target] = etype
        elif etype in PAN_ONLY_TYPES:
            pan_imgs.append((target, etype))
        elif etype == "guideline_mismatch":
            guideline_fix_imgs.append(target)
        elif etype == "scene_leak":
            leak_scenes.append(target)

    # Xu ly scene_leak: dua ca canh ve split da so
    scene_splits: dict[str, Counter[str]] = defaultdict(Counter)
    for m in metadata_items:
        scene_splits[m["scene_id"]][m["split"]] += 1
    fixed_scene_split: dict[str, str] = {}
    for sid in leak_scenes:
        fixed_scene_split[sid] = scene_splits[sid].most_common(1)[0][0]

    v2_dir = run_dir / "handover" / f"{release_id}_v2"
    if v2_dir.exists():
        shutil.rmtree(v2_dir)
    (v2_dir / "images").mkdir(parents=True)
    (v2_dir / "labels").mkdir(parents=True)

    # Copy anh/nhan sach sang v2 & tinh manifest + label_summary + truyvet
    manifest_rows: list[tuple[str, str]] = []
    class_counts: Counter[str] = Counter()
    truyvet_rows: list[list[str]] = []
    kept_images = 0

    for img_id in sorted(manifest.keys()):
        if img_id in rework_imgs:
            continue
        item = manifest[img_id]
        src_img = delivery / item["image"]
        src_lbl = delivery / item["label"]
        dst_img = v2_dir / "images" / f"{img_id}.jpg"
        dst_lbl = v2_dir / "labels" / f"{img_id}.txt"
        shutil.copy2(src_img, dst_img)
        shutil.copy2(src_lbl, dst_lbl)
        kept_images += 1

        manifest_rows.append((f"images/{img_id}.jpg", sha256_file(dst_img)))
        manifest_rows.append((f"labels/{img_id}.txt", sha256_file(dst_lbl)))

        for line in dst_lbl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cid = int(line.split()[0])
                class_counts[classes[cid]] += 1

        m = meta_by_img[img_id]
        job = jobs[m["job_id"]]
        split = fixed_scene_split.get(m["scene_id"], m["split"])
        truyvet_rows.append([
            img_id,
            m["scene_id"],
            split,
            m["job_id"],
            job["annotator"],
            job["reviewer"],
            job["guideline"],
        ])

    # rework_queue.csv
    with (v2_dir / "rework_queue.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "type", "annotator", "reviewer", "action"])
        for img_id in sorted(rework_imgs.keys()):
            m = meta_by_img[img_id]
            job = jobs[m["job_id"]]
            w.writerow([img_id, rework_imgs[img_id], job["annotator"], job["reviewer"], "re_annotate_and_review"])

    # manifest.csv
    with (v2_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256"])
        for rel, h in sorted(manifest_rows):
            w.writerow([rel, h])

    # label_summary.csv
    total_labels = 0
    with (v2_dir / "label_summary.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["class", "count"])
        for cid in sorted(classes.keys()):
            cname = classes[cid]
            cnt = class_counts[cname]
            if cnt > 0:
                total_labels += cnt
                w.writerow([cname, cnt])
        w.writerow(["TOTAL", total_labels])

    # truyvet.csv
    with (v2_dir / "truyvet.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"])
        for row in truyvet_rows:
            w.writerow(row)

    # README.txt
    v1_total = len(manifest)
    err_cnt = len(errors_data)
    err_pct = (err_cnt / v1_total) * 100.0
    gl_groups: dict[str, list[str]] = defaultdict(list)
    for jid in sorted(jobs.keys()):
        gl_groups[jobs[jid]["guideline"]].append(jid)
    gl_str = ", ".join(f"{gl} ({jids[0]}-{jids[-1]})" for gl, jids in sorted(gl_groups.items()))

    pan_note = ", ".join(f"{im} ({tp})" for im, tp in pan_imgs) if pan_imgs else "khong co"
    readme_text = (
        f"Release: {release_id}_v2\n"
        f"Parent: {release_id}\n"
        f"Số ảnh: {kept_images}\n"
        f"Số nhãn: {total_labels}\n"
        f"Guideline: {gl_str}\n"
        f"QC v1: {err_cnt}/{v1_total} = {err_pct:.1f}%\n"
        f"Kết luận v1: Hold — vuot nguong 2% ({err_pct:.1f}% > 2.0%), khong duoc train truc tiep.\n"
        f"Kết luận v2: Release — da tach {len(rework_imgs)} anh loi detection vao rework_queue.csv, sua metadata/hash; giu nguyen nhan sach.\n"
        f"Ghi chú: Da sua scene_leak ({', '.join(leak_scenes) or 'khong'}) ve mot split; "
        f"da mo kiem anh wrong_hash ({', '.join(wrong_hash_imgs) or 'khong'}) con nguyen ven va cap nhat sha256 moi; "
        f"sua guideline_mismatch ({', '.join(guideline_fix_imgs) or 'khong'}) theo jobs.csv; "
        f"anh loi chi o panoptic van o lai v2 va bao team panoptic: {pan_note}.\n"
    )
    (v2_dir / "README.txt").write_text(readme_text, encoding="utf-8")

    # Pha 5: Truy vet ticket -> trace.json
    ticket_text = (delivery / "incoming" / "ticket.md").read_text(encoding="utf-8")
    changelog_text = (delivery / "guideline" / "changelog.md").read_text(encoding="utf-8")

    ticket_scenes = set(re.findall(r"scene_\d+", ticket_text))
    m_cls = re.search(r"`([a-zA-Z0-9_ ]+)`", ticket_text) or re.search(r"Lớp\s+`([^`]+)`", changelog_text)
    target_class = m_cls.group(1).strip() if m_cls else "surfboard"
    name_to_cid = {v: k for k, v in classes.items()}
    target_cid = name_to_cid[target_class]

    # Guideline cu = phien ban nho nhat trong jobs.csv
    old_guideline = sorted({j["guideline"] for j in jobs.values()})[0]

    tier_a: list[str] = []
    tier_b: list[str] = []
    notify: set[str] = set()

    for img_id in sorted(manifest.keys()):
        m = meta_by_img[img_id]
        job = jobs[m["job_id"]]
        if job["guideline"] != old_guideline:
            continue
        lbl_path = delivery / manifest[img_id]["label"]
        if not lbl_path.is_file():
            continue
        has_target_box = any(
            int(line.split()[0]) == target_cid
            for line in lbl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if not has_target_box:
            continue
        if m["scene_id"] in ticket_scenes:
            tier_a.append(img_id)
        else:
            tier_b.append(img_id)
        notify.add(job["annotator"])
        notify.add(job["reviewer"])

    trace_out = {
        "tier_a": tier_a,
        "tier_b": tier_b,
        "notify": sorted(notify),
    }
    (run_dir / "trace.json").write_text(json.dumps(trace_out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Built v2 at {v2_dir} ({kept_images} images, {total_labels} labels)")
    print(f"Built trace.json: tier_a={len(tier_a)}, tier_b={len(tier_b)}, notify={sorted(notify)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build v2 handover and trace.json")
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    build_v2_and_trace(args.run)


if __name__ == "__main__":
    main()
