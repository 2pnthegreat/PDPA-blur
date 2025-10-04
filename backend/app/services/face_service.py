"""Face processing utilities."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import face_recognition
import mediapipe as mp
import numpy as np


async def compute_embedding(image_path: Path) -> List[float]:
    """Compute a 128-d face embedding using face_recognition.

    Raises:
        ValueError: When no face can be detected in the provided image.
    """

    encoding = await asyncio.to_thread(_extract_encoding, image_path)
    return encoding.tolist()


def _extract_encoding(image_path: Path) -> np.ndarray:
    image = face_recognition.load_image_file(str(image_path))
    location = _detect_face_location(image)
    encodings = face_recognition.face_encodings(image, [location], num_jitters=2)
    if not encodings:
        raise ValueError("ไม่สามารถสร้างข้อมูลใบหน้าได้จากรูปนี้")

    return encodings[0]


def _detect_face_location(image: np.ndarray) -> tuple[int, int, int, int]:
    """Detect the most prominent face using Mediapipe and return it in FR format."""

    mp_face = mp.solutions.face_detection
    with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.6) as detector:
        results = detector.process(image)

    detections = getattr(results, "detections", None) or []
    if not detections:
        raise ValueError("ไม่พบใบหน้าในรูปที่อัปโหลด กรุณาลองรูปอื่น")

    def _area(det: mp.framework.formats.detection_pb2.Detection) -> float:
        box = det.location_data.relative_bounding_box
        return max(box.width, 0.0) * max(box.height, 0.0)

    target = max(detections, key=_area)
    return _mediapipe_detection_to_face_location(image, target)


def _mediapipe_detection_to_face_location(
    image: np.ndarray, detection: mp.framework.formats.detection_pb2.Detection
) -> tuple[int, int, int, int]:
    height, width, _ = image.shape
    relative_box = detection.location_data.relative_bounding_box

    padding_ratio = 0.08
    xmin = relative_box.xmin
    ymin = relative_box.ymin
    box_width = relative_box.width
    box_height = relative_box.height

    pad_w = box_width * padding_ratio
    pad_h = box_height * padding_ratio

    left = max(0, int((xmin - pad_w) * width))
    top = max(0, int((ymin - pad_h) * height))
    right = min(width, int((xmin + box_width + pad_w) * width))
    bottom = min(height, int((ymin + box_height + pad_h) * height))

    if right <= left or bottom <= top:
        raise ValueError("ไม่พบใบหน้าที่สามารถใช้งานได้ในรูปนี้")

    return top, right, bottom, left
