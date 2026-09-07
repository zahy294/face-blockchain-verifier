"""Face processing module using Google MediaPipe (BlazeFace) and OpenCV Headless.

This module provides face detection, dominant face selection, margin-expanded cropping,
blur scoring via Laplacian variance, SHA-256 hashing, and temporary file management
without any GUI dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Tuple

import cv2
import mediapipe as mp
import numpy as np


class FaceProcessingError(Exception):
    """Base exception for all face processing errors."""


class NoFaceDetectedError(FaceProcessingError):
    """Raised when no face is detected in the provided image."""


class MultipleFacesDetectedError(FaceProcessingError):
    """Raised when multiple faces are detected and strict single face mode is enabled."""


@dataclass(frozen=True)
class FaceCropResult:
    """Immutable result container for face detection and cropping operations.

    Attributes:
        temp_file_path: Path to the safe temporary JPEG file containing the cropped face.
        sha256_hash: Direct SHA-256 hex digest of the raw JPEG crop bytes.
        original_dimensions: Dimensions of the source image as (height, width).
        crop_box: Bounding box coordinates of the crop as (x1, y1, x2, y2).
        detection_confidence: Confidence score of the face detection (0.0 to 1.0).
        blur_score: Variance of the Laplacian score evaluating crop sharpness.
    """

    temp_file_path: str
    sha256_hash: str
    original_dimensions: Tuple[int, int]
    crop_box: Tuple[int, int, int, int]
    detection_confidence: float
    blur_score: float

    @property
    def crop_path(self) -> str:
        """Alias for temp_file_path."""
        return self.temp_file_path

    @property
    def bounding_box(self) -> Tuple[int, int, int, int]:
        """Alias for crop_box."""
        return self.crop_box


class FaceProcessor:
    """BlazeFace-powered face processor for bounding box extraction and validation."""

    def __init__(
        self,
        min_detection_confidence: float = 0.65,
        margin: float = 0.18,
        model_selection: int = 0,
    ) -> None:
        """Initialize the FaceProcessor.

        Args:
            min_detection_confidence: Minimum detection confidence threshold (default 0.65).
            margin: Fractional margin to expand bounding box around the face (default 0.18 for 18%).
            model_selection: MediaPipe model selection (0 for short-range faces within 2 meters,
                1 for full-range faces). Default is 0.
        """
        if not 0.0 <= min_detection_confidence <= 1.0:
            raise ValueError("min_detection_confidence must be between 0.0 and 1.0.")
        if margin < 0.0:
            raise ValueError("margin must be non-negative.")

        self.min_detection_confidence = min_detection_confidence
        self.margin = margin
        self.model_selection = model_selection

        self._mp_face_detection = mp.solutions.face_detection
        self._detector: mp.solutions.face_detection.FaceDetection | None = (
            self._mp_face_detection.FaceDetection(
                min_detection_confidence=self.min_detection_confidence,
                model_selection=self.model_selection,
            )
        )

    def __enter__(self) -> FaceProcessor:
        """Context manager entry point."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit point to ensure cleanup."""
        self.close()

    def close(self) -> None:
        """Release underlying MediaPipe detector resources."""
        if self._detector is not None:
            self._detector.close()
            self._detector = None

    def process(
        self,
        image_path: str | Path,
        strict_single_face: bool = False,
        quality_check: bool = True,
    ) -> FaceCropResult:
        """Process an image file to detect, crop, hash, and assess face quality.

        Args:
            image_path: Path to the target image file.
            strict_single_face: If True, raises MultipleFacesDetectedError when >1 face is found.
                If False, selects dominant face based on bounding box area.
            quality_check: Whether to compute image quality metrics (e.g. Laplacian blur score).

        Returns:
            FaceCropResult containing file paths, hashes, coordinates, and metrics.

        Raises:
            FileNotFoundError: If the input file does not exist.
            FaceProcessingError: If image reading, decoding, or encoding fails.
            NoFaceDetectedError: If no face is detected in the image.
            MultipleFacesDetectedError: If multiple faces are detected and strict_single_face is True.
        """
        if self._detector is None:
            raise FaceProcessingError("FaceProcessor has been closed and cannot process images.")

        path_obj = Path(image_path).resolve()
        if not path_obj.is_file():
            raise FileNotFoundError(f"Input image not found: {path_obj}")

        # Read image with OpenCV Headless (BGR format)
        image = cv2.imread(str(path_obj))
        if image is None:
            raise FaceProcessingError(f"Failed to read/decode image from {path_obj}")

        img_height, img_width = image.shape[:2]
        if img_height == 0 or img_width == 0:
            raise FaceProcessingError(f"Image has invalid dimensions ({img_width}x{img_height})")

        # MediaPipe requires RGB format
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        detection_results = self._detector.process(rgb_image)

        if not detection_results or not detection_results.detections:
            raise NoFaceDetectedError(f"No face detected in image: {path_obj}")

        detections = detection_results.detections
        num_faces = len(detections)

        if num_faces > 1 and strict_single_face:
            raise MultipleFacesDetectedError(
                f"Detected {num_faces} faces in image, but strict_single_face is enabled."
            )

        # Select dominant face based on bounding box area
        if num_faces == 1:
            dominant_detection = detections[0]
        else:
            dominant_detection = max(
                detections,
                key=lambda d: (
                    d.location_data.relative_bounding_box.width
                    * d.location_data.relative_bounding_box.height
                ),
            )

        # Extract normalized coordinates
        rel_box = dominant_detection.location_data.relative_bounding_box
        abs_xmin = int(rel_box.xmin * img_width)
        abs_ymin = int(rel_box.ymin * img_height)
        abs_width = int(rel_box.width * img_width)
        abs_height = int(rel_box.height * img_height)

        # Apply configurable bounding box margin (default 18%)
        margin_x = int(abs_width * self.margin)
        margin_y = int(abs_height * self.margin)

        # Clamp bounding box cleanly within original image boundaries
        x1 = max(0, abs_xmin - margin_x)
        y1 = max(0, abs_ymin - margin_y)
        x2 = min(img_width, abs_xmin + abs_width + margin_x)
        y2 = min(img_height, abs_ymin + abs_height + margin_y)

        if x2 <= x1 or y2 <= y1:
            raise FaceProcessingError(
                f"Invalid crop coordinates calculated: ({x1}, {y1}, {x2}, {y2})"
            )

        # Crop face from original image (BGR)
        cropped_bgr = image[y1:y2, x1:x2]

        # Compute blur score using variance of the Laplacian
        if quality_check:
            gray_crop = cv2.cvtColor(cropped_bgr, cv2.COLOR_BGR2GRAY)
            blur_score = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())
        else:
            blur_score = 0.0

        # Encode crop directly to JPEG bytes
        encode_success, jpeg_buffer = cv2.imencode(".jpg", cropped_bgr)
        if not encode_success:
            raise FaceProcessingError("Failed to encode cropped face to JPEG format.")

        jpeg_bytes = jpeg_buffer.tobytes()

        # Compute direct SHA-256 hex digest of the raw JPEG bytes
        sha256_hash = hashlib.sha256(jpeg_bytes).hexdigest()

        # Write to safe temporary file prefixed with face_crop_ and ending in .jpg
        with tempfile.NamedTemporaryFile(
            prefix="face_crop_", suffix=".jpg", delete=False
        ) as temp_file:
            temp_file.write(jpeg_bytes)
            temp_file_path = temp_file.name

        # Extract detection confidence score
        confidence = (
            float(dominant_detection.score[0]) if dominant_detection.score else 0.0
        )

        return FaceCropResult(
            temp_file_path=temp_file_path,
            sha256_hash=sha256_hash,
            original_dimensions=(img_height, img_width),
            crop_box=(x1, y1, x2, y2),
            detection_confidence=confidence,
            blur_score=blur_score,
        )

    def detect_and_crop(self, image_path: str | Path) -> FaceCropResult:
        """Alias for process method."""
        return self.process(image_path)

    def get_face_hash(self, image_path: str | Path) -> str:
        """Process image, return SHA-256 hash, and immediately clean up temporary file."""
        result = self.process(image_path)
        if os.path.exists(result.temp_file_path):
            try:
                os.remove(result.temp_file_path)
            except OSError:
                pass
        return result.sha256_hash


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Extract, crop, hash, and analyze faces using MediaPipe BlazeFace and OpenCV."
    )
    parser.add_argument(
        "--image",
        "-i",
        type=str,
        required=True,
        help="Path to the input face image.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce strict single-face detection (fails if multiple faces detected).",
    )
    parser.add_argument(
        "--confidence",
        "-c",
        type=float,
        default=0.65,
        help="Minimum face detection confidence threshold (default: 0.65).",
    )
    parser.add_argument(
        "--margin",
        "-m",
        type=float,
        default=0.18,
        help="Bounding box expansion margin ratio (default: 0.18 for 18%%).",
    )
    parser.add_argument(
        "--no-quality-check",
        action="store_true",
        help="Skip Laplacian blur score computation.",
    )
    return parser


def main() -> None:
    """CLI entry point for face processor."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        with FaceProcessor(
            min_detection_confidence=args.confidence, margin=args.margin
        ) as processor:
            result = processor.process(
                image_path=args.image,
                strict_single_face=args.strict,
                quality_check=not args.no_quality_check,
            )

            result_dict = asdict(result)
            print(json.dumps(result_dict, indent=2))
    except FaceProcessingError as err:
        print(json.dumps({"error": err.__class__.__name__, "message": str(err)}, indent=2))
        raise SystemExit(1) from err
    except Exception as err:
        print(json.dumps({"error": "UnexpectedError", "message": str(err)}, indent=2))
        raise SystemExit(1) from err


if __name__ == "__main__":
    main()
