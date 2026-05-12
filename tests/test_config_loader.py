"""Tests for src.config_loader."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.config_loader import Config, load_config


# +---------------------------------------------------
# load_config
# +---------------------------------------------------
class TestLoadConfig:
    def test_returns_config_object(self, example_config_path):
        """Returns a Config instance, not a raw dict."""
        config = load_config(example_config_path)
        assert isinstance(config, Config)

    def test_raises_on_missing_file(self, tmp_path):
        """Raises FileNotFoundError for a non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "does_not_exist.yaml")

    def test_raises_on_invalid_yaml(self, tmp_path):
        """Raises YAMLError for invalid YAML."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("key: value\n  bad: indentation: here")
        with pytest.raises(yaml.YAMLError):
            load_config(bad_file)

    def test_raises_on_missing_required_field(self, tmp_path):
        """Raises ValidationError if 'accounts' is missing."""
        cfg = tmp_path / "no_accounts.yaml"
        cfg.write_text("savings_accounts:\n  - depot\n")
        with pytest.raises(ValidationError):
            load_config(cfg)

    def test_accepts_str_and_path(self, example_config_path):
        """Accepts both str and Path as argument."""
        assert load_config(example_config_path).accounts == load_config(str(example_config_path)).accounts


# +---------------------------------------------------
# Config.accounts
# +---------------------------------------------------
class TestAccounts:
    def test_accessible_as_attribute(self, example_config_path):
        """accounts is accessible directly on the config object."""
        config = load_config(example_config_path)
        assert isinstance(config.accounts, dict)
        assert config.accounts["DE69120300001016456459"] == "fixkonto"

    def test_includes_paypal(self, example_config_path):
        """PayPal email is present as an account identifier."""
        assert load_config(example_config_path).accounts["TOBI.KLATT@WEB.DE"] == "paypal"


# +---------------------------------------------------
# Config.paths
# +---------------------------------------------------
class TestPaths:
    def test_accessible_as_attribute(self, example_config_path):
        """paths is accessible directly on the config object."""
        config = load_config(example_config_path)
        assert isinstance(config.paths, dict)

    def test_values_are_path_objects(self, example_config_path):
        """Path strings are automatically converted to Path objects by Pydantic."""
        for value in load_config(example_config_path).paths.values():
            assert isinstance(value, Path)

    def test_contains_expected_keys(self, example_config_path):
        """Contains the expected path keys."""
        paths = load_config(example_config_path).paths
        assert {"raw_dir", "processed_dir", "labeled_dir", "bilanz_dir"}.issubset(paths.keys())

    def test_defaults_to_empty_dict(self, tmp_path):
        """Defaults to empty dict if 'paths' section is absent."""
        cfg = tmp_path / "no_paths.yaml"
        cfg.write_text("accounts:\n  DE123: fixkonto\n")
        assert load_config(cfg).paths == {}


# +---------------------------------------------------
# Config.savings_accounts
# +---------------------------------------------------
class TestSavingsAccounts:
    def test_accessible_as_attribute(self, example_config_path):
        """savings_accounts is accessible directly on the config object."""
        savings = load_config(example_config_path).savings_accounts
        assert isinstance(savings, list)
        assert "depot" in savings
        assert "sparkonto" in savings

    def test_excludes_geteiltes_sparkonto(self, example_config_path):
        """geteiltes_sparkonto is intentionally NOT in savings_accounts."""
        assert "geteiltes_sparkonto" not in load_config(example_config_path).savings_accounts

    def test_defaults_to_empty_list(self, tmp_path):
        """Defaults to empty list if 'savings_accounts' section is absent."""
        cfg = tmp_path / "no_savings.yaml"
        cfg.write_text("accounts:\n  DE123: fixkonto\n")
        assert load_config(cfg).savings_accounts == []
