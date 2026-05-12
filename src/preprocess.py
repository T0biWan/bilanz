"""
Preprocessing module for bank transactions.

Transforms a raw bank Excel export into a clean structure:
- Reduces to relevant columns
- Normalizes IBANs (no whitespace, uppercase)
- Classifies accounts (own accounts vs. external)
- Extracts month as YYYY-MM
- Strips time component from buchungstag
- Categorizes transactions (income, expense, savings, ...)
"""

import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# +---------------------------------------------------
# Constants
# +---------------------------------------------------
# Columns kept from the raw bank export (27 total, rest discarded)
INPUT_COLUMNS = [
    "Buchungs-ID",
    "Buchungstag",
    "Referenzkonto",
    "IBAN Beguenstigter/Auftraggeber",
    "Betrag",
    "Verwendungszweck",
    "Beguenstigter/Auftraggeber",
]
# Final output column order (all lowercase)
OUTPUT_COLUMNS = [
    "id",
    "buchungstag",
    "monat",
    "von_konto",
    "von_iban",
    "zu_konto",
    "zu_iban",
    "betrag",
    "verwendungszweck",
    "beguenstigter",
    "kategorie",
]
# Valid kategorie values
CATEGORIES = {
    "income",
    "expense",
    "savings",
    "unsavings",
    "savings_transfer",
    "internal_transfer",
    "unknown",
}
# Regex patterns matched against Verwendungszweck to detect depot/ETF purchases.
# DKB provides no destination IBAN for securities transactions, so these would
# otherwise be miscategorized as 'expense'. Patterns are specific to depot 0506508407.
DEPOT_PATTERNS = [
    r"^Depot 0506508407",
]


# +---------------------------------------------------
# Normalization
# +---------------------------------------------------
def normalize_iban(iban) -> Optional[str]:
    """
    Normalize an IBAN: remove whitespace and convert to uppercase.

    Args:
        iban: IBAN as string, None, or NaN

    Returns:
        Normalized IBAN string, or None if input is NaN/None
    """
    if pd.isna(iban):
        return None
    return str(iban).replace(" ", "").upper()


# +---------------------------------------------------
# Classification
# +---------------------------------------------------
def classify_account(iban: Optional[str], accounts: dict[str, str]) -> str:
    """
    Classify an IBAN as a known account name or 'external'.

    Compares the (already normalized) IBAN against account identifiers
    from the config, normalizing them as well to handle whitespace/casing.

    Args:
        iban: Already normalized IBAN (or None)
        accounts: Dict mapping IBAN/identifier -> account name

    Returns:
        Account name from accounts dict, or 'external' if not found
    """
    if not iban:
        return "external"
    for account_iban, name in accounts.items():
        if normalize_iban(account_iban) == iban:
            return name
    return "external"


# +---------------------------------------------------
# Depot detection
# +---------------------------------------------------
def is_depot_transaction(verwendungszweck: Optional[str], depot_patterns: list[str]) -> bool:
    """
    Check if a transaction is a depot/ETF purchase based on Verwendungszweck.

    DKB does not provide a destination IBAN for securities transactions, so
    these appear as expense (own -> external) but should be treated as savings.
    Detection is based on regex patterns configured in config.yaml.

    Args:
        verwendungszweck: Transaction description field
        depot_patterns: List of regex patterns to match against

    Returns:
        True if any pattern matches
    """
    if not verwendungszweck or not depot_patterns:
        return False
    return any(re.search(pattern, str(verwendungszweck)) for pattern in depot_patterns)


# +---------------------------------------------------
# Categorization
# +---------------------------------------------------
def categorize_transaction(
    von_konto: str,
    zu_konto: str,
    betrag: float,
    savings_accounts: list[str],
) -> str:
    """
    Categorize a transaction based on accounts and amount sign.

    Note: von_konto is always the Referenzkonto (own account on whose statement
    this transaction appears). The actual money flow direction is determined by
    the sign of betrag:
        betrag > 0: money arrived  -> counterparty (zu_konto) was the sender
        betrag < 0: money departed -> counterparty (zu_konto) was the receiver

    Categories:
        income           - external -> own account (salary, freelance, ...)
        expense          - own account -> external (groceries, subscriptions, ...)
        savings          - own (non-savings) -> savings account
        unsavings        - savings account -> own (non-savings)
        savings_transfer - savings account -> savings account
        internal_transfer- own (non-savings) -> own (non-savings)
        unknown          - both external or zero amount (should not occur in practice)

    Args:
        von_konto: Classified Referenzkonto (always own account or 'external')
        zu_konto: Classified counterparty account (or 'external')
        betrag: Transaction amount (positive = received, negative = sent)
        savings_accounts: List of account names that count as savings

    Returns:
        Category string
    """
    if betrag == 0:
        return "unknown"

    # Resolve actual sender and receiver from betrag sign
    if betrag > 0:
        # Money arrived at Referenzkonto: counterparty sent, we received
        actual_from, actual_to = zu_konto, von_konto
    else:
        # Money left Referenzkonto: we sent, counterparty received
        actual_from, actual_to = von_konto, zu_konto

    from_external = actual_from == "external"
    to_external = actual_to == "external"
    from_savings = actual_from in savings_accounts
    to_savings = actual_to in savings_accounts

    if from_external and to_external:
        return "unknown"
    if from_external:
        return "income"
    if to_external:
        return "expense"
    if to_savings and not from_savings:
        return "savings"
    if from_savings and not to_savings:
        return "unsavings"
    if from_savings and to_savings:
        return "savings_transfer"
    return "internal_transfer"


# +---------------------------------------------------
# Pipeline
# +---------------------------------------------------
def preprocess_transactions(
    input_file: Path | str,
    accounts: dict[str, str],
    savings_accounts: list[str],
) -> pd.DataFrame:
    """
    Run the full preprocessing pipeline on a raw bank Excel export.

    Steps:
        1. Load Excel
        2. Reduce to relevant columns
        3. Extract month (YYYY-MM)
        4. Strip time from buchungstag
        5. Normalize IBANs
        6. Classify accounts
        7. Categorize transactions
        8. Override depot/ETF purchases to 'savings' (via DEPOT_PATTERNS)
        9. Rename and reorder columns

    Args:
        input_file: Path to the raw bank Excel
        accounts: Dict mapping IBAN/identifier -> account name
        savings_accounts: List of account names that count as savings

    Returns:
        Cleaned and categorized DataFrame (caller is responsible for saving to excel)
    """
    input_path = Path(input_file)

    # + --- Load ----------------------------------------------
    logger.info("Loading raw Excel: %s", input_path)
    df = pd.read_excel(input_path)
    logger.info("Found %d transactions", len(df))

    # + --- Reduce columns ------------------------------------
    logger.info("Reducing to %d relevant columns", len(INPUT_COLUMNS))
    df = df[INPUT_COLUMNS].copy()

    # + --- Time fields ---------------------------------------
    logger.info("Extracting month and stripping time from buchungstag")
    df["monat"] = pd.to_datetime(df["Buchungstag"]).dt.to_period("M").astype(str)
    df["buchungstag"] = pd.to_datetime(df["Buchungstag"]).dt.date

    # + --- IBAN normalization --------------------------------
    logger.info("Normalizing IBANs")
    df["von_iban"] = df["Referenzkonto"].apply(normalize_iban)
    df["zu_iban"] = df["IBAN Beguenstigter/Auftraggeber"].apply(normalize_iban)

    # + --- Account classification ----------------------------
    logger.info("Classifying accounts")
    df["von_konto"] = df["von_iban"].apply(lambda x: classify_account(x, accounts))
    df["zu_konto"] = df["zu_iban"].apply(lambda x: classify_account(x, accounts))
    logger.debug("von_konto distribution: %s", df["von_konto"].value_counts().to_dict())
    logger.debug("zu_konto distribution: %s", df["zu_konto"].value_counts().to_dict())

    # + --- Categorization ------------------------------------
    logger.info("Categorizing transactions")
    df["kategorie"] = df.apply(
        lambda row: categorize_transaction(
            row["von_konto"], row["zu_konto"], row["Betrag"], savings_accounts
        ),
        axis=1,
    )
    logger.debug("kategorie distribution: %s", df["kategorie"].value_counts().to_dict())

    # + --- Depot transaction override ------------------------
    depot_mask = df["Verwendungszweck"].apply(
        lambda vz: is_depot_transaction(vz, DEPOT_PATTERNS)
    )
    n_overrides = depot_mask.sum()
    df.loc[depot_mask, "kategorie"] = "savings"
    logger.info("Overrode %d transactions to 'savings' (depot pattern match)", n_overrides)

    # + --- Rename & reorder ----------------------------------
    df["id"] = df["Buchungs-ID"]
    df["betrag"] = df["Betrag"]
    df["verwendungszweck"] = df["Verwendungszweck"]
    df["beguenstigter"] = df["Beguenstigter/Auftraggeber"]
    output_df = df[OUTPUT_COLUMNS]

    logger.info(
        "Done - %d transactions across %d months",
        len(output_df),
        output_df["monat"].nunique(),
    )
    return output_df
