"""
Loads and validates YAML configuration for the finance-bilanz tool.

Uses a Pydantic model so config fields are accessible as attributes
(config.accounts, config.paths, ...) with automatic type validation.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError


# +---------------------------------------------------
# Model
# +---------------------------------------------------
class Config(BaseModel):
    """Typed representation of config/config.yaml."""
    accounts: dict[str, str]
    savings_accounts: list[str] = []
    paths: dict[str, Path] = {}


# +---------------------------------------------------
# Loader
# +---------------------------------------------------
def load_config(config_path: Path | str) -> Config:
    """
    Load a YAML config file, validate it, and return a Config object.

    Args:
        config_path: Path to the YAML file

    Returns:
        Validated Config instance

    Raises:
        FileNotFoundError: If the file does not exist
        yaml.YAMLError: If the YAML is invalid
        pydantic.ValidationError: If required fields are missing or have wrong types
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(**raw)
