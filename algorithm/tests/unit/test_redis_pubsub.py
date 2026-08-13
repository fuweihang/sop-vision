from algorithm.common.redis_pubsub import RedisRoiSubscriber
from algorithm.common.roi import RoiState


VALID_PAYLOAD = (
    '{"schema_version":1,"type":"roi_update","task_id":"detector-demo",'
    '"roi_id":"main","enabled":true,'
    '"points":[[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]]}'
)


def test_subscriber_applies_valid_message_and_ignores_invalid_message() -> None:
    state = RoiState()
    subscriber = RedisRoiSubscriber(
        "redis://127.0.0.1:63793/0",
        "vision:config:roi:detector-demo",
        "detector-demo",
        state,
    )

    assert subscriber.apply_message(VALID_PAYLOAD)
    active = state.snapshot()
    assert active is not None

    assert not subscriber.apply_message('{"task_id":"wrong"}')
    assert state.snapshot() == active
