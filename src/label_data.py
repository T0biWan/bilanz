"""
Label module for bank transactions.

Applies regex-based label rules (from labels.yaml) to a preprocessed
DataFrame, adding 'label' and 'sublabel' columns.

Label hierarchy:
    label    - top-level category (e.g. 'lebensmittel')
    sublabel - specific match    (e.g. 'lidl')

Two label sources, applied in order (manual always wins):
    1. labels.yaml        - regex rules, applied automatically
    2. manual_labels.xlsx - hand-curated overrides for one-off transactions

First matching rule wins. Unmatched rows get None for both columns.
"""

import logging
import re
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
import yaml
from pydantic import BaseModel, ValidationError


logger = logging.getLogger(__name__)


# +---------------------------------------------------
# Models
# +---------------------------------------------------
class LabelRule(BaseModel):
    """A single regex rule applied to one DataFrame column."""
    field: str
    regex: str


class Label(BaseModel):
    """A named label with one or more rules and a match strategy."""
    name: str
    match: Literal["any", "all"]
    rules: list[LabelRule]
    category: str


# +---------------------------------------------------
# Loader
# +---------------------------------------------------
def load_labels(labels_path: Path | str) -> list[Label]:
    """
    Load and validate a labels YAML file.

    The YAML is structured with categories as top-level keys, each
    containing a list of label definitions. The category name is
    injected into each Label object automatically.

    Args:
        labels_path: Path to the labels YAML file

    Returns:
        List of validated Label objects

    Raises:
        FileNotFoundError: If the file does not exist
        yaml.YAMLError: If the YAML is invalid
        pydantic.ValidationError: If a label definition is malformed
                                   (e.g. missing required 'match' field)
    """
    path = Path(labels_path)
    if not path.exists():
        raise FileNotFoundError(f"Labels file not found: {path}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    labels = []
    for category, items in raw.items():
        for item in items:
            labels.append(Label(category=category, **item))
    logger.debug("Loaded %d labels from %s", len(labels), path)
    return labels


# +---------------------------------------------------
# Matching
# +---------------------------------------------------
def _matches(row: pd.Series, label: Label) -> bool:
    """
    Check whether a single row matches a label's rules.

    Args:
        row: DataFrame row as a Series
        label: Label to check against

    Returns:
        True if the row matches according to the label's match strategy
    """
    results = [
        bool(re.search(rule.regex, str(row.get(rule.field) or "")))
        for rule in label.rules
    ]
    return any(results) if label.match == "any" else all(results)


def _find_label(row: pd.Series, labels: list[Label]) -> tuple[Optional[str], Optional[str]]:
    """
    Find the first matching label for a row.

    Args:
        row: DataFrame row as a Series
        labels: Ordered list of labels to check (first match wins)

    Returns:
        Tuple of (category, name) or (None, None) if no match
    """
    for label in labels:
        if _matches(row, label):
            return label.category, label.name
    return None, None


# +---------------------------------------------------
# Auto labeling
# +---------------------------------------------------
def apply_labels(df: pd.DataFrame, labels: list[Label]) -> pd.DataFrame:
    """
    Apply label rules to a preprocessed transactions DataFrame.

    Adds two new columns:
        label    - top-level category (e.g. 'lebensmittel')
        sublabel - specific label name (e.g. 'lidl')

    First matching label wins. Rows with no match get None for both columns.
    Fields referenced in rules are validated against DataFrame columns upfront.

    Args:
        df: Preprocessed transactions DataFrame
        labels: List of Label objects (from load_labels)

    Returns:
        New DataFrame with 'label' and 'sublabel' columns appended

    Raises:
        ValueError: If a rule references a column that doesn't exist in df
    """
    # + --- Validate fields -----------------------------------
    valid_fields = set(df.columns)
    for label in labels:
        for rule in label.rules:
            if rule.field not in valid_fields:
                raise ValueError(
                    f"Label '{label.category}/{label.name}': "
                    f"unknown field '{rule.field}'. "
                    f"Valid fields: {sorted(valid_fields)}"
                )

    # + --- Apply rules ---------------------------------------
    logger.info("Applying %d labels to %d transactions", len(labels), len(df))
    df = df.copy()
    results = df.apply(lambda row: _find_label(row, labels), axis=1)
    df["label"] = results.apply(lambda x: x[0])
    df["sublabel"] = results.apply(lambda x: x[1])

    matched = df["label"].notna().sum()
    logger.info(
        "Labeled %d/%d transactions (%.1f%%)",
        matched,
        len(df),
        100 * matched / len(df) if len(df) else 0,
    )
    logger.debug("label distribution: %s", df["label"].value_counts().to_dict())
    return df


# +---------------------------------------------------
# Manual labeling
# +---------------------------------------------------
def apply_manual_labels(
    df: pd.DataFrame,
    manual_labels_path: Path | str,
) -> pd.DataFrame:
    """
    Apply manual labels from an Excel file, overriding auto-generated labels.

    Manual labels take precedence over labels from apply_labels(). This allows
    one-off transactions to be labeled without adding rules to labels.yaml.

    The Excel file must have columns: id, label, sublabel.
    Rows with an id not found in df are logged as warnings and skipped.
    If the file does not exist or is empty, df is returned unchanged.

    Args:
        df: Labeled transactions DataFrame (output of apply_labels)
        manual_labels_path: Path to manual_labels.xlsx

    Returns:
        New DataFrame with manual labels applied
    """
    path = Path(manual_labels_path)

    # + --- Guard clauses -------------------------------------
    if not path.exists():
        logger.warning("manual_labels file not found: %s — skipping", path)
        return df
    manual = pd.read_excel(path)
    if manual.empty:
        logger.info("manual_labels is empty — skipping")
        return df

    # + --- Apply overrides -----------------------------------
    logger.info("Applying %d manual labels", len(manual))
    df = df.copy()
    n_applied = 0
    for _, row in manual.iterrows():
        mask = df["id"] == row["id"]
        if not mask.any():
            logger.warning("manual_labels: id '%s' not found in transactions — skipping", row["id"])
            continue
        df.loc[mask, "label"] = row["label"]
        df.loc[mask, "sublabel"] = row["sublabel"]
        n_applied += 1

    logger.info("Applied %d/%d manual labels", n_applied, len(manual))
    return df
