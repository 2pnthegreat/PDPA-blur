"""Background video processing services using face_recognition embeddings."""
from __future__ import annotations

import logging
import math
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Optional, Tuple

import cv2
import face_recognition
import mediapipe as mp
import numpy as np

from ..core.config import get_settings
from ..core.jobs import JobState, job_store
from ..face import FaceProfile, face_registry
from ..schemas.video import BlurMode, VideoBlurRequest
from ..utils.cleanup import prune_expired_files, schedule_file_expiration

logger = logging.getLogger(__name__)


@dataclass
class ModeConfig:
    detection_model: str
    upsample: int
    num_jitters: int
    match_threshold: float
    demotion_margin: float
    promote_hits: int
    demote_misses: int
    track_ttl: int
    track_match_threshold: float
    blur_expand: float
    detection_stride: int
    resize_width: Optional[int]
    detector_model_selection: int
    detector_confidence: float
    min_confidence_gap: float
    embedding_smooth_alpha: float
    require_reference_match: bool


@dataclass
class Track:
    bbox: Tuple[int, int, int, int]
    label: str
    ttl: int
    distance: float
    user_hits: int = 0
    user_misses: int = 0
    running_embedding: Optional[np.ndarray] = None


def enqueue_blur_job(request: VideoBlurRequest) -> None:
    thread = threading.Thread(target=_process_job, args=(request,), daemon=True)
    thread.start()


def _mode_config(mode: BlurMode) -> ModeConfig:
    if mode == BlurMode.DETAILED:
        return ModeConfig(
            detection_model="hog",
            upsample=1,
            num_jitters=1,
            match_threshold=0.48,
            demotion_margin=0.08,
            promote_hits=2,
            demote_misses=2,
            track_ttl=22,
            track_match_threshold=0.30,
            blur_expand=0.16,
            detection_stride=1,
            resize_width=720,
            detector_model_selection=1,
            detector_confidence=0.55,
            min_confidence_gap=0.15,
            embedding_smooth_alpha=0.60,
            require_reference_match=False,
        )
    return ModeConfig(
        detection_model="hog",
        upsample=0,
        num_jitters=0,
        match_threshold=0.40,
        demotion_margin=0.06,
        promote_hits=3,
        demote_misses=2,
        track_ttl=14,
        track_match_threshold=0.22,
        blur_expand=0.16,
        detection_stride=2,
        resize_width=640,
        detector_model_selection=0,
        detector_confidence=0.5,
        min_confidence_gap=0.30,
        embedding_smooth_alpha=0.45,
        require_reference_match=True,
    )

def _process_job(request: VideoBlurRequest) -> None:
    job_id = request.job_id
    config = _mode_config(request.mode)
    try:
        start_time = time.perf_counter()
        logger.info(
            "Job %s started (mode=%s, blur=%d)", job_id, request.mode, request.blur_level
        )
        settings = get_settings()
        prune_expired_files(settings.reference_faces_dir, 300, "reference image")
        prune_expired_files(settings.uploads_dir, 300, "uploaded video")
        prune_expired_files(settings.processed_dir, 300, "processed video")
        job_store.update(job_id, message="Preparing face data", progress=2.0)

        profile = face_registry.get(request.user_id)
        if profile is None or not profile.embeddings:
            raise ValueError("Reference face not found for user")

        reference_matrix = _prepare_reference_embeddings(profile)
        logger.info(
            "Job %s using %d reference images (mode=%s, blur=%d)",
            job_id,
            len(profile.image_paths),
            request.mode,
            request.blur_level,
        )

        job_store.update(job_id, message="Processing video", progress=5.0)
        process_start = time.perf_counter()
        output_path = _blur_video_frames(request, reference_matrix, config)
        process_elapsed = time.perf_counter() - process_start
        logger.info("Job %s video processing took %.2f seconds", job_id, process_elapsed)

        elapsed = time.perf_counter() - start_time
        logger.info("Job %s finished in %.2f seconds", job_id, elapsed)
        job_store.update(
            job_id,
            progress=100.0,
            state=JobState.COMPLETED,
            message="Processing finished",
            result_path=str(output_path),
        )
    except Exception as exc:  # pragma: no cover - placeholder error handling
        logger.exception("Job %s failed", job_id)
        job_store.update(job_id, state=JobState.FAILED, message=str(exc))


def _prepare_reference_embeddings(profile: FaceProfile) -> np.ndarray:
    encodings = np.array(profile.embeddings, dtype=np.float32)
    if encodings.ndim == 1:
        encodings = encodings.reshape(1, -1)
    if encodings.size == 0:
        raise ValueError("No valid reference embeddings available")
    return encodings


def _blur_video_frames(
    request: VideoBlurRequest,
    reference_matrix: np.ndarray,
    config: ModeConfig,
) -> Path:
    job_id = request.job_id
    video_path = Path(request.video_path)
    settings = get_settings()
    settings.processed_dir.mkdir(parents=True, exist_ok=True)

    suffix = video_path.suffix or ".mp4"
    output_name = f"{video_path.stem}_{request.mode}_{job_id[:8]}{suffix}"
    final_output = settings.processed_dir / output_name

    with NamedTemporaryFile(suffix=".mp4", delete=False, dir=settings.processed_dir) as temp_file:
        temp_video_path = Path(temp_file.name)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError("Cannot open uploaded video")

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

    writer = cv2.VideoWriter(
        str(temp_video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise ValueError("Cannot initialise video writer")

    processed_frames = 0
    faces_preserved = 0
    faces_blurred = 0
    tracked_faces: List[Track] = []

    mp_face = mp.solutions.face_detection
    with mp_face.FaceDetection(
        model_selection=config.detector_model_selection,
        min_detection_confidence=config.detector_confidence,
    ) as detector:
        try:
            while True:
                success, frame = capture.read()
                if not success:
                    break

                detection_frame = processed_frames % config.detection_stride == 0
                preserved, blurred = _process_frame(
                    frame,
                    reference_matrix,
                    request.blur_level,
                    config,
                    tracked_faces,
                    detection_frame,
                    detector,
                )
                faces_preserved += preserved
                faces_blurred += blurred
                processed_frames += 1
                writer.write(frame)

                if frame_count:
                    progress = 5.0 + (processed_frames / frame_count) * 85.0
                    job_store.update(request.job_id, progress=min(progress, 95.0))
        finally:
            capture.release()
            writer.release()

    logger.info(
        "Job %s processed %d frames at %.2f FPS (%s mode). preserved=%d blurred=%d",
        request.job_id,
        processed_frames,
        fps,
        request.mode,
        faces_preserved,
        faces_blurred,
    )

    _mux_audio_with_ffmpeg(temp_video_path, video_path, final_output)
    temp_video_path.unlink(missing_ok=True)
    schedule_file_expiration(final_output, 300, f"processed video for job {request.job_id}")
    return final_output


def _process_frame(
    frame: np.ndarray,
    reference_matrix: np.ndarray,
    blur_level: int,
    config: ModeConfig,
    tracked_faces: List[Track],
    detection_frame: bool,
    detector: mp.solutions.face_detection.FaceDetection,
) -> Tuple[int, int]:
    if detection_frame:
        preserved, blurred = _detect_and_update(
            frame, reference_matrix, blur_level, config, tracked_faces, detector
        )
    else:
        preserved, blurred = _blur_existing_tracks(frame, blur_level, config, tracked_faces)
        for track in tracked_faces:
            track.ttl = max(1, track.ttl - 1)
    return preserved, blurred


def _detect_and_update(
    frame: np.ndarray,
    reference_matrix: np.ndarray,
    blur_level: int,
    config: ModeConfig,
    tracked_faces: List[Track],
    detector: mp.solutions.face_detection.FaceDetection,
) -> Tuple[int, int]:
    rgb_frame = frame[:, :, ::-1].copy()
    detection_frame, scale_ratio = _prepare_detection_frame(rgb_frame, config)

    detections = detector.process(detection_frame)
    if not detections.detections:
        return _decay_tracks(frame, blur_level, config, tracked_faces)

    preserved = 0
    blurred = 0
    frame_height, frame_width = frame.shape[:2]
    existing_tracks = list(tracked_faces)
    tracked_faces.clear()
    matched_indices: set[int] = set()

    for detection in detections.detections:
        bbox = _mediapipe_bbox_to_tuple(detection_frame.shape, detection)
        original_bbox = _convert_location(bbox, scale_ratio)
        original_bbox = _normalize_bbox(original_bbox, frame_width, frame_height)

        encoding = _compute_embedding(rgb_frame, original_bbox, config)
        distance = float("inf")
        distance_gap = float("inf")
        distance_ok = False
        strong_miss = True
        classification_confident = False
        reference_ok = False
        confidence_window_ok = False
        running_ok = False
        if encoding is not None:
            diff = reference_matrix - encoding
            squared = np.sum(diff * diff, axis=1)
            sorted_sq = np.sort(squared)
            if sorted_sq.size:
                distance = float(np.sqrt(sorted_sq[0]))
                if sorted_sq.size > 1:
                    second_distance = float(np.sqrt(sorted_sq[1]))
                    distance_gap = max(0.0, second_distance - distance)
                else:
                    distance_gap = float("inf")
                classification_confident = distance_gap >= config.min_confidence_gap
                reference_ok = distance <= config.match_threshold
                confidence_window_ok = (
                    classification_confident
                    and distance <= (config.match_threshold + config.demotion_margin * 0.25)
                )
                distance_ok = reference_ok
                strong_miss = distance > (
                    config.match_threshold + config.demotion_margin * 0.6
                )

        match_idx = _find_best_track(existing_tracks, original_bbox, config.track_match_threshold)
        running_distance = float("inf")
        if match_idx is not None:
            track = existing_tracks[match_idx]
            matched_indices.add(match_idx)
            blended_bbox = _blend_bbox(track.bbox, original_bbox)
            track.bbox = _normalize_bbox(blended_bbox, frame_width, frame_height)
            track.ttl = config.track_ttl

            if encoding is not None:
                if track.running_embedding is not None:
                    running_distance = float(
                        np.linalg.norm(track.running_embedding - encoding)
                    )
                alpha = config.embedding_smooth_alpha
                if track.running_embedding is None:
                    track.running_embedding = encoding.copy()
                else:
                    track.running_embedding = (
                        track.running_embedding * alpha
                        + encoding * (1 - alpha)
                    )
                running_factor = 0.8 if config.require_reference_match else 0.9
                running_ok = math.isfinite(running_distance) and running_distance <= (
                    config.match_threshold * running_factor
                )
            else:
                running_ok = False

            running_ready = track.running_embedding is not None
            if config.require_reference_match:
                distance_ok = reference_ok and (not running_ready or running_ok)
                strong_miss = not distance_ok and (
                    not reference_ok or (running_ready and not running_ok)
                )
            else:
                if reference_ok:
                    distance_ok = True
                    strong_miss = False
                elif confidence_window_ok and running_ok:
                    distance_ok = True
                    strong_miss = False
                else:
                    distance_ok = False
                    if not running_ok and not reference_ok:
                        strong_miss = True

            track.distance = _blend_distance(track.distance, distance)

            if distance_ok:
                track.user_hits = min(track.user_hits + 1, config.promote_hits)
                track.user_misses = max(0, track.user_misses - 1)
            else:
                track.user_hits = 0
                if strong_miss:
                    track.user_misses = min(track.user_misses + 1, config.demote_misses)
        else:
            if config.require_reference_match:
                final_user = reference_ok
            else:
                final_user = reference_ok or confidence_window_ok
            distance_ok = final_user
            running_distance = 0.0 if final_user and encoding is not None else float("inf")
            running_ok = final_user
            track = Track(
                bbox=original_bbox,
                label='user' if final_user else 'other',
                ttl=config.track_ttl,
                distance=distance,
                user_hits=1 if final_user else 0,
                user_misses=0 if final_user else (1 if strong_miss else 0),
                running_embedding=encoding.copy() if encoding is not None else None,
            )

        if strong_miss and track.label == 'user' and track.user_misses >= config.demote_misses:
            track.label = 'other'

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "face dist=%.3f gap=%.3f run=%.3f ref_ok=%s run_ok=%s label=%s hits=%d misses=%d matched=%s strong_miss=%s",
                distance,
                distance_gap,
                running_distance,
                reference_ok,
                running_ok,
                track.label,
                track.user_hits,
                track.user_misses,
                match_idx is not None,
                strong_miss,
            )

        if track.label == 'user':
            preserved += 1
        else:
            if _apply_blur(frame, track.bbox, blur_level, config):
                blurred += 1
        tracked_faces.append(track)

    for idx, track in enumerate(existing_tracks):
        if idx in matched_indices:
            continue
        track.ttl = max(0, track.ttl - 1)
        if track.ttl <= 0:
            continue
        track.bbox = _normalize_bbox(track.bbox, frame_width, frame_height)
        track.user_hits = 0
        track.user_misses = min(track.user_misses + 1, config.demote_misses)
        if track.label == 'user' and track.user_misses >= config.demote_misses:
            track.label = 'other'
        if track.label == 'user':
            preserved += 1
        else:
            if _apply_blur(frame, track.bbox, blur_level, config):
                blurred += 1
        tracked_faces.append(track)

    return preserved, blurred


def _blur_existing_tracks(
    frame: np.ndarray,
    blur_level: int,
    config: ModeConfig,
    tracked_faces: List[Track],
) -> Tuple[int, int]:
    preserved = 0
    blurred = 0
    frame_height, frame_width = frame.shape[:2]
    for track in list(tracked_faces):
        track.ttl -= 1
        track.bbox = _normalize_bbox(track.bbox, frame_width, frame_height)
        if track.ttl <= 0:
            tracked_faces.remove(track)
            continue

        if track.label == "user":
            preserved += 1
        else:
            if _apply_blur(frame, track.bbox, blur_level, config):
                blurred += 1
    return preserved, blurred


def _apply_blur(
    frame: np.ndarray,
    bbox: Tuple[int, int, int, int],
    blur_level: int,
    config: ModeConfig,
) -> bool:
    x, y, w, h = bbox
    expand_ratio = _dynamic_blur_expand(blur_level, config)
    blur_box = _expanded_box(bbox, frame.shape[1], frame.shape[0], expand_ratio)
    x1, y1, x2, y2 = blur_box
    if x1 >= x2 or y1 >= y2:
        return False

    passes = _blur_pass_count(blur_level)
    kernel_size = _kernel_size_for_region(x2 - x1, y2 - y1, blur_level, passes)
    region = frame[y1:y2, x1:x2]
    if not region.size:
        return False
    blurred_region = region.copy()
    for _ in range(passes):
        blurred_region = cv2.GaussianBlur(blurred_region, (kernel_size, kernel_size), 0)

    mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
    center = (mask.shape[1] // 2, mask.shape[0] // 2)
    axes = (max(1, (x2 - x1) // 2), max(1, (y2 - y1) // 2))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
    mask_3c = cv2.merge([mask, mask, mask])

    np.putmask(region, mask_3c == 255, blurred_region)
    return True


def _decay_tracks(
    frame: np.ndarray,
    blur_level: int,
    config: ModeConfig,
    tracked_faces: List[Track],
) -> Tuple[int, int]:
    preserved = 0
    blurred = 0
    frame_height, frame_width = frame.shape[:2]
    for track in list(tracked_faces):
        track.ttl -= 1
        track.bbox = _normalize_bbox(track.bbox, frame_width, frame_height)
        track.user_hits = 0
        track.user_misses = min(track.user_misses + 1, config.demote_misses)
        if track.label == "user" and track.user_misses >= config.demote_misses:
            track.label = "other"
        if track.label == "user":
            preserved += 1
        else:
            if _apply_blur(frame, track.bbox, blur_level, config):
                blurred += 1
        if track.ttl <= 0:
            tracked_faces.remove(track)
    return preserved, blurred


def _prepare_detection_frame(
    rgb_frame: np.ndarray,
    config: ModeConfig,
) -> Tuple[np.ndarray, float]:
    scale_ratio = 1.0
    if config.resize_width and rgb_frame.shape[1] > config.resize_width:
        scale_ratio = config.resize_width / rgb_frame.shape[1]
        resized = cv2.resize(
            rgb_frame,
            (int(rgb_frame.shape[1] * scale_ratio), int(rgb_frame.shape[0] * scale_ratio)),
            interpolation=cv2.INTER_AREA,
        )
        return resized, scale_ratio
    return rgb_frame, scale_ratio


def _convert_location(location: Tuple[int, int, int, int], scale_ratio: float) -> Tuple[int, int, int, int]:
    top, right, bottom, left = location
    inv = 1.0 / scale_ratio if scale_ratio != 0 else 1.0
    x = int(left * inv)
    y = int(top * inv)
    w = int((right - left) * inv)
    h = int((bottom - top) * inv)
    return max(0, x), max(0, y), max(1, w), max(1, h)


def _blend_bbox(
    box_a: Tuple[int, int, int, int],
    box_b: Tuple[int, int, int, int],
) -> Tuple[int, int, int, int]:
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b
    blended = (
        int((ax + bx) / 2),
        int((ay + by) / 2),
        int((aw + bw) / 2),
        int((ah + bh) / 2),
    )
    return blended




def _blur_pass_count(blur_level: int) -> int:
    return 1 + max(0, (blur_level - 5) // 2)


def _dynamic_blur_expand(blur_level: int, config: ModeConfig) -> float:
    extra = max(0, blur_level - 1) * 0.01
    return min(0.35, config.blur_expand + extra)


def _normalize_bbox(
    bbox: Tuple[int, int, int, int], frame_width: int, frame_height: int
) -> Tuple[int, int, int, int]:
    x, y, w, h = bbox
    frame_width = max(1, frame_width)
    frame_height = max(1, frame_height)
    x = int(max(0, min(frame_width - 1, x)))
    y = int(max(0, min(frame_height - 1, y)))
    w = int(max(1, min(w, frame_width - x)))
    h = int(max(1, min(h, frame_height - y)))
    return x, y, w, h


def _find_best_track(
    tracks: List[Track], bbox: Tuple[int, int, int, int], threshold: float
) -> Optional[int]:
    best_idx: Optional[int] = None
    best_score = threshold
    for idx, track in enumerate(tracks):
        score = _iou(track.bbox, bbox)
        if score >= best_score:
            best_idx = idx
            best_score = score
    return best_idx


def _blend_distance(current: float, new: float) -> float:
    if not math.isfinite(new):
        return current
    if not math.isfinite(current):
        return new
    return (current * 0.6) + (new * 0.4)


def _kernel_size_for_region(
    width: int,
    height: int,
    blur_level: int,
    passes: int,
) -> int:
    passes = max(1, passes)
    base = max(width, height)
    base_strength = 0.18 + (blur_level / 12.0)
    kernel = base_strength * base
    if passes > 1:
        kernel *= 1 + 0.25 * (passes - 1)
    kernel = int(max(9, min(kernel, 151)))
    if kernel % 2 == 0:
        kernel += 1
    return kernel

def _expanded_box(
    bbox: Tuple[int, int, int, int],
    frame_width: int,
    frame_height: int,
    expand_ratio: float,
) -> Tuple[int, int, int, int]:
    x, y, w, h = bbox
    x1 = max(0, int(x - w * expand_ratio))
    y1 = max(0, int(y - h * expand_ratio))
    x2 = min(frame_width, int(x + w * (1 + expand_ratio)))
    y2 = min(frame_height, int(y + h * (1 + expand_ratio)))
    return x1, y1, x2, y2


def _iou(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b

    inter_x1 = max(ax, bx)
    inter_y1 = max(ay, by)
    inter_x2 = min(ax + aw, bx + bw)
    inter_y2 = min(ay + ah, by + bh)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = aw * ah
    area_b = bw * bh
    union_area = max(area_a + area_b - inter_area, 1)
    return inter_area / union_area


def _mediapipe_bbox_to_tuple(
    shape: Tuple[int, int, int], detection: mp.framework.formats.detection_pb2.Detection
) -> Tuple[int, int, int, int]:
    h, w, _ = shape
    relative_box = detection.location_data.relative_bounding_box
    left = max(0, int(relative_box.xmin * w))
    top = max(0, int(relative_box.ymin * h))
    width = int(relative_box.width * w)
    height = int(relative_box.height * h)
    right = left + width
    bottom = top + height
    return top, right, bottom, left


def _compute_embedding(
    frame_rgb: np.ndarray,
    bbox_xywh: Tuple[int, int, int, int],
    config: ModeConfig,
) -> Optional[np.ndarray]:
    x, y, w, h = bbox_xywh
    top = max(0, y)
    left = max(0, x)
    bottom = min(frame_rgb.shape[0], y + h)
    right = min(frame_rgb.shape[1], x + w)
    if bottom <= top or right <= left:
        return None

    face_location = [(top, right, bottom, left)]
    encodings = face_recognition.face_encodings(
        frame_rgb,
        face_location,
        num_jitters=config.num_jitters,
    )
    if not encodings:
        return None
    return encodings[0]


def _mux_audio_with_ffmpeg(temp_video: Path, original_video: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(temp_video),
        "-i",
        str(original_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "copy",
        str(output_path),
    ]

    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {process.stderr.strip()}")
