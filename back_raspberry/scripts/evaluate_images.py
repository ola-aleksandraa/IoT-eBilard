"""Offline evaluation of local photos; annotations are local QA artifacts, never API output.

The HTTP API only analyses frames captured by the server camera, so this script runs
the same analysis service the camera endpoints use on local files.

Run from back_raspberry/: uv run --frozen python -m scripts.evaluate_images path.png ...
"""

import argparse
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from fastapi import UploadFile

from app.engine.models import Calibration
from app.engine.lens import source_outline, distort_points
from app.schemas import AnalysisOptions
from app.services.analysis import analyze
from app.services.images import read_image, correct_lens


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--config", type=Path, help="AnalysisOptions JSON, including optional manual calibration/settings")
    parser.add_argument("--output", type=Path, default=Path("evaluation-output"))
    args = parser.parse_args()
    options = AnalysisOptions.model_validate_json(args.config.read_text()) if args.config else AnalysisOptions()
    args.output.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(args.images, 1):
        original = read_image(UploadFile(file=io.BytesIO(path.read_bytes())))
        result = analyze(original, options, "upload", datetime.now(timezone.utc)).model_dump(mode="json")
        prefix = args.output / f"{index}-{path.stem}"
        prefix.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
        image = correct_lens(original, options.lens)
        height, width = image.shape[:2]
        calibration = Calibration.model_validate(result['calibration']) if result['calibration'] else None
        corrected = correct_lens(image, calibration.lens).copy() if calibration else image.copy()
        if calibration and calibration.lens:
            cv2.imwrite(str(prefix) + '-corrected.jpg', corrected)
            # A reproducible before/after QA artifact. Pixel outputs stay
            # in this offline script, outside the numerical API runtime.
            left, right = image.copy(), corrected.copy()
            for panel, text in [(left, 'Original'), (right, 'Automatic lens correction')]:
                cv2.putText(panel, text, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)
            comparison = cv2.resize(np.hstack([left, right]), (1920, round(height * 960 / width)))
            cv2.imwrite(str(prefix) + '-comparison.jpg', comparison)
        if result["calibration"]:
            points = np.float32([[p.x * (width - 1), p.y * (height - 1)] for p in calibration.corners])
            cv2.polylines(image, [np.int32(source_outline(points, calibration.lens))], True, (0, 255, 255), 2)
            target = np.float32([[0, 0], [999, 0], [999, 499], [0, 499]])
            target[:, 1] *= 2 / result['settings']['table_ratio']
            rectified = cv2.warpPerspective(corrected, cv2.getPerspectiveTransform(points, target),
                                            (1000, round(1000 / result['settings']['table_ratio'])))
            cv2.imwrite(str(prefix) + '-table.jpg', rectified)
        detection = result["detection"]
        for ball in detection["balls"] if detection else []:
            native = distort_points([[ball["source_x"] * (width - 1), ball["source_y"] * (height - 1)]], calibration.lens)[0]
            center = tuple(np.rint(native).astype(int))
            cv2.circle(image, center, 20, (0, 0, 255), 2)
            cv2.putText(image, f"{ball['id']} {ball['kind']}", (center[0] + 20, center[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 255), 1, cv2.LINE_AA)
        cv2.imwrite(str(prefix.with_suffix(".jpg")), image)
        print(json.dumps({"input": str(path), "status": result["table_status"],
                          "counts": detection["counts"] if detection else None,
                          "analysis_ms": result["analysis_ms"], "output": str(prefix)}))


if __name__ == "__main__":
    main()
