from app.config import BASE_DIR, Settings


def test_settings_expose_base_dir() -> None:
    settings = Settings()
    assert settings.base_dir == BASE_DIR
