"""Tests for src.create_bilanz."""

import pandas as pd
import pytest
from openpyxl import load_workbook

from src.create_bilanz import (
    _aggregate_expense,
    _aggregate_income,
    _aggregate_savings,
    _sorted_months,
    create_bilanz,
    write_bilanz,
)


# +---------------------------------------------------
# Helpers
# +---------------------------------------------------
def make_df(rows: list[dict]) -> pd.DataFrame:
    """Create a minimal transactions DataFrame for tests."""
    defaults = {
        "id": "tx-001",
        "monat": "2026-01",
        "kategorie": "expense",
        "betrag": -50.0,
        "label": None,
        "sublabel": None,
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


# +---------------------------------------------------
# _sorted_months
# +---------------------------------------------------
class TestSortedMonths:
    def test_newest_first(self):
        """Months are returned newest first."""
        df = make_df([
            {"monat": "2025-01"},
            {"monat": "2026-03"},
            {"monat": "2025-06"},
        ])
        assert _sorted_months(df) == ["2026-03", "2025-06", "2025-01"]

    def test_deduplicates(self):
        """Duplicate months appear only once."""
        df = make_df([{"monat": "2026-01"}, {"monat": "2026-01"}, {"monat": "2025-12"}])
        assert len(_sorted_months(df)) == 2


# +---------------------------------------------------
# _aggregate_income
# +---------------------------------------------------
class TestAggregateIncome:
    def test_sums_income_per_month(self):
        """Sums positive income transactions per month."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "income", "betrag": 3000.0},
            {"monat": "2026-01", "kategorie": "income", "betrag": 1200.0},
        ])
        assert _aggregate_income(df)["2026-01"] == pytest.approx(4200.0)

    def test_excludes_non_income(self):
        """Expense and savings transactions are not counted."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "income",  "betrag":  4200.0},
            {"monat": "2026-01", "kategorie": "expense", "betrag": -1000.0},
            {"monat": "2026-01", "kategorie": "savings", "betrag":  -500.0},
        ])
        assert _aggregate_income(df)["2026-01"] == pytest.approx(4200.0)

    def test_excludes_negative_income(self):
        """Negative betrag with kategorie=income is excluded (double-entry)."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "income", "betrag":  4200.0},
            {"monat": "2026-01", "kategorie": "income", "betrag": -4200.0},
        ])
        assert _aggregate_income(df)["2026-01"] == pytest.approx(4200.0)

    def test_month_with_no_income_not_in_result(self):
        """Months with no income are absent from the result."""
        df = make_df([{"monat": "2026-01", "kategorie": "expense", "betrag": -100.0}])
        assert "2026-01" not in _aggregate_income(df)


# +---------------------------------------------------
# _aggregate_expense
# +---------------------------------------------------
class TestAggregateExpense:
    def test_sums_expense_per_month(self):
        """Sums negative expense transactions per month."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "expense", "betrag": -1000.0},
            {"monat": "2026-01", "kategorie": "expense", "betrag":  -500.0},
        ])
        assert _aggregate_expense(df)["2026-01"] == pytest.approx(-1500.0)

    def test_excludes_non_expense(self):
        """Income and savings are not counted."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "expense", "betrag": -1000.0},
            {"monat": "2026-01", "kategorie": "income",  "betrag":  4200.0},
            {"monat": "2026-01", "kategorie": "savings", "betrag":  -500.0},
        ])
        assert _aggregate_expense(df)["2026-01"] == pytest.approx(-1000.0)

    def test_excludes_positive_expense(self):
        """Positive betrag with kategorie=expense is excluded (double-entry)."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "expense", "betrag": -1000.0},
            {"monat": "2026-01", "kategorie": "expense", "betrag":  1000.0},
        ])
        assert _aggregate_expense(df)["2026-01"] == pytest.approx(-1000.0)

    def test_month_with_no_expense_not_in_result(self):
        """Months with no expense are absent from the result."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        assert "2026-01" not in _aggregate_expense(df)


# +---------------------------------------------------
# _aggregate_savings
# +---------------------------------------------------
class TestAggregateSavings:
    def test_net_savings(self):
        """Net savings = savings - unsavings (both sender perspective)."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "savings",   "betrag": -1000.0},
            {"monat": "2026-01", "kategorie": "unsavings", "betrag":  -200.0},
        ])
        assert _aggregate_savings(df)["2026-01"] == pytest.approx(800.0)

    def test_positive_result(self):
        """Result is positive when more saved than withdrawn."""
        df = make_df([{"monat": "2026-01", "kategorie": "savings", "betrag": -500.0}])
        assert _aggregate_savings(df)["2026-01"] > 0

    def test_negative_result_when_more_unsavings(self):
        """Result is negative when more withdrawn than saved."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "savings",   "betrag":  -200.0},
            {"monat": "2026-01", "kategorie": "unsavings", "betrag": -1000.0},
        ])
        assert _aggregate_savings(df)["2026-01"] == pytest.approx(-800.0)

    def test_excludes_double_entry(self):
        """Positive betrag (receiver perspective) is excluded."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "savings", "betrag": -1000.0},
            {"monat": "2026-01", "kategorie": "savings", "betrag":  1000.0},
        ])
        assert _aggregate_savings(df)["2026-01"] == pytest.approx(1000.0)

    def test_only_sender_savings_counted(self):
        """
        Simulates a real transfer: fixkonto→sparkonto appears as two rows.
        Only the sender row (betrag=-1000) must be counted, not the receiver
        row (betrag=+1000), otherwise the result would be 0 instead of 1000.
        """
        df = make_df([
            # Sender perspective: fixkonto statement, money leaving
            {"monat": "2026-01", "kategorie": "savings", "betrag": -1000.0},
            # Receiver perspective: sparkonto statement, money arriving
            {"monat": "2026-01", "kategorie": "savings", "betrag":  1000.0},
        ])
        result = _aggregate_savings(df)["2026-01"]
        assert result == pytest.approx(1000.0), (
            "Double-entry detected: receiver perspective must be excluded"
        )

    def test_only_sender_unsavings_counted(self):
        """
        Simulates a real withdrawal: sparkonto→fixkonto appears as two rows.
        Only the sender row (betrag=-500) must be counted, not the receiver
        row (betrag=+500), otherwise unsavings would be overstated.
        """
        df = make_df([
            # Sender perspective: sparkonto statement, money leaving
            {"monat": "2026-01", "kategorie": "unsavings", "betrag": -500.0},
            # Receiver perspective: fixkonto statement, money arriving
            {"monat": "2026-01", "kategorie": "unsavings", "betrag":  500.0},
        ])
        df_savings = make_df([
            {"monat": "2026-01", "kategorie": "savings", "betrag": -1000.0},
        ])
        df_combined = pd.concat([df, df_savings], ignore_index=True)
        result = _aggregate_savings(df_combined)["2026-01"]
        assert result == pytest.approx(500.0), (
            "Double-entry detected: receiver perspective of unsavings must be excluded"
        )

    def test_includes_depot_savings(self):
        """Depot/ETF purchases (kategorie=savings) are included."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "savings", "betrag": -701.5},
        ])
        assert _aggregate_savings(df)["2026-01"] == pytest.approx(701.5)

    def test_month_with_no_savings_not_in_result(self):
        """Months with no savings activity are absent from the result."""
        df = make_df([{"monat": "2026-01", "kategorie": "expense", "betrag": -100.0}])
        assert "2026-01" not in _aggregate_savings(df)


# +---------------------------------------------------
# create_bilanz
# +---------------------------------------------------
class TestCreateBilanz:
    def test_returns_dataframe(self):
        """Returns a DataFrame."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        result = create_bilanz(df)
        assert isinstance(result, pd.DataFrame)

    def test_months_as_columns_newest_first(self):
        """Columns are months sorted newest first."""
        df = make_df([
            {"monat": "2025-01", "kategorie": "income", "betrag": 1000.0},
            {"monat": "2026-03", "kategorie": "income", "betrag": 2000.0},
        ])
        result = create_bilanz(df)
        assert list(result.columns) == ["2026-03", "2025-01"]

    def test_income_row_exists(self):
        """Overview has an 'income' row."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        assert "income" in create_bilanz(df).index

    def test_expense_row_exists(self):
        """Overview has an 'expense' row."""
        df = make_df([{"monat": "2026-01", "kategorie": "expense", "betrag": -1000.0}])
        assert "expense" in create_bilanz(df).index

    def test_savings_row_exists(self):
        """Overview has a 'savings' row."""
        df = make_df([{"monat": "2026-01", "kategorie": "savings", "betrag": -500.0}])
        assert "savings" in create_bilanz(df).index

    def test_savings_values_positive(self):
        """Net savings values are positive."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "savings",   "betrag": -1000.0},
            {"monat": "2026-01", "kategorie": "unsavings", "betrag":  -200.0},
        ])
        assert create_bilanz(df).loc["savings", "2026-01"] == pytest.approx(800.0)

    def test_month_with_no_savings_shows_zero(self):
        """Months with no savings show 0."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        assert create_bilanz(df).loc["savings", "2026-01"] == pytest.approx(0.0)

    def test_expense_values_negative(self):
        """Expense values are negative."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "expense", "betrag": -1000.0},
            {"monat": "2026-01", "kategorie": "expense", "betrag":  -500.0},
        ])
        assert create_bilanz(df).loc["expense", "2026-01"] == pytest.approx(-1500.0)

    def test_month_with_no_expense_shows_zero(self):
        """Months with no expense show 0."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "income",  "betrag":  4200.0},
            {"monat": "2025-12", "kategorie": "expense", "betrag": -1000.0},
        ])
        assert create_bilanz(df).loc["expense", "2026-01"] == pytest.approx(0.0)

    def test_income_values_correct(self):
        """Income values match aggregated totals."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "income", "betrag": 3000.0},
            {"monat": "2026-01", "kategorie": "income", "betrag": 1200.0},
            {"monat": "2025-12", "kategorie": "income", "betrag": 4100.0},
        ])
        result = create_bilanz(df)
        assert result.loc["income", "2026-01"] == pytest.approx(4200.0)
        assert result.loc["income", "2025-12"] == pytest.approx(4100.0)

    def test_month_with_no_income_shows_zero(self):
        """Months with no income show 0."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "income",  "betrag":  4200.0},
            {"monat": "2025-12", "kategorie": "expense", "betrag": -100.0},
        ])
        result = create_bilanz(df)
        assert result.loc["income", "2025-12"] == pytest.approx(0.0)

    def test_input_df_not_mutated(self):
        """Input DataFrame is not modified."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        original_cols = list(df.columns)
        create_bilanz(df)
        assert list(df.columns) == original_cols


# +---------------------------------------------------
# write_bilanz
# +---------------------------------------------------
class TestWriteBilanz:
    def test_creates_output_file(self, tmp_path):
        """Output file is created."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        out = tmp_path / "bilanz.xlsx"
        write_bilanz(create_bilanz(df), out)
        assert out.exists()

    def test_creates_parent_dirs(self, tmp_path):
        """Creates parent directories if they don't exist."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        out = tmp_path / "nested" / "bilanz.xlsx"
        write_bilanz(create_bilanz(df), out)
        assert out.exists()

    def test_uebersicht_sheet_exists(self, tmp_path):
        """Workbook contains an 'Übersicht' sheet."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        out = tmp_path / "bilanz.xlsx"
        write_bilanz(create_bilanz(df), out)
        assert "Übersicht" in load_workbook(out).sheetnames

    def test_top_left_label_is_monat(self, tmp_path):
        """Top-left cell says 'Monat'."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        out = tmp_path / "bilanz.xlsx"
        write_bilanz(create_bilanz(df), out)
        ws = load_workbook(out)["Übersicht"]
        assert ws.cell(row=1, column=1).value == "Monat"

    def test_freeze_panes(self, tmp_path):
        """First row and first column are frozen."""
        df = make_df([{"monat": "2026-01", "kategorie": "income", "betrag": 4200.0}])
        out = tmp_path / "bilanz.xlsx"
        write_bilanz(create_bilanz(df), out)
        ws = load_workbook(out)["Übersicht"]
        assert ws.freeze_panes == "B2"

    def test_months_newest_first_in_excel(self, tmp_path):
        """Month columns are newest first in the Excel output."""
        df = make_df([
            {"monat": "2025-01", "kategorie": "income", "betrag": 1000.0},
            {"monat": "2026-03", "kategorie": "income", "betrag": 2000.0},
        ])
        out = tmp_path / "bilanz.xlsx"
        write_bilanz(create_bilanz(df), out)
        ws = load_workbook(out)["Übersicht"]
        assert ws.cell(row=1, column=2).value == "2026-03"
        assert ws.cell(row=1, column=3).value == "2025-01"

    def test_income_values_in_excel(self, tmp_path):
        """Income values are correctly written to Excel."""
        df = make_df([
            {"monat": "2026-01", "kategorie": "income", "betrag": 3000.0},
            {"monat": "2026-01", "kategorie": "income", "betrag": 1200.0},
        ])
        out = tmp_path / "bilanz.xlsx"
        write_bilanz(create_bilanz(df), out)
        ws = load_workbook(out)["Übersicht"]
        assert ws.cell(row=2, column=2).value == pytest.approx(4200.0)
