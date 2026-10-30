"""Bounded image decoding, EXIF normalization and optional lens correction."""

import io
import json
import warnings

import cv2
import numpy as np
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ValidationError

from ..engine.models import LensCalibration

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def parse_json(model: type[BaseModel], value: str):
    try:
        return model.model_validate_json(value)
    except ValidationError as exc:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise HTTPException(422, detail) from None


def validate_dimensions(width: int, height: int):
    if width * height > MAX_PIXELS or max(width, height) > 10000:
        raise HTTPException(413, "Images must be at most 16 megapixels and 10,000 pixels per side.")
    if min(width, height) < 100:
        raise HTTPException(422, "Image is too small; each side must be at least 100 pixels.")


def read_image(file: UploadFile) -> np.ndarray:
    byte_limit = MAX_UPLOAD_BYTES
    data = file.file.read(byte_limit + 1)
    if len(data) > byte_limit:
        raise HTTPException(413, f"Image exceeds the {byte_limit // 1024 // 1024} MB upload limit.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    raise HTTPException(415, "Use a JPEG, PNG, or WebP image.")
                validate_dimensions(source.width, source.height)
                image = ImageOps.exif_transpose(source).convert("RGB")
                return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(422, "The uploaded file is not a readable image.") from None
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(413, "Image exceeds the safe pixel limit.") from None


def correct_lens(image: np.ndarray, lens: LensCalibration | None) -> np.ndarray:
    height, width = image.shape[:2]
    if lens is not None:
        if (width, height) != (lens.image_width, lens.image_height):
            raise HTTPException(422, "Lens calibration resolution must match the oriented image.")
        image = cv2.undistort(image, np.float64(lens.camera_matrix), np.float64(lens.distortion))
    return image
