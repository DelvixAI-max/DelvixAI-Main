"""Read the broadcast's on-screen game clock, once per second, for an entire
quarter video. This is the raw signal `clock_sync.py` turns into a lookup
table.

EasyOCR is used by default (better than Tesseract on clean broadcast-graphic
digits). It's imported lazily so importing this module doesn't require the
(large) easyocr/torch install unless you actually call `read_clock_track`.
"""

from __future__ import annotations

import cv2

from common.time_utils import parse_clock_string
from stage0_ingestion.clock_sync import ClockSample

CropBox = tuple[int, int, int, int]  # x, y, w, h


_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr

        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def _crop(frame, box: CropBox):
    x, y, w, h = box
    return frame[y : y + h, x : x + w]


def _preprocess_for_ocr(cropped_frame):
    gray = cv2.cvtColor(cropped_frame, cv2.COLOR_BGR2GRAY)
    # Broadcast clock graphics are usually high-contrast; a fixed threshold
    # cleans up compression artifacts before OCR.
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    return thresh


def read_clock_track(video_path: str, crop_box: CropBox, sample_every_seconds: float = 1.0) -> list[ClockSample]:
    """Sample the on-screen clock once every `sample_every_seconds` and OCR
    it, returning one ClockSample per sample point (broadcast_second is the
    position in *this* video file, not the game clock)."""
    reader = _get_reader()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps else 0.0

    samples: list[ClockSample] = []
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok:
            break

        cropped = _crop(frame, crop_box)
        processed = _preprocess_for_ocr(cropped)
        results = reader.readtext(processed, detail=0, allowlist="0123456789:")

        parsed = None
        for text in results:
            parsed = parse_clock_string(text.replace(" ", ""))
            if parsed is not None:
                break

        samples.append(ClockSample(broadcast_second=int(round(t)), game_clock_seconds=parsed))
        t += sample_every_seconds

    cap.release()
    return samples
