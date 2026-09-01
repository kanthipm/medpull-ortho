from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    # Webhook signing secrets — empty means that provider's deliveries are
    # rejected (verification fails closed; the mock/demo path needs none).
    terra_signing_secret: str = ""
    junction_webhook_secret: str = ""
    # Junction (fka Vital), the wearable aggregator. The API key is the switch:
    # without it the registry reports Junction as needing setup and every
    # Junction endpoint answers 503, while signed deliveries to the webhook are
    # still verified and stored. Sandbox is the default on purpose — a
    # production key against a sandbox host (or the reverse) is a 401 from
    # Junction, never a silent cross-environment write.
    junction_api_key: str = ""
    junction_environment: str = "sandbox"  # sandbox | production
    junction_region: str = "us"  # us | eu
    junction_base_url: str = ""  # explicit override; derived from the two above when empty
    # Where Junction Link sends the patient after they connect a device. Empty
    # leaves them on Junction's own completion screen, which is fine for a
    # link handed over in clinic.
    junction_link_redirect_url: str = ""
    # Intraday heart-rate samples are the one Junction stream nothing in the
    # engine reads (ANALYZED_METRICS scores resting HR, not HR_SAMPLE) and the
    # one that dwarfs every other in volume — a day of Apple Watch samples is
    # thousands of rows. Off unless someone has a consumer for it.
    junction_ingest_heart_rate_samples: bool = False
    # Local Ollama is OPT-IN (cloud-first product direction): leave the URL
    # empty and the chain is Groq -> deterministic fallback. Set OLLAMA_URL
    # explicitly to use a local model as the middle tier.
    ollama_url: str = ""
    ollama_model: str = "qwen3-vl-agent:latest"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'recovery.db'}"


settings = Settings()
