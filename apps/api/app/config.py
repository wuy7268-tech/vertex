from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vertex:vertex@localhost:5432/vertex"
    redis_url: str = "redis://localhost:6379/0"
    vertex_scheduler: bool = True
    vertex_auto_seed: bool = True
    vertex_llm_base_url: str = "https://api.openai.com/v1"
    vertex_llm_api_key: str = ""
    vertex_llm_model: str = "gpt-4o-mini"


def get_settings() -> Settings:
    return Settings()
