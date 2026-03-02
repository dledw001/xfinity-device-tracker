import os
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Settings:
    router_ip: str
    router_username: str
    router_password: str
    db_path: str
    poll_seconds: int
    api_token: str

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
        api_token=os.getenv("API_TOKEN", "changeme"),
    )