"""
config.py — Configuration loader for Attendance Agent.

Reads from attendance_agent.toml (co-located with the package)
and can be overridden by environment variables.
"""
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # pip install tomli
    except ImportError:
        tomllib = None  # type: ignore


# Default config file locations (searched in order)
_CONFIG_SEARCH = [
    Path(__file__).parent / "attendance_agent.toml",
    Path.home() / ".secure_attendance" / "attendance_agent.toml",
    Path("attendance_agent.toml"),
]


@dataclass
class AgentConfig:
    # Agent HTTP server settings
    port: int = 5000
    host: str = "0.0.0.0"
    hotspot_ip: str = "192.168.137.1"

    # Django connection
    django_url: str = "https://192-168-137-1.sslip.io:8000"
    api_token: str = ""
    verify_ssl: bool = False  # False for local dev with self-signed cert

    # Key storage
    key_dir: Path = field(default_factory=lambda: Path.home() / ".secure_attendance")

    # Cryptographic settings
    challenge_ttl_seconds: int = 30
    heartbeat_interval_seconds: int = 30

    # mDNS advertisement (optional)
    mdns_enabled: bool = False
    mdns_name: str = "attendance"

    @property
    def key_path(self) -> Path:
        return self.key_dir / "agent_key.pem"

    @property
    def pub_key_path(self) -> Path:
        return self.key_dir / "agent_pub.pem"


def load_config(config_path: Optional[str] = None) -> AgentConfig:
    """
    Load configuration from TOML file (with env-var overrides).
    Falls back to defaults if no config file found.
    """
    raw: dict = {}

    paths_to_try = [Path(config_path)] if config_path else _CONFIG_SEARCH
    for p in paths_to_try:
        if p.exists():
            if tomllib is None:
                print(
                    f"[WARN] tomllib/tomli not available — cannot read {p}. "
                    "Run: pip install tomli (Python < 3.11). Using defaults.",
                    file=sys.stderr,
                )
            else:
                with open(p, "rb") as f:
                    raw = tomllib.load(f)
            break

    agent_sec = raw.get("agent", {})
    django_sec = raw.get("django", {})

    cfg = AgentConfig(
        port=int(os.getenv("AGENT_PORT", agent_sec.get("port", 5000))),
        host=os.getenv("AGENT_HOST", agent_sec.get("host", "0.0.0.0")),
        hotspot_ip=os.getenv("AGENT_HOTSPOT_IP", agent_sec.get("hotspot_ip", "192.168.137.1")),
        django_url=os.getenv("DJANGO_URL", django_sec.get("url", "https://13-127-69-218.sslip.io")),
        api_token=os.getenv("ATTENDANCE_AGENT_API_TOKEN", django_sec.get("api_token", "secure_presence_v3_default_token")),
        verify_ssl=os.getenv("DJANGO_VERIFY_SSL", str(django_sec.get("verify_ssl", False))).lower() == "true",
        key_dir=Path(os.getenv("AGENT_KEY_DIR", agent_sec.get("key_dir", str(Path.home() / ".secure_attendance")))),
        challenge_ttl_seconds=int(os.getenv("CHALLENGE_TTL", agent_sec.get("challenge_ttl_seconds", 30))),
        heartbeat_interval_seconds=int(os.getenv("HEARTBEAT_INTERVAL", agent_sec.get("heartbeat_interval_seconds", 30))),
        mdns_enabled=os.getenv("MDNS_ENABLED", str(agent_sec.get("mdns_enabled", False))).lower() == "true",
        mdns_name=os.getenv("MDNS_NAME", agent_sec.get("mdns_name", "attendance")),
    )

    cfg.key_dir.mkdir(parents=True, exist_ok=True)
    return cfg
