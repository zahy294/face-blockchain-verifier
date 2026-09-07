"""Unit tests for FaceProcessor module."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

import cv2
import numpy as np

from src.face_processor import (
    FaceCropResult,
    FaceProcessingError,
    FaceProcessor,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
)


class TestFaceProcessor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_dir = Path(cls.temp_dir.name)

        # 1. Blank image (no face)
        cls.blank_image_path = cls.test_dir / "blank_image.jpg"
        blank = np.zeros((300, 400, 3), dtype=np.uint8)
        cv2.imwrite(str(cls.blank_image_path), blank)

        # 2. Corrupt / invalid file
        cls.corrupt_path = cls.test_dir / "corrupt.jpg"
        with open(cls.corrupt_path, "wb") as f:
            f.write(b"not a real jpeg image file")

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_dataclass_properties(self):
        """Test FaceCropResult immutability and attributes."""
        res = FaceCropResult(
            temp_file_path="face_crop_123.jpg",
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            original_dimensions=(400, 600),
            crop_box=(50, 40, 250, 240),
            detection_confidence=0.92,
            blur_score=145.2,
        )
        self.assertEqual(res.temp_file_path, "face_crop_123.jpg")
        self.assertEqual(res.sha256_hash, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        self.assertEqual(res.original_dimensions, (400, 600))
        self.assertEqual(res.crop_box, (50, 40, 250, 240))
        self.assertEqual(res.detection_confidence, 0.92)
        self.assertEqual(res.blur_score, 145.2)

        with self.assertRaises(Exception):
            # Should be frozen dataclass
            res.blur_score = 50.0  # type: ignore

    def test_file_not_found(self):
        """Test non-existent file handling."""
        with FaceProcessor() as processor:
            with self.assertRaises(FileNotFoundError):
                processor.process("non_existent_image_99999.jpg")

    def test_corrupt_image(self):
        """Test corrupted image handling."""
        with FaceProcessor() as processor:
            with self.assertRaises(FaceProcessingError):
                processor.process(self.corrupt_path)

    def test_no_face_detected_error(self):
        """Test NoFaceDetectedError when image has no face."""
        with FaceProcessor(min_detection_confidence=0.5) as processor:
            with self.assertRaises(NoFaceDetectedError):
                processor.process(self.blank_image_path)

    def test_context_manager_and_close(self):
        """Test context manager lifecycle and close cleanup."""
        processor = FaceProcessor()
        self.assertIsNotNone(processor._detector)
        processor.close()
        self.assertIsNone(processor._detector)

        with self.assertRaises(FaceProcessingError):
            processor.process(self.blank_image_path)

    def _create_mock_detection(self, xmin: float, ymin: float, width: float, height: float, score: float = 0.95):
        """Helper to create a mock MediaPipe Detection object."""
        mock_det = MagicMock()
        mock_bbox = MagicMock()
        mock_bbox.xmin = xmin
        mock_bbox.ymin = ymin
        mock_bbox.width = width
        mock_bbox.height = height
        mock_det.location_data.relative_bounding_box = mock_bbox
        mock_det.score = [score]
        return mock_det

    def test_single_face_detection_and_crop(self):
        """Test single face detection, margin expansion, JPEG hash, and blur score."""
        with FaceProcessor(margin=0.18) as processor:
            # Mock detector
            mock_detection = self._create_mock_detection(0.2, 0.2, 0.4, 0.4, score=0.88)
            mock_results = MagicMock()
            mock_results.detections = [mock_detection]
            processor._detector.process = MagicMock(return_value=mock_results)

            result = processor.process(self.blank_image_path, quality_check=True)

            self.assertIsInstance(result, FaceCropResult)
            self.assertTrue(os.path.exists(result.temp_file_path))
            self.assertTrue(Path(result.temp_file_path).name.startswith("face_crop_"))
            self.assertTrue(result.temp_file_path.endswith(".jpg"))

            # Check original dimensions (blank image is 300x400)
            self.assertEqual(result.original_dimensions, (300, 400))
            self.assertAlmostEqual(result.detection_confidence, 0.88)

            # Check crop box:
            # img_w = 400, img_h = 300
            # abs_xmin = 80, abs_ymin = 60, abs_w = 160, abs_h = 120
            # margin_x = int(160 * 0.18) = 28
            # margin_y = int(120 * 0.18) = 21
            # x1 = max(0, 80 - 28) = 52
            # y1 = max(0, 60 - 21) = 39
            # x2 = min(400, 80 + 160 + 28) = 268
            # y2 = min(300, 60 + 120 + 21) = 201
            self.assertEqual(result.crop_box, (52, 39, 268, 201))

            # Verify SHA-256 match
            with open(result.temp_file_path, "rb") as f:
                content = f.read()
            expected_hash = hashlib.sha256(content).hexdigest()
            self.assertEqual(result.sha256_hash, expected_hash)

            # Cleanup
            if os.path.exists(result.temp_file_path):
                os.remove(result.temp_file_path)

    def test_dominant_face_selection_multiple_faces(self):
        """Test dominant face selection when multiple faces are detected."""
        with FaceProcessor(margin=0.10) as processor:
            # Small face: area = 0.1 * 0.1 = 0.01
            small_face = self._create_mock_detection(0.1, 0.1, 0.1, 0.1, score=0.75)
            # Dominant face: area = 0.5 * 0.5 = 0.25
            dominant_face = self._create_mock_detection(0.3, 0.3, 0.5, 0.5, score=0.96)

            mock_results = MagicMock()
            mock_results.detections = [small_face, dominant_face]
            processor._detector.process = MagicMock(return_value=mock_results)

            result = processor.process(self.blank_image_path, strict_single_face=False)

            # Should pick dominant face
            self.assertAlmostEqual(result.detection_confidence, 0.96)
            if os.path.exists(result.temp_file_path):
                os.remove(result.temp_file_path)

    def test_strict_single_face_error(self):
        """Test MultipleFacesDetectedError when strict_single_face is True."""
        with FaceProcessor() as processor:
            face1 = self._create_mock_detection(0.1, 0.1, 0.2, 0.2)
            face2 = self._create_mock_detection(0.5, 0.5, 0.3, 0.3)
            mock_results = MagicMock()
            mock_results.detections = [face1, face2]
            processor._detector.process = MagicMock(return_value=mock_results)

            with self.assertRaises(MultipleFacesDetectedError):
                processor.process(self.blank_image_path, strict_single_face=True)

    def test_margin_clamping_at_boundaries(self):
        """Test that margin expansion cleanly clamps at 0 and max dimensions."""
        with FaceProcessor(margin=0.5) as processor:
            # Face right on top-left edge
            det = self._create_mock_detection(0.0, 0.0, 0.8, 0.8, score=0.99)
            mock_results = MagicMock()
            mock_results.detections = [det]
            processor._detector.process = MagicMock(return_value=mock_results)

            result = processor.process(self.blank_image_path)
            x1, y1, x2, y2 = result.crop_box

            # Clamped at 0
            self.assertEqual(x1, 0)
            self.assertEqual(y1, 0)
            # Clamped at width=400, height=300
            self.assertEqual(x2, 400)
            self.assertEqual(y2, 300)

            if os.path.exists(result.temp_file_path):
                os.remove(result.temp_file_path)

    def test_quality_check_flag(self):
        """Test quality_check=False sets blur_score to 0.0."""
        with FaceProcessor() as processor:
            det = self._create_mock_detection(0.2, 0.2, 0.4, 0.4, score=0.90)
            mock_results = MagicMock()
            mock_results.detections = [det]
            processor._detector.process = MagicMock(return_value=mock_results)

            result = processor.process(self.blank_image_path, quality_check=False)
            self.assertEqual(result.blur_score, 0.0)

            if os.path.exists(result.temp_file_path):
                os.remove(result.temp_file_path)

    def test_cli_execution_no_face_error(self):
        """Test CLI command execution when image has no face."""
        cmd = [
            sys.executable,
            "src/face_processor.py",
            "--image",
            str(self.blank_image_path),
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        output = json.loads(proc.stdout)
        self.assertEqual(output.get("error"), "NoFaceDetectedError")


if __name__ == "__main__":
    unittest.main()
