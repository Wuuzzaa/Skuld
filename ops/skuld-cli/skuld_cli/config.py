"""Load server/environment configuration."""

from pathlib import Path

import yaml


def _find_config() -> Path:
    """Find environments.yaml — either in the repo root or next to this file."""
    # When installed editable from the repo, walk up to find ops/environments.yaml
    here = Path(__file__).resolve().parent
    for ancestor in [here, *here.parents]:
        candidate = ancestor / "ops" / "environments.yaml"
        if candidate.exists():
            return candidate
    # Fallback: bundled copy next to this file
    fallback = here / "environments.yaml"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(
        "Cannot find environments.yaml. "
        "Run from the repo root or install the CLI with `pip install -e .`"
    )


def load_config() -> dict:
    """Load environments.yaml and wrap it in the expected structure."""
    config_path = _find_config()
    with open(config_path) as f:
        envs = yaml.safe_load(f)
    return {
        "repo": "Wuuzzaa/Skuld",
        "environments": envs,
    }


def get_repo(config: dict) -> str:
    return config["repo"]


def get_env(config: dict, name: str) -> dict:
    envs = config["environments"]
    if name not in envs:
        valid = ", ".join(envs.keys())
        raise KeyError(f"Unknown environment '{name}'. Valid: {valid}")
    return envs[name]


def list_envs(config: dict) -> dict:
    return config["environments"]
