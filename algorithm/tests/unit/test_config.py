from pathlib import Path

import pytest

from algorithm.common.config import (
    DEFAULT_REDIS_URL,
    AlgorithmConfigError,
    default_config_path,
    load_algorithm_config,
    redact_url,
)


def test_redact_url_hides_rtsp_credentials() -> None:
    value = "rtsp://admin:secret%23@192.168.1.10:554/stream"

    assert redact_url(value) == "rtsp://***:***@192.168.1.10:554/stream"


def test_toml_使用默认redis并按worker解析相对模型路径(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime.toml"
    _write_config(config_path, include_redis=False)

    config = load_algorithm_config(config_path)

    assert config.redis_url == DEFAULT_REDIS_URL
    assert config.model_path_for("detector") == (
        tmp_path / "models/detector.pt"
    ).resolve()
    assert config.model_path_for("tracker") == (
        tmp_path / "models/tracker.pt"
    ).resolve()


def test_toml_绝对模型路径保持不变(tmp_path: Path) -> None:
    absolute_model = tmp_path / "shared/model.pt"
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(
        f'''[workers.detector]
model_path = "{absolute_model}"

[workers.tracker]
model_path = "{absolute_model}"
''',
        encoding="utf-8",
    )

    config = load_algorithm_config(config_path)

    assert config.model_path_for("detector") == absolute_model
    assert config.model_path_for("tracker") == absolute_model


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("redis_url = [", "无法读取外围配置文件"),
        (
            '''redis_url = "redis://user:secret@localhost/0"
[workers.detector]
model_path = "detector.pt"
''',
            "workers.tracker.model_path",
        ),
        (
            '''unexpected = "redis://user:secret@localhost/0"
[workers.detector]
model_path = "detector.pt"
[workers.tracker]
model_path = "tracker.pt"
''',
            "unexpected",
        ),
        (
            '''[workers.detector]
model_path = "detector.pt"
extra = "redis://user:secret@localhost/0"
[workers.tracker]
model_path = "tracker.pt"
''',
            "workers.detector.extra",
        ),
    ],
)
def test_toml_错误只报告文件或字段且不回显凭据(
    tmp_path: Path,
    content: str,
    expected: str,
) -> None:
    config_path = tmp_path / "invalid.toml"
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises(AlgorithmConfigError) as captured:
        load_algorithm_config(config_path)

    assert expected in str(captured.value)
    assert "secret" not in str(captured.value)


def test_toml_缺少文件时报告完整路径(tmp_path: Path) -> None:
    config_path = tmp_path / "missing.toml"

    with pytest.raises(AlgorithmConfigError) as captured:
        load_algorithm_config(config_path)

    assert str(config_path) in str(captured.value)


def test_default_config_path_优先使用环境变量(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "custom.toml"
    monkeypatch.setenv("ALGORITHM_CONFIG", str(configured))

    assert default_config_path() == configured


def _write_config(path: Path, *, include_redis: bool) -> None:
    redis = 'redis_url = "redis://custom/0"\n\n' if include_redis else ""
    path.write_text(
        redis
        + '''[workers.detector]
model_path = "models/detector.pt"

[workers.tracker]
model_path = "models/tracker.pt"
''',
        encoding="utf-8",
    )
