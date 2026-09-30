"""Configuration for the Kubernetes inspection agent."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    k8s_mcp_url: str = "http://127.0.0.1:8083/mcp"
    k8s_mcp_token: str = field(default="", repr=False)
    public_base_url: str = "http://localhost:8002"
    model: str = "gemini-3.6-flash"
    # Google recommends the default 1.0 for Gemini 3 to avoid degraded reasoning.
    temperature: float = 1.0
    port: int = 8002

    @classmethod
    def from_env(cls) -> "Settings":
        # The second path also works with `uv run --project k8s-agent` from its parent.
        load_dotenv(Path.cwd() / ".env", override=False)
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        settings = cls(
            k8s_mcp_url=os.getenv(
                "K8S_MCP_URL", "http://127.0.0.1:8083/mcp"
            ).strip(),
            k8s_mcp_token=os.getenv("K8S_MCP_TOKEN", "").strip(),
            public_base_url=os.getenv(
                "K8S_AGENT_BASE_URL", "http://localhost:8002"
            ).strip(),
            model=os.getenv("K8S_AGENT_MODEL", "gemini-3.6-flash").strip(),
            temperature=float(os.getenv("K8S_AGENT_TEMPERATURE", "1.0")),
            port=int(os.getenv("PORT", "8002")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        for name, value in (
            ("K8S_MCP_URL", self.k8s_mcp_url),
            ("K8S_AGENT_BASE_URL", self.public_base_url),
        ):
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"{name} must be an HTTP(S) URL")
        if not self.model:
            raise ValueError("K8S_AGENT_MODEL is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        if not 0 <= self.temperature <= 1:
            raise ValueError("K8S_AGENT_TEMPERATURE must be between 0 and 1")
