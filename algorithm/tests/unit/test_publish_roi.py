import json

from algorithm.tools import publish_roi


class FakeRedis:
    def __init__(self) -> None:
        self.published = None
        self.closed = False

    def publish(self, channel: str, payload: str) -> int:
        self.published = (channel, json.loads(payload))
        return 1

    def close(self) -> None:
        self.closed = True


def test_publish_roi_validates_and_publishes(monkeypatch, capsys) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(
        publish_roi.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: fake,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "publish-roi",
            "--json",
            '{"schema_version":1,"type":"roi_update","task_id":"detector-demo",'
            '"roi_id":"main","enabled":true,'
            '"points":[[0,0],[1,0],[1,1],[0,1]]}',
        ],
    )

    assert publish_roi.main() == 0
    assert fake.published is not None
    assert fake.published[0] == "vision:config:roi:detector-demo"
    assert fake.published[1]["roi_id"] == "main"
    assert fake.closed
    assert "active subscribers: 1" in capsys.readouterr().out


def test_publish_roi_rejects_task_mismatch_before_connecting(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "publish-roi",
            "--task-id",
            "expected",
            "--json",
            '{"schema_version":1,"type":"roi_update","task_id":"other",'
            '"roi_id":"main","enabled":false,"points":[]}',
        ],
    )

    assert publish_roi.main() == 2
