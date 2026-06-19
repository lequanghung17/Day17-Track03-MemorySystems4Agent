from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from model_provider import ProviderConfig


SUPPORTED_PROVIDERS = {
    "openai",
    "custom",
    "gemini",
    "anthropic",
    "ollama",
    "openrouter",
}

PROVIDER_ALIASES = {
    "gpt": "openai",
    "chatgpt": "openai",
    "google": "gemini",
    "google-genai": "gemini",
    "anthorpic": "anthropic",
    "claude": "anthropic",
    "local": "ollama",
    "open-router": "openrouter",
}

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "custom": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
    "anthropic": "claude-3-5-haiku-latest",
    "ollama": "llama3.1",
    "openrouter": "openai/gpt-4o-mini",
}


@dataclass
class LabConfig:
    """Student TODO: define the shared configuration for the lab.

    Hints:
    - Keep paths for the repo root, dataset directory, and state directory.
    - Add compact-memory settings such as threshold and number of messages to keep.
    - Add provider settings for `openai`, `custom`, `gemini`, `anthropic`, `ollama`, and `openrouter`.
    """

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Student TODO: load environment variables and return a LabConfig.

    Pseudocode:
    1. Resolve the repo root or default to the current file parent.
    2. Optionally load values from `.env`.
    3. Create `state/` if it does not exist.
    4. Return a populated LabConfig instance.
    """

    root = (base_dir or Path(__file__).resolve().parent.parent).resolve()
    _load_dotenv_if_available(root)

    data_dir = _path_from_env("DATA_DIR", root / "data")
    state_dir = _path_from_env("STATE_DIR", root / "state")
    state_dir.mkdir(parents=True, exist_ok=True)

    provider = _provider_from_env("LLM_PROVIDER", "openai")
    judge_provider = _provider_from_env("JUDGE_PROVIDER", provider)

    return LabConfig(
        base_dir=root,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=_int_from_env("COMPACT_THRESHOLD_TOKENS", 1200),
        compact_keep_messages=_int_from_env("COMPACT_KEEP_MESSAGES", 6),
        model=_build_provider_config(prefix="LLM", provider=provider),
        judge_model=_build_provider_config(prefix="JUDGE", provider=judge_provider),
    )


def _load_dotenv_if_available(root: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(root / ".env")


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default.resolve()

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = default.parent / path
    return path.resolve()


def _int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc

    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0, got {parsed}")
    return parsed


def _float_from_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default

    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float, got {value!r}") from exc


def _provider_from_env(name: str, default: str) -> str:
    raw_provider = os.getenv(name, default).strip().lower()
    provider = PROVIDER_ALIASES.get(raw_provider, raw_provider)
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise ValueError(f"{name} must be one of: {supported}. Got {raw_provider!r}")
    return provider


def _build_provider_config(prefix: str, provider: str) -> ProviderConfig:
    env_prefix = prefix.upper()
    model_name = os.getenv(f"{env_prefix}_MODEL", DEFAULT_MODELS[provider])
    temperature = _float_from_env(f"{env_prefix}_TEMPERATURE", 0.0)

    return ProviderConfig(
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        api_key=_api_key_for_provider(env_prefix, provider),
        base_url=_base_url_for_provider(env_prefix, provider),
    )


def _api_key_for_provider(env_prefix: str, provider: str) -> str | None:
    specific_names = {
        "openai": "OPENAI_API_KEY",
        "custom": "CUSTOM_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    return os.getenv(f"{env_prefix}_API_KEY") or os.getenv(specific_names.get(provider, ""))


def _base_url_for_provider(env_prefix: str, provider: str) -> str | None:
    specific_names = {
        "custom": "CUSTOM_BASE_URL",
        "ollama": "OLLAMA_BASE_URL",
        "openrouter": "OPENROUTER_BASE_URL",
    }
    default_urls = {
        "ollama": "http://localhost:11434",
        "openrouter": "https://openrouter.ai/api/v1",
    }

    return (
        os.getenv(f"{env_prefix}_BASE_URL")
        or os.getenv(specific_names.get(provider, ""))
        or default_urls.get(provider)
    )
