import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()


def require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError as e:
        raise RuntimeError(f"Env var {name} must be an int. Got: {v!r}") from e


def env_csv(name: str, default: str) -> List[str]:
    v = os.getenv(name, default)
    return [part.strip() for part in v.split(",") if part.strip()]


@dataclass(frozen=True)
class Settings:
    router_ip: str
    router_username: str
    router_password: str
    db_path: str
    poll_seconds: int
    poll_backoff_max_seconds: int
    api_token: str
    router_connect_timeout_seconds: int
    router_read_timeout_seconds: int
    router_fetch_retries: int
    router_retry_backoff_seconds: int
    cors_origins: List[str]

    @property
    def base_url(self) -> str:
        return f"https://{self.router_ip}"


def get_settings() -> Settings:
    return Settings(
        router_ip=require_env("ROUTER_IP"),
        router_username=require_env("ROUTER_USERNAME"),
        router_password=require_env("ROUTER_PASSWORD"),
        db_path=os.getenv("DB_PATH", "router.db"),
        poll_seconds=env_int("POLL_SECONDS", 60),
        poll_backoff_max_seconds=env_int("POLL_BACKOFF_MAX_SECONDS", 300),
        api_token=os.getenv("API_TOKEN", "changeme"),
        router_connect_timeout_seconds=env_int("ROUTER_CONNECT_TIMEOUT_SECONDS", 5),
        router_read_timeout_seconds=env_int("ROUTER_READ_TIMEOUT_SECONDS", 30),
        router_fetch_retries=env_int("ROUTER_FETCH_RETRIES", 2),
        router_retry_backoff_seconds=env_int("ROUTER_RETRY_BACKOFF_SECONDS", 1),
        cors_origins=env_csv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        ),
    )
