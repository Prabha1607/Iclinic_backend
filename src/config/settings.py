from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str

    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    ALGORITHM: str
    ACCESS_SECRET_KEY: str
    REFRESH_SECRET_KEY: str

    GROQ_API_KEYS: str
    DEEPGRAM_API_KEY: str
    TWILIO_SID: str
    TWILIO_AUTH: str
    TWILIO_NUMBER: str
    MY_PHONE: str
    TWIML_BIN_URL: str

    VOICE : str
    LANGUAGE : str
    SPEECH_TIMEOUT : str
    ACTION_ON_EMPTY_RESULT : str
    GATHER_TIMEOUT : int

    SPEAKING_RATE : str

    SESSION_TTL_SECONDS : int

    EMAIL_USERNAME: str
    EMAIL_PASSWORD: str
    EMAIL_FROM: str
    EMAIL_PORT: int
    EMAIL_SERVER: str
    EMAIL_STARTTLS: bool
    EMAIL_SSL_TLS: bool
    EMAIL_USE_CREDENTIALS: bool

    EMERGENCY_FORWARD_NUMBER : str

    @property
    def groq_keys_list(self) -> List[str]:
        return [k.strip() for k in self.GROQ_API_KEYS.split(",")]

    class Config:
        env_file = ".env"

settings = Settings()


