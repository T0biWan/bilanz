"""Tests for src.preprocess."""

import pandas as pd
import pytest

from src.preprocess import (
    CATEGORIES,
    DEPOT_PATTERNS,
    OUTPUT_COLUMNS,
    categorize_transaction,
    classify_account,
    is_depot_transaction,
    normalize_iban,
    preprocess_transactions,
)


# +---------------------------------------------------
# normalize_iban
# +---------------------------------------------------
class TestNormalizeIban:
    def test_with_spaces(self):
        """Whitespace is removed."""
        assert normalize_iban("DE69 1203 0000 1016 4564 59") == "DE69120300001016456459"

    def test_lowercase(self):
        """Lowercase is converted to uppercase."""
        assert normalize_iban("de69120300001016456459") == "DE69120300001016456459"

    def test_mixed_case(self):
        """Mixed case is normalized."""
        assert normalize_iban("De69120300001016456459") == "DE69120300001016456459"

    def test_none(self):
        """None returns None."""
        assert normalize_iban(None) is None

    def test_nan(self):
        """NaN values return None."""
        assert normalize_iban(pd.NA) is None
        assert normalize_iban(float("nan")) is None

    def test_empty_string(self):
        """Empty string stays empty."""
        assert normalize_iban("") == ""

    def test_idempotent(self):
        """Already normalized IBANs are not changed."""
        iban = "DE69120300001016456459"
        assert normalize_iban(iban) == iban


# +---------------------------------------------------
# classify_account
# +---------------------------------------------------
class TestClassifyAccount:
    @pytest.mark.parametrize("iban,expected", [
        ("DE69120300001016456459", "fixkonto"),
        ("DE17100110012621473008", "flexkonto"),
        ("506508407", "depot"),
    ])
    def test_known_iban(self, mini_accounts, iban, expected):
        """Known IBANs are classified correctly."""
        assert classify_account(iban, mini_accounts) == expected

    def test_external(self, mini_accounts):
        """Unknown IBAN returns 'external'."""
        assert classify_account("DE99999999999999999999", mini_accounts) == "external"

    def test_none(self, mini_accounts):
        """None returns 'external'."""
        assert classify_account(None, mini_accounts) == "external"

    def test_with_spaces_via_normalize(self, mini_accounts):
        """IBANs with spaces work correctly after normalize_iban."""
        assert classify_account(normalize_iban("DE69 1203 0000 1016 4564 59"), mini_accounts) == "fixkonto"

    def test_lowercase_via_normalize(self, mini_accounts):
        """Lowercase IBANs work correctly after normalize_iban."""
        assert classify_account(normalize_iban("de69120300001016456459"), mini_accounts) == "fixkonto"

    def test_all_real_accounts(self, real_accounts):
        """Every account from the real config is classified correctly."""
        for iban, expected_name in real_accounts.items():
            result = classify_account(normalize_iban(iban), real_accounts)
            assert result == expected_name, f"Failed for {iban} -> expected {expected_name}, got {result}"


# +---------------------------------------------------
# categorize_transaction
# +---------------------------------------------------
class TestCategorizeTransaction:
    def test_income(self, mini_savings):
        """betrag>0 + own referenz + external counterparty = income (e.g. salary)."""
        assert categorize_transaction("fixkonto", "external", 3919.88, mini_savings) == "income"

    def test_income_external_to_savings(self, mini_savings):
        """betrag>0 + savings referenz + external counterparty = income (e.g. interest)."""
        assert categorize_transaction("depot", "external", 12.50, mini_savings) == "income"

    def test_expense(self, mini_savings):
        """betrag<0 + own referenz + external counterparty = expense (e.g. groceries)."""
        assert categorize_transaction("fixkonto", "external", -50.00, mini_savings) == "expense"

    def test_expense_from_paypal(self, mini_savings):
        """betrag<0 + paypal referenz + external counterparty = expense."""
        assert categorize_transaction("paypal", "external", -29.99, mini_savings) == "expense"

    def test_savings_from_sender_perspective(self, mini_savings):
        """betrag<0 + non-savings referenz + savings counterparty = savings."""
        assert categorize_transaction("fixkonto", "depot", -500.00, mini_savings) == "savings"

    def test_savings_from_receiver_perspective(self, mini_savings):
        """betrag>0 + savings referenz + non-savings counterparty = savings."""
        assert categorize_transaction("depot", "fixkonto", 500.00, mini_savings) == "savings"

    def test_unsavings_from_sender_perspective(self, mini_savings):
        """betrag<0 + savings referenz + non-savings counterparty = unsavings."""
        assert categorize_transaction("depot", "fixkonto", -200.00, mini_savings) == "unsavings"

    def test_unsavings_from_receiver_perspective(self, mini_savings):
        """betrag>0 + non-savings referenz + savings counterparty = unsavings."""
        assert categorize_transaction("fixkonto", "depot", 200.00, mini_savings) == "unsavings"

    def test_savings_transfer(self, mini_savings):
        """savings -> savings = savings_transfer."""
        assert categorize_transaction("depot", "sparkonto", -300.00, mini_savings) == "savings_transfer"

    def test_internal_transfer_sender(self, mini_savings):
        """betrag<0 + own non-savings + own non-savings = internal_transfer."""
        assert categorize_transaction("fixkonto", "flexkonto", -100.00, mini_savings) == "internal_transfer"

    def test_internal_transfer_receiver(self, mini_savings):
        """betrag>0 + own non-savings + own non-savings = internal_transfer."""
        assert categorize_transaction("flexkonto", "fixkonto", 100.00, mini_savings) == "internal_transfer"

    def test_unknown_zero_betrag(self, mini_savings):
        """betrag=0 = unknown."""
        assert categorize_transaction("fixkonto", "external", 0.0, mini_savings) == "unknown"

    @pytest.mark.parametrize("von,zu,betrag", [
        ("fixkonto", "external",  3919.88),   # income
        ("fixkonto", "external",   -50.00),   # expense
        ("fixkonto", "depot",     -500.00),   # savings
        ("depot",    "fixkonto",   500.00),   # savings
        ("depot",    "fixkonto",  -200.00),   # unsavings
        ("fixkonto", "depot",      200.00),   # unsavings
        ("depot",    "sparkonto", -300.00),   # savings_transfer
        ("fixkonto", "flexkonto", -100.00),   # internal_transfer
    ])
    def test_always_returns_valid_category(self, mini_savings, von, zu, betrag):
        """categorize_transaction always returns a value from CATEGORIES."""
        assert categorize_transaction(von, zu, betrag, mini_savings) in CATEGORIES


# +---------------------------------------------------
# is_depot_transaction
# +---------------------------------------------------
class TestIsDepotTransaction:
    def test_detects_wertp_abrechn(self):
        """Detects standard ETF Sparplan transaction."""
        vz = "Depot 0506508407 Wertp.Abrechn. 01.04.2026 WKN A3DN5J HSBC ETF- WORLD DLA"
        assert is_depot_transaction(vz, DEPOT_PATTERNS) is True

    def test_detects_kap_massnahmen(self):
        """Detects Kapitalmaßnahmen (e.g. fund mergers) on depot."""
        vz = "Depot 0506508407 Kap.Massnahmen 26.02.2025 WKN LYX0YD"
        assert is_depot_transaction(vz, DEPOT_PATTERNS) is True

    def test_detects_any_depot_transaction(self):
        """Matches any transaction starting with the depot number."""
        assert is_depot_transaction("Depot 0506508407 SomeOtherType", DEPOT_PATTERNS) is True

    def test_does_not_match_other_depot_number(self):
        """Does not match a different depot number."""
        assert is_depot_transaction("Depot 9999999999 Wertp.Abrechn.", DEPOT_PATTERNS) is False

    def test_does_not_match_regular_expense(self):
        """Regular expense is not detected as depot transaction."""
        assert is_depot_transaction("Lastschrift Lidl Sagt Danke", DEPOT_PATTERNS) is False

    def test_does_not_match_salary(self):
        """Salary is not detected as depot transaction."""
        assert is_depot_transaction("Lohn-/Gehaltzahlung 6/2026", DEPOT_PATTERNS) is False

    def test_none_returns_false(self):
        """None Verwendungszweck returns False."""
        assert is_depot_transaction(None, DEPOT_PATTERNS) is False

    def test_empty_patterns_returns_false(self):
        """Empty patterns list always returns False."""
        vz = "Depot 0506508407 Wertp.Abrechn."
        assert is_depot_transaction(vz, []) is False


# +---------------------------------------------------
# preprocess_transactions (E2E)
# +---------------------------------------------------
class TestPreprocessTransactions:
    def test_output_columns(self, example_excel_path, real_accounts, real_savings_accounts):
        """Output has exactly 11 columns in the correct order."""
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        assert list(df.columns) == OUTPUT_COLUMNS

    def test_monat_format(self, example_excel_path, real_accounts, real_savings_accounts):
        """monat column follows YYYY-MM format."""
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        for monat in df["monat"].dropna():
            jahr, mon = monat.split("-")
            assert len(jahr) == 4 and jahr.isdigit()
            assert len(mon) == 2 and mon.isdigit()

    def test_buchungstag_has_no_time(self, example_excel_path, real_accounts, real_savings_accounts):
        """buchungstag has no time component."""
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        for ts in pd.to_datetime(df["buchungstag"]).dropna():
            assert ts.hour == 0 and ts.minute == 0 and ts.second == 0

    def test_iban_normalization(self, example_excel_path, real_accounts, real_savings_accounts):
        """Output IBANs contain no whitespace and are uppercase."""
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        for col in ("von_iban", "zu_iban"):
            for iban in df[col].dropna():
                assert " " not in iban
                assert iban == iban.upper()

    def test_account_classification_valid(self, example_excel_path, real_accounts, real_savings_accounts):
        """von_konto and zu_konto only contain known account names or 'external'."""
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        valid = set(real_accounts.values()) | {"external"}
        assert set(df["von_konto"]).issubset(valid)
        assert set(df["zu_konto"]).issubset(valid)

    def test_kategorie_valid(self, example_excel_path, real_accounts, real_savings_accounts):
        """kategorie only contains valid category values."""
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        assert set(df["kategorie"]).issubset(CATEGORIES)

    def test_row_count_preserved(self, example_excel_path, real_accounts, real_savings_accounts):
        """Row count is unchanged (no data lost)."""
        input_rows = len(pd.read_excel(example_excel_path))
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        assert len(df) == input_rows

    def test_betrag_preserved(self, example_excel_path, real_accounts, real_savings_accounts):
        """Betrag values are unchanged."""
        input_df = pd.read_excel(example_excel_path)
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        pd.testing.assert_series_equal(
            input_df["Betrag"].reset_index(drop=True),
            df["betrag"].reset_index(drop=True),
            check_names=False,
        )

    def test_returns_dataframe(self, example_excel_path, real_accounts, real_savings_accounts):
        """Function returns a DataFrame."""
        result = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == OUTPUT_COLUMNS

    def test_id_is_unique(self, example_excel_path, real_accounts, real_savings_accounts):
        """id column contains unique values (no duplicate transactions)."""
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        assert df["id"].is_unique

    def test_edge_cases_present(self, example_excel_path, real_accounts, real_savings_accounts):
        """Fixture covers edge cases: known accounts, external, multiple months."""
        df = preprocess_transactions(example_excel_path, real_accounts, real_savings_accounts)
        assert "fixkonto" in df["von_konto"].values
        assert "external" in df["von_konto"].values
        assert "external" in df["zu_konto"].values
        assert df["monat"].nunique() >= 2
