from types import SimpleNamespace

import numpy as np

from algorithm.algorithms.object_detection.detection import YoloDetector
from algorithm.algorithms.object_tracking.bytetrack import YoloTracker
from algorithm.algorithms.yolo import detections_from_result


class FakeTensor:
    def __init__(self, value):
        self.value = value

    def cpu(self):
        return self

    def tolist(self):
        return self.value


class FakeBoxes:
    xyxy = FakeTensor([[10.0, 20.0, 110.0, 220.0]])
    conf = FakeTensor([0.91])
    cls = FakeTensor([0.0])

    def __len__(self):
        return 1


def test_ultralytics_result_is_converted_to_owned_values() -> None:
    result = SimpleNamespace(
        boxes=FakeBoxes(),
        names={0: "person"},
        speed={"inference": 12.5},
    )

    batch = detections_from_result(result)

    assert batch.inference_ms == 12.5
    assert len(batch.detections) == 1
    assert batch.detections[0].class_name == "person"
    assert batch.detections[0].confidence == 0.91
    assert batch.detections[0].bbox == (10.0, 20.0, 110.0, 220.0)
    assert batch.detections[0].track_id is None


def test_empty_result_has_no_detections() -> None:
    result = SimpleNamespace(boxes=None, names={}, speed=None)

    batch = detections_from_result(result)

    assert batch.detections == ()
    assert batch.inference_ms == 0.0


def test_追踪结果会保留bytetrack编号() -> None:
    boxes = FakeBoxes()
    boxes.id = FakeTensor([37.0])
    result = SimpleNamespace(
        boxes=boxes,
        names={0: "person"},
        speed={"inference": 8.5},
    )

    batch = detections_from_result(result)

    assert batch.detections[0].track_id == 37


def test_yolo检测器调用predict并转换结果() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.arguments = None

        def predict(self, **arguments):
            self.arguments = arguments
            return [
                SimpleNamespace(
                    boxes=FakeBoxes(),
                    names={0: "person"},
                    speed={"inference": 7.0},
                )
            ]

    model = FakeModel()
    detector = object.__new__(YoloDetector)
    detector._model = model
    detector._image_size = 640
    detector._confidence = 0.5
    detector._device = "cpu"

    batch = detector.predict(np.zeros((10, 10, 3), dtype=np.uint8))

    assert batch.detections[0].track_id is None
    assert model.arguments["device"] == "cpu"
    assert "persist" not in model.arguments


def test_yolo追踪器固定使用bytetrack() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.arguments = None

        def track(self, **arguments):
            self.arguments = arguments
            boxes = FakeBoxes()
            boxes.id = FakeTensor([8.0])
            return [
                SimpleNamespace(
                    boxes=boxes,
                    names={0: "person"},
                    speed={"inference": 6.0},
                )
            ]

    model = FakeModel()
    tracker = object.__new__(YoloTracker)
    tracker._model = model
    tracker._image_size = 640
    tracker._confidence = 0.5
    tracker._device = "cpu"

    batch = tracker.track(np.zeros((10, 10, 3), dtype=np.uint8))

    assert batch.detections[0].track_id == 8
    assert model.arguments["persist"] is True
    assert model.arguments["tracker"] == "bytetrack.yaml"
    assert model.arguments["device"] == "cpu"
