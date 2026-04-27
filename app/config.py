from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://billing_user:billing_pass@localhost:5432/billing_db"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
