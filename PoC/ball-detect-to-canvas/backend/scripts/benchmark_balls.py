"""Evaluate ball centers/types against public Pix2Pockets tournament annotations.

Download the pinned 8-Ball-Pool-3.zip separately (see README); no network, model
weights, training, or table-corner ground truth is used by this script.
"""

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models import DetectionRequest
from app.vision import detect, suggest_corners

SHA256 = "39153bb1225370d7fa9c458988acd25d5b356f59ddc6a95d7f45c773ffca534f"
KINDS = {0: "eight", 1: "cue", 3: "solid", 4: "striped"}  # class 2 = table dot


def labels_for(text, width, height):
    labels = []
    for line in text.splitlines():
        values = list(map(float, line.split()))
        kind = KINDS.get(int(values[0]))
        if kind is None:
            continue
        if len(values) == 5:
            x, y, w, h = values[1:]
        else:
            polygon = np.asarray(values[1:]).reshape(-1, 2)
            low, high = polygon.min(axis=0), polygon.max(axis=0)
            x, y = (low + high) / 2
            w, h = high - low
        labels.append(
            {
                "kind": kind,
                "x": x * width,
                "y": y * height,
                "w": w * width,
                "h": h * height,
            }
        )
    return labels


def match_centers(balls, labels, width, height):
    # Same criterion for baseline and new pipeline; this is NOT bounding-box AP.
    pairs = sorted(
        (
            np.hypot(
                b["source_x"] * width - label["x"], b["source_y"] * height - label["y"]
            )
            / max(label["w"], label["h"]),
            i,
            j,
        )
        for i, b in enumerate(balls)
        for j, label in enumerate(labels)
    )
    used_balls, used_labels, matched = set(), set(), []
    for distance, i, j in pairs:
        if distance > 0.65 or i in used_balls or j in used_labels:
            continue
        used_balls.add(i)
        used_labels.add(j)
        matched.append([labels[j]["kind"], balls[i]["kind"]])
    return matched


def run(archive, split):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Dataset checksum differs from the documented version.")
    rows = []
    cv2.setNumThreads(4)
    with zipfile.ZipFile(archive) as source:
        files = sorted(
            n for n in source.namelist() if "/train/images/" in n and n.endswith(".jpg")
        )
        for filename in files:
            group = int(re.match(r"\d+", Path(filename).name)[0])
            partition = "holdout" if group % 5 == 0 else "development"
            if split != "all" and partition != split:
                continue
            image = cv2.imdecode(
                np.frombuffer(source.read(filename), np.uint8), cv2.IMREAD_COLOR
            )
            height, width = image.shape[:2]
            labels = labels_for(
                source.read(
                    filename.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
                ).decode(),
                width,
                height,
            )
            start = perf_counter()
            corners = suggest_corners(image)
            balls = []
            if corners:
                request = DetectionRequest.model_validate(
                    {
                        "calibration": {
                            "image_width": width,
                            "image_height": height,
                            "corners": corners,
                        }
                    }
                )
                balls = detect(image, request, debug=False)["balls"]
            elapsed = (perf_counter() - start) * 1000
            matches = match_centers(balls, labels, width, height)
            rows.append(
                {
                    "file": Path(filename).name,
                    "split": partition,
                    "labels": len(labels),
                    "detections": len(balls),
                    "matches": matches,
                    "missed": len(labels) - len(matches),
                    "extra": len(balls) - len(matches),
                    "elapsed_ms": round(elapsed, 1),
                }
            )
    summaries = {}
    for partition in ("development", "holdout"):
        selected = [r for r in rows if r["split"] == partition]
        if not selected:
            continue
        matches = [m for row in selected for m in row["matches"]]
        total = sum(r["labels"] for r in selected)
        detections = sum(r["detections"] for r in selected)
        summaries[partition] = {
            "frames": len(selected),
            "annotated_balls": total,
            "matched": len(matches),
            "missed": total - len(matches),
            "extra": detections - len(matches),
            "precision": round(len(matches) / max(1, detections), 4),
            "recall": round(len(matches) / max(1, total), 4),
            "matched_type_accuracy": round(
                sum(a == b for a, b in matches) / max(1, len(matches)), 4
            ),
            "correctly_located_and_typed": round(
                sum(a == b for a, b in matches) / max(1, total), 4
            ),
            "confusion": dict(Counter(f"{a}->{b}" for a, b in matches)),
            "median_ms": round(
                float(np.median([r["elapsed_ms"] for r in selected])), 1
            ),
        }
    return {"dataset_sha256": SHA256, "summaries": summaries, "frames": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--split", choices=["development", "holdout", "all"], default="holdout"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.archive, args.split)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result["summaries"], indent=2))
