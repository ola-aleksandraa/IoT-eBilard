"""Offline API evaluation; annotations are local QA artifacts, never API output.

Run from backend/: uv run --frozen python -m scripts.evaluate_images path.png ...
"""

import argparse
import io
import json
from pathlib import Path

import cv2
import numpy as np
from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import AnalysisOptions
from app.services.images import read_image, correct_lens


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--config", type=Path, help="AnalysisOptions JSON, including optional manual calibration/settings")
    parser.add_argument("--output", type=Path, default=Path("evaluation-output"))
    args = parser.parse_args()
    options = AnalysisOptions.model_validate_json(args.config.read_text()) if args.config else AnalysisOptions()
    args.output.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as client:
        for index, path in enumerate(args.images, 1):
            response = client.post("/api/v1/images/detect", files={"file": (path.name, path.read_bytes())},
                                   data={"config": options.model_dump_json()})
            response.raise_for_status()
            result = response.json()
            prefix = args.output / f"{index}-{path.stem}"
            prefix.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
            # Decode/orient using the same bounded path as the API.
            image = correct_lens(read_image(UploadFile(file=io.BytesIO(path.read_bytes()))), options.lens)
            height, width = image.shape[:2]
            if result["calibration"]:
                points = np.int32([[p["x"] * (width - 1), p["y"] * (height - 1)]
                                   for p in result["calibration"]["corners"]])
                cv2.polylines(image, [points], True, (0, 255, 255), 2)
            detection = result["detection"]
            for ball in detection["balls"] if detection else []:
                center = (round(ball["source_x"] * (width - 1)), round(ball["source_y"] * (height - 1)))
                cv2.circle(image, center, 20, (0, 0, 255), 2)
                cv2.putText(image, f"{ball['id']} {ball['kind']}", (center[0] + 20, center[1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 255), 1, cv2.LINE_AA)
            cv2.imwrite(str(prefix.with_suffix(".jpg")), image)
            print(json.dumps({"input": str(path), "status": result["table_status"],
                              "counts": detection["counts"] if detection else None,
                              "analysis_ms": result["analysis_ms"], "output": str(prefix)}))


if __name__ == "__main__":
    main()
