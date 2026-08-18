import pytest
from pydantic import ValidationError

from algorithm.contracts.detection import DetectionObject


def test_detection_object_rejects_non_normalized_bbox() -> None:
    with pytest.raises(ValidationError):
        DetectionObject(
            class_id=0,
            class_name="person",
            confidence=0.9,
            bbox=(0.0, 0.0, 1.2, 1.0),
        )


def test_detection_object_rejects_reversed_bbox() -> None:
    with pytest.raises(ValidationError):
        DetectionObject(
            class_id=0,
            class_name="person",
            confidence=0.9,
            bbox=(0.8, 0.0, 0.2, 1.0),
        )
