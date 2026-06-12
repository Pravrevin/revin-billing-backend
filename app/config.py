from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://billing_user:billing_pass@localhost:5432/billing_db"

    # JWT auth. Override jwt_secret in .env for production.
    jwt_secret: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Mistral key for AI bill extraction (purchase "Upload Bill"). Override in .env.
    mistral_api_key: str = "o3b9BdvJ0NZrYu0zPydJS0xD7c3kHG7Y"

    # GST verification (Add Supplier → "Fetch details"). Set a key from a GST
    # lookup provider in .env to auto-fill supplier details from a GSTIN.
    # Supported providers: "appyflow" (default). Without a key, lookups still
    # validate the GSTIN and derive the state + PAN from the number itself.
    gst_api_key: str = ""
    gst_api_provider: str = "appyflow"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
