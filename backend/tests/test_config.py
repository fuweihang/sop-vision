from app.core.config import Settings


def test_cors_origins_are_parsed_from_comma_separated_environment_variable(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:8000, https://vision.example.com",
    )

    settings = Settings()

    assert settings.backend_cors_origins == [
        "http://localhost:8000",
        "https://vision.example.com",
    ]
