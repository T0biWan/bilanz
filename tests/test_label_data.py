"""Tests for src.label_data."""

import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from src.label_data import Label, LabelRule, apply_labels, apply_manual_labels, load_labels


# +---------------------------------------------------
# Helpers
# +---------------------------------------------------
def make_row(**kwargs) -> pd.Series:
    """Create a minimal transaction row for unit tests."""
    defaults = {
        "beguenstigter": "",
        "verwendungszweck": "",
        "betrag": -10.0,
    }
    return pd.Series({**defaults, **kwargs})


def make_label(category: str, name: str, match: str, rules: list[dict]) -> Label:
    """Create a Label object for unit tests."""
    return Label(
        category=category,
        name=name,
        match=match,
        rules=[LabelRule(**r) for r in rules],
    )


# +---------------------------------------------------
# load_labels
# +---------------------------------------------------
class TestLoadLabels:
    def test_returns_list_of_labels(self, example_labels_path):
        """Returns a list of Label objects."""
        labels = load_labels(example_labels_path)
        assert isinstance(labels, list)
        assert all(isinstance(l, Label) for l in labels)

    def test_injects_category(self, example_labels_path):
        """Category is set from the top-level YAML key."""
        labels = load_labels(example_labels_path)
        lidl = next(l for l in labels if l.name == "lidl")
        assert lidl.category == "lebensmittel"

    def test_match_is_preserved(self, example_labels_path):
        """match field is loaded correctly."""
        labels = load_labels(example_labels_path)
        dkb = next(l for l in labels if l.name == "dkb_sparplan")
        assert dkb.match == "all"

    def test_raises_on_missing_file(self, tmp_path):
        """Raises FileNotFoundError for non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_labels(tmp_path / "does_not_exist.yaml")

    def test_raises_on_missing_match_field(self, tmp_path):
        """Raises ValidationError if 'match' is missing (required field)."""
        bad = tmp_path / "bad_labels.yaml"
        bad.write_text(
            "lebensmittel:\n"
            "  - name: lidl\n"
            "    rules:\n"
            "      - field: beguenstigter\n"
            "        regex: lidl\n"
        )
        with pytest.raises(ValidationError):
            load_labels(bad)

    def test_raises_on_invalid_yaml(self, tmp_path):
        """Raises YAMLError for invalid YAML."""
        bad = tmp_path / "bad.yaml"
        bad.write_text("key: value\n  bad: indentation: here")
        with pytest.raises(yaml.YAMLError):
            load_labels(bad)


# +---------------------------------------------------
# _matches via apply_labels (unit)
# +---------------------------------------------------
class TestLabelMatching:
    def test_any_matches_first_rule(self):
        """match=any: first rule match is sufficient."""
        label = make_label("lebensmittel", "lidl", "any", [
            {"field": "beguenstigter", "regex": "(?i)lidl"},
            {"field": "verwendungszweck", "regex": "(?i)lidl"},
        ])
        row = make_row(beguenstigter="Lidl Sagt Danke")
        df = pd.DataFrame([row])
        result = apply_labels(df, [label])
        assert result.iloc[0]["label"] == "lebensmittel"
        assert result.iloc[0]["sublabel"] == "lidl"

    def test_any_matches_second_rule(self):
        """match=any: second rule match is sufficient."""
        label = make_label("lebensmittel", "edeka", "any", [
            {"field": "beguenstigter", "regex": "(?i)edeka"},
            {"field": "verwendungszweck", "regex": "(?i)edeka"},
        ])
        row = make_row(verwendungszweck="Edeka Einkauf")
        df = pd.DataFrame([row])
        result = apply_labels(df, [label])
        assert result.iloc[0]["sublabel"] == "edeka"

    def test_all_requires_both_rules(self):
        """match=all: both rules must match."""
        label = make_label("test", "dkb_sparplan", "all", [
            {"field": "beguenstigter", "regex": "(?i)dkb"},
            {"field": "verwendungszweck", "regex": "(?i)sparplan"},
        ])
        row_both = make_row(beguenstigter="DKB", verwendungszweck="Sparplan ETF")
        row_one = make_row(beguenstigter="DKB", verwendungszweck="Ueberweisung")
        df = pd.DataFrame([row_both, row_one])
        result = apply_labels(df, [label])
        assert result.iloc[0]["sublabel"] == "dkb_sparplan"
        assert pd.isna(result.iloc[1]["sublabel"])

    def test_no_match_returns_none(self):
        """Unmatched row gets NaN for label and sublabel."""
        label = make_label("lebensmittel", "lidl", "any", [
            {"field": "beguenstigter", "regex": "(?i)lidl"},
        ])
        row = make_row(beguenstigter="Spotify")
        df = pd.DataFrame([row])
        result = apply_labels(df, [label])
        assert pd.isna(result.iloc[0]["label"])
        assert pd.isna(result.iloc[0]["sublabel"])

    def test_first_match_wins(self):
        """When multiple labels match, the first one in the list wins."""
        label_a = make_label("cat_a", "label_a", "any", [
            {"field": "beguenstigter", "regex": "(?i)test"},
        ])
        label_b = make_label("cat_b", "label_b", "any", [
            {"field": "beguenstigter", "regex": "(?i)test"},
        ])
        row = make_row(beguenstigter="test")
        df = pd.DataFrame([row])
        result = apply_labels(df, [label_a, label_b])
        assert result.iloc[0]["label"] == "cat_a"
        assert result.iloc[0]["sublabel"] == "label_a"

    def test_case_insensitive_regex(self):
        """Regex is applied as-is — (?i) flag in yaml makes it case-insensitive."""
        label = make_label("lebensmittel", "lidl", "any", [
            {"field": "beguenstigter", "regex": "(?i)lidl"},
        ])
        for name in ["LIDL", "Lidl", "lidl", "LiDl"]:
            df = pd.DataFrame([make_row(beguenstigter=name)])
            assert apply_labels(df, [label]).iloc[0]["sublabel"] == "lidl"

    def test_none_field_value_does_not_crash(self):
        """None values in a field are treated as empty string."""
        label = make_label("lebensmittel", "lidl", "any", [
            {"field": "beguenstigter", "regex": "(?i)lidl"},
        ])
        row = make_row(beguenstigter=None)
        df = pd.DataFrame([row])
        result = apply_labels(df, [label])
        assert pd.isna(result.iloc[0]["label"])


# +---------------------------------------------------
# apply_labels
# +---------------------------------------------------
class TestApplyLabels:
    def test_adds_label_and_sublabel_columns(self, example_labels_path):
        """Output DataFrame has label and sublabel columns."""
        labels = load_labels(example_labels_path)
        df = pd.DataFrame([make_row(beguenstigter="Lidl")])
        result = apply_labels(df, labels)
        assert "label" in result.columns
        assert "sublabel" in result.columns

    def test_original_columns_preserved(self, example_labels_path):
        """Existing columns are not modified."""
        labels = load_labels(example_labels_path)
        df = pd.DataFrame([make_row(beguenstigter="Lidl", betrag=-42.0)])
        result = apply_labels(df, labels)
        assert result.iloc[0]["betrag"] == -42.0
        assert result.iloc[0]["beguenstigter"] == "Lidl"

    def test_input_df_not_mutated(self, example_labels_path):
        """Original DataFrame is not modified."""
        labels = load_labels(example_labels_path)
        df = pd.DataFrame([make_row(beguenstigter="Lidl")])
        apply_labels(df, labels)
        assert "label" not in df.columns

    def test_raises_on_unknown_field(self, example_labels_path):
        """Raises ValueError if a rule references a non-existent column."""
        label = make_label("test", "bad", "any", [
            {"field": "nonexistent_column", "regex": ".*"},
        ])
        df = pd.DataFrame([make_row()])
        with pytest.raises(ValueError, match="unknown field"):
            apply_labels(df, [label])

    def test_multiple_rows(self, example_labels_path):
        """Correctly labels multiple rows with different matches."""
        labels = load_labels(example_labels_path)
        df = pd.DataFrame([
            make_row(beguenstigter="Lidl"),
            make_row(beguenstigter="Spotify"),
            make_row(beguenstigter="Unknown"),
        ])
        result = apply_labels(df, labels)
        assert result.iloc[0]["sublabel"] == "lidl"
        assert result.iloc[1]["sublabel"] == "spotify"
        assert pd.isna(result.iloc[2]["sublabel"])


# +---------------------------------------------------
# apply_manual_labels
# +---------------------------------------------------
class TestApplyManualLabels:
    def _make_manual_xlsx(self, tmp_path, rows: list[dict]) -> str:
        """Helper to create a manual_labels.xlsx in tmp_path."""
        path = tmp_path / "manual_labels.xlsx"
        pd.DataFrame(rows).to_excel(path, index=False)
        return str(path)

    def test_overrides_auto_label(self, tmp_path):
        """Manual label overrides the auto-generated label."""
        df = pd.DataFrame([make_row(beguenstigter="Lidl")])
        df["id"] = "tx-001"
        df["label"] = "lebensmittel"
        df["sublabel"] = "lidl"
        path = self._make_manual_xlsx(tmp_path, [
            {"id": "tx-001", "label": "haushalt", "sublabel": "sonstiges"}
        ])
        result = apply_manual_labels(df, path)
        assert result.iloc[0]["label"] == "haushalt"
        assert result.iloc[0]["sublabel"] == "sonstiges"

    def test_only_matched_rows_are_changed(self, tmp_path):
        """Only the row with the matching id is changed."""
        df = pd.DataFrame([
            {**make_row(beguenstigter="Lidl"), "id": "tx-001", "label": "lebensmittel", "sublabel": "lidl"},
            {**make_row(beguenstigter="Spotify"), "id": "tx-002", "label": "unterhaltung", "sublabel": "streaming"},
        ])
        path = self._make_manual_xlsx(tmp_path, [
            {"id": "tx-001", "label": "haushalt", "sublabel": "sonstiges"}
        ])
        result = apply_manual_labels(df, path)
        assert result.iloc[0]["label"] == "haushalt"
        assert result.iloc[1]["label"] == "unterhaltung"

    def test_missing_file_returns_df_unchanged(self, tmp_path):
        """Returns df unchanged if manual_labels file does not exist."""
        df = pd.DataFrame([{**make_row(), "id": "tx-001", "label": "lebensmittel", "sublabel": "lidl"}])
        result = apply_manual_labels(df, tmp_path / "does_not_exist.xlsx")
        pd.testing.assert_frame_equal(df, result)

    def test_empty_file_returns_df_unchanged(self, tmp_path):
        """Returns df unchanged if manual_labels file is empty."""
        path = self._make_manual_xlsx(tmp_path, [])
        df = pd.DataFrame([{**make_row(), "id": "tx-001", "label": "lebensmittel", "sublabel": "lidl"}])
        result = apply_manual_labels(df, path)
        pd.testing.assert_frame_equal(df, result)

    def test_unknown_id_is_skipped(self, tmp_path):
        """Unknown id in manual_labels logs a warning but does not crash."""
        df = pd.DataFrame([{**make_row(), "id": "tx-001", "label": None, "sublabel": None}])
        path = self._make_manual_xlsx(tmp_path, [
            {"id": "UNKNOWN-ID", "label": "lebensmittel", "sublabel": "lidl"}
        ])
        result = apply_manual_labels(df, path)
        assert pd.isna(result.iloc[0]["label"])

    def test_input_df_not_mutated(self, tmp_path):
        """Original DataFrame is not modified."""
        df = pd.DataFrame([{**make_row(), "id": "tx-001", "label": "lebensmittel", "sublabel": "lidl"}])
        path = self._make_manual_xlsx(tmp_path, [
            {"id": "tx-001", "label": "haushalt", "sublabel": "sonstiges"}
        ])
        apply_manual_labels(df, path)
        assert df.iloc[0]["label"] == "lebensmittel"
