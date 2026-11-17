"""Offline test-data authoring; never called by the backend or frontend runtime."""

from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from tests.fixtures.synthetic import make_demo

public = Path(__file__).resolve().parents[1] / "public"
public.mkdir(exist_ok=True)
assert cv2.imwrite(str(public / "sample-table.png"), make_demo()[0])
assert cv2.imwrite(str(public / "empty-table.png"), np.full((760, 1200, 3), 100, np.uint8))
