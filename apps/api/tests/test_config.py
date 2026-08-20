from src.core.config import get_settings


def test_settings_initialization():
    settings = get_settings()
    assert settings.SERVICE_NAME == "tradedna-api"
    assert settings.SERVICE_VERSION == "1.0.0"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7
    assert settings.PAIRING_TOKEN_EXPIRE_MINUTES == 5
