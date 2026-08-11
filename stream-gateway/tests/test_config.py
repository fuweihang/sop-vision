from app.core.config import Settings


def test_cors_origins_are_parsed_from_comma_separated_environment_variable(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "STREAM_GATEWAY_CORS_ORIGINS",
        "http://localhost:5173, https://vision.example.com",
    )

    settings = Settings()

    assert settings.stream_gateway_cors_origins == [
        "http://localhost:5173",
        "https://vision.example.com",
    ]
