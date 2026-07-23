"""Standalone smoke-test for the Bob inference gateway.

Run from the project root:
    .venv/bin/python scripts/test_bob.py

Reads credentials from .env via pydantic-settings (same as the app).
No project imports required.
"""
import httpx
from openai import OpenAI
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class _BobSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIRP_", env_file=".env", extra="ignore")
    bob_auth_token: str
    bob_base_url: AnyHttpUrl = "https://api.us-east.bob.ibm.com"
    bob_instance_id: str | None = None
    bob_team_id: str | None = None


cfg = _BobSettings()

auth_headers: dict[str, str] = {"Authorization": f"Apikey {cfg.bob_auth_token}"}
if cfg.bob_instance_id:
    auth_headers["x-instance-id"] = cfg.bob_instance_id
if cfg.bob_team_id:
    auth_headers["x-team-id"] = cfg.bob_team_id

# BOB requires "Authorization: Apikey <token>", not "Bearer <token>".
# api_key="dummy" stops the SDK from overwriting the header we set above.
client = OpenAI(
    api_key="dummy",
    base_url=f"{str(cfg.bob_base_url).rstrip('/')}/inference/v1",
    default_headers=auth_headers,
    http_client=httpx.Client(timeout=120.0),
)

response = client.chat.completions.create(
    model="haiku-4.5",
    messages=[{"role": "user", "content": "Explain this project"}],
    max_tokens=100,
)
print(response.choices[0].message.content)
