"""
Pytest fixtures shared across all tests.
"""

import sys
from pathlib import Path

import pytest

# Add project root to sys.path so `from src...` works in tests
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# +---------------------------------------------------
# Paths
# +---------------------------------------------------
@pytest.fixture
def fixtures_dir() -> Path:
    """Directory containing test fixture files (Excel, YAML, etc.)."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def example_config_path(fixtures_dir) -> Path:
    """Path to the example config YAML used in tests."""
    return fixtures_dir / "example_config.yaml"


@pytest.fixture
def example_labels_path(fixtures_dir) -> Path:
    """Path to the example labels YAML used in tests."""
    return fixtures_dir / "example_labels.yaml"


@pytest.fixture
def example_excel_path(fixtures_dir) -> Path:
    """Path to the example raw bank export (~15 rows, various edge cases)."""
    return fixtures_dir / "example_raw.xlsx"


# +---------------------------------------------------
# Account mappings
# +---------------------------------------------------
@pytest.fixture
def real_accounts(example_config_path) -> dict[str, str]:
    """
    Full account mapping loaded from example_config.yaml.

    Used in integration and E2E tests to verify all accounts
    from the real config are handled correctly.
    """
    from src.config_loader import load_config
    return load_config(example_config_path).accounts


@pytest.fixture
def real_savings_accounts(example_config_path) -> list[str]:
    """Savings accounts list loaded from example_config.yaml."""
    from src.config_loader import load_config
    return load_config(example_config_path).savings_accounts


@pytest.fixture
def mini_accounts() -> dict[str, str]:
    """
    Minimal in-memory account mapping for fast unit tests.

    Keeps unit tests focused and independent of config files.
    """
    return {
        "DE69120300001016456459": "fixkonto",
        "DE17100110012621473008": "flexkonto",
        "50650840 7": "depot",
    }


@pytest.fixture
def mini_savings() -> list[str]:
    """Minimal savings accounts list for fast unit tests."""
    return ["depot", "sparkonto"]
