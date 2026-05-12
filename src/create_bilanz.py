"""
Bilanz creation module.

Two responsibilities, cleanly separated:
    create_bilanz(df)             - builds and returns overview DataFrame
    write_bilanz(overview, path)  - writes it to a clean formatted Excel file

Overview structure: categories as rows, months as columns (newest first).

Built incrementally:
    Step 1: income
    Step 2: expense        (TODO)
    Step 3: savings        (TODO)
    Step 4: labeled cats   (TODO)
"""

import logging
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)


# +---------------------------------------------------
# Constants
# +---------------------------------------------------
NUMBER_FORMAT = '#,##0.00 "€"'   # German format: 1.234,56 €
FONT_NAME     = "Arial"
FONT_SIZE     = 10


# +---------------------------------------------------
# Helpers
# +---------------------------------------------------
def _sorted_months(df: pd.DataFrame) -> list[str]:
    """Return all months in the DataFrame sorted newest first."""
    return sorted(df["monat"].dropna().unique(), reverse=True)


def _border_right() -> Border:
    return Border(right=Side(style="thin"))


def _border_bottom() -> Border:
    return Border(bottom=Side(style="thin"))


def _border_corner() -> Border:
    return Border(right=Side(style="thin"), bottom=Side(style="thin"))


# +---------------------------------------------------
# Aggregations
# +---------------------------------------------------
def _aggregate_income(df: pd.DataFrame) -> pd.Series:
    """
    Aggregate income per month.

    Only counts betrag > 0 where kategorie == 'income' to avoid
    double-entry from internal transfers.

    Returns:
        Series with monat as index and summed income as values
    """
    mask = (df["kategorie"] == "income") & (df["betrag"] > 0)
    return df[mask].groupby("monat")["betrag"].sum()


def _aggregate_expense(df: pd.DataFrame) -> pd.Series:
    """
    Aggregate expenses per month.

    Only counts betrag < 0 where kategorie == 'expense' to avoid
    double-entry from internal transfers.

    Returns:
        Series with monat as index and summed expenses as values (negative)
    """
    mask = (df["kategorie"] == "expense") & (df["betrag"] < 0)
    return df[mask].groupby("monat")["betrag"].sum()


def _aggregate_savings(df: pd.DataFrame) -> pd.Series:
    """
    Aggregate net savings per month (savings minus unsavings).

    Uses only sender-perspective rows (betrag < 0) to avoid double-entry.
    Depot/ETF purchases (categorized as 'savings') are included.
    Result is positive: positive = net saved, negative = net withdrawn.

    Returns:
        Series with monat as index and net savings as values
    """
    savings_mask   = (df["kategorie"] == "savings")   & (df["betrag"] < 0)
    unsavings_mask = (df["kategorie"] == "unsavings") & (df["betrag"] < 0)

    savings   = df[savings_mask].groupby("monat")["betrag"].sum().abs()
    unsavings = df[unsavings_mask].groupby("monat")["betrag"].sum().abs()

    return savings.subtract(unsavings, fill_value=0)


# +---------------------------------------------------
# Build
# +---------------------------------------------------
def create_bilanz(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the bilanz overview DataFrame from labeled transactions.

    Structure: categories as rows (index), months as columns (newest first).
    Currently includes: income, expense, savings.

    Args:
        df: Labeled transactions DataFrame (output of apply_manual_labels)

    Returns:
        Overview DataFrame — index=category names, columns=months
    """
    months  = _sorted_months(df)
    income  = _aggregate_income(df)
    expense = _aggregate_expense(df)
    savings = _aggregate_savings(df)

    overview = pd.DataFrame(
        index=["income", "expense", "savings"],
        columns=months,
        dtype=float,
    )
    for monat in months:
        overview.loc["income",  monat] = income.get(monat,  0.0)
        overview.loc["expense", monat] = expense.get(monat, 0.0)
        overview.loc["savings", monat] = savings.get(monat, 0.0)

    logger.info("Built bilanz overview: %d months", len(months))
    return overview


# +---------------------------------------------------
# Write
# +---------------------------------------------------
def write_bilanz(overview: pd.DataFrame, output_path: Path | str) -> None:
    """
    Write the bilanz overview DataFrame to a clean Excel file.

    Formatting:
        - No background colors
        - Bold for header row and label column
        - Thin border right of label column and below header row
        - German number format (1.234,56 €)
        - Freeze panes at B2 (first row + first column fixed)

    Args:
        overview: DataFrame returned by create_bilanz()
        output_path: Path where the bilanz Excel will be saved
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    months = list(overview.columns)
    row_labels = list(overview.index)

    wb = Workbook()
    ws = wb.active
    ws.title = "Übersicht"

    # + --- Header row ------------------------------------
    cell = ws.cell(row=1, column=1, value="Monat")
    cell.font = Font(bold=True, name=FONT_NAME, size=FONT_SIZE)
    cell.alignment = Alignment(horizontal="left")
    cell.border = _border_corner()

    for col_idx, monat in enumerate(months, start=2):
        cell = ws.cell(row=1, column=col_idx, value=monat)
        cell.font = Font(bold=True, name=FONT_NAME, size=FONT_SIZE)
        cell.alignment = Alignment(horizontal="center")
        cell.border = _border_bottom()

    # + --- Data rows -------------------------------------
    for row_idx, label in enumerate(row_labels, start=2):
        cell = ws.cell(row=row_idx, column=1, value=label.capitalize())
        cell.font = Font(bold=True, name=FONT_NAME, size=FONT_SIZE)
        cell.alignment = Alignment(horizontal="left")
        cell.border = _border_right()

        for col_idx, monat in enumerate(months, start=2):
            cell = ws.cell(row=row_idx, column=col_idx, value=overview.loc[label, monat])
            cell.font = Font(name=FONT_NAME, size=FONT_SIZE)
            cell.alignment = Alignment(horizontal="right")
            cell.number_format = NUMBER_FORMAT

    # + --- Column widths ---------------------------------
    ws.column_dimensions["A"].width = 20
    for col_idx in range(2, len(months) + 2):
        ws.column_dimensions[get_column_letter(col_idx)].width = 14

    # + --- Freeze panes ----------------------------------
    ws.freeze_panes = "B2"

    wb.save(output_path)
    logger.info("Saved bilanz: %s", output_path)
