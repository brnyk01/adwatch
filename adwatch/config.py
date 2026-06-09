from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    meta_access_token: str = ""
    meta_api_version: str = "v22.0"

    google_application_credentials: str = ""  # path to service-account JSON

    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""

    database_url: str = "sqlite:///adwatch.db"


settings = Settings()
