from types import SimpleNamespace

from algorithm.algorithms.object_detection.yolo import detections_from_result


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


def test_empty_result_has_no_detections() -> None:
    result = SimpleNamespace(boxes=None, names={}, speed=None)

    batch = detections_from_result(result)

    assert batch.detections == ()
    assert batch.inference_ms == 0.0
