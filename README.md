# Finance Bilanz

Tool for processing bank transaction exports into balance sheets with Google Sheets integration.

This repo is built in phases. Current status: **Phase 1 (Preprocessing) complete.**

## Setup

```bash
uv sync
mkdir -p data/0_raw data/1_processed data/2_labeled data/3_bilanz
```

## Usage

For now, invoke directly in Python (CLI comes in a later phase):

```python
from src.config_loader import load_config
from src.label_data import apply_labels, apply_manual_labels, load_labels
from src.preprocess import preprocess_transactions

config = load_config("config/config.yaml")
labels = load_labels("config/labels.yaml")

df = preprocess_transactions(
    input_file="data/0_raw/export.xlsx",
    accounts=config.accounts,
    savings_accounts=config.savings_accounts,
)
df = apply_labels(df, labels)
df = apply_manual_labels(df, "config/manual_labels.xlsx")
df.to_excel("data/2_labeled/transactions.xlsx", index=False)
```

## Tests

```bash
uv run pytest                                   # all tests
uv run pytest tests/test_preprocess.py -v       # preprocess only
uv run pytest -k normalize_iban                 # filter by name
```

## Configuration

`config/config.yaml`:

- `paths`: directories for input/output
- `accounts`: IBAN/identifier → account name (PayPal via email address)
- `savings_accounts`: which accounts count as savings (used in categorization)

### Labeling Workflow

Labels come from two sources, applied in order (manual always wins):

1. **`config/labels.yaml`** — regex rules applied automatically to every run
2. **`config/manual_labels.xlsx`** — hand-curated overrides for one-off transactions

**Typical workflow:**
1. Run the script → inspect `transactions.xlsx`
2. Spot a pattern that repeats → add a rule to `labels.yaml`
3. Spot a one-off transaction → add its `id` + `label` + `sublabel` to `manual_labels.xlsx`
4. Re-run → both sources are applied, manual overrides auto

`config/manual_labels.xlsx` columns: `id`, `label`, `sublabel`

`config/labels.yaml`:

- Hierarchical: top-level key = `label` (e.g. `lebensmittel`), each entry = `sublabel` (e.g. `lidl`)
- Each label requires `name`, `match` (`any`/`all`), and `rules` (list of `field` + `regex`)
- `match: any` — at least one rule must match
- `match: all` — all rules must match (useful for precise multi-field conditions)
- First matching label wins; unmatched rows get `None` for both `label` and `sublabel`

```yaml
lebensmittel:
  - name: lidl
    match: any
    rules:
      - field: beguenstigter
        regex: "(?i)lidl"

  - name: dkb_sparplan        # AND example: both fields must match
    match: all
    rules:
      - field: beguenstigter
        regex: "(?i)dkb"
      - field: verwendungszweck
        regex: "(?i)sparplan"
```

## Architecture Decisions

- **uv** over pip/poetry: faster, modern lockfile handling
- **Typer** for CLI (Phase 6): type-hints, modern
- **Config**: Pydantic model — attribute access (`config.accounts`), automatic type validation and Path conversion
- **Labels hierarchical**: category as YAML top-level key, label rules as list underneath
- **Label rules** use a list of `{field, regex}` pairs per label for maximum flexibility
- **pathlib.Path** throughout instead of os.path
- **logging** instead of print
- **buchungstag** stripped of time component (.dt.date)
- **PayPal** recognized as a regular account via email identifier (no special casing)
- **Unknown IBANs** → classified as `external`
- **Depot/ETF purchases**: detected via `DEPOT_PATTERNS` constant in `preprocess.py` (regex on `Verwendungszweck`, specific to depot `0506508407`), overriding `expense` → `savings` (DKB omits destination IBAN for securities transactions)
- **preprocess + label_data**: pure data transformation functions — both return a DataFrame, caller is responsible for saving (separation of concerns)
- **Categorization**: based on `betrag` sign + account classification — `Referenzkonto` is always the own account, actual direction determined by betrag sign (positive = received, negative = sent)
- **savings accounts**: depot, sparkonto, kapitalkonto, notgroschen (not geteiltes_sparkonto)

### Transaction Categories

#### Why Referenzkonto is always "our" account

In the DKB "Alle Buchungen" export, `Referenzkonto` is always the account on whose statement the transaction appears — never the counterparty. The actual direction of money flow is determined by the **sign of `betrag`**:

- `betrag > 0` — money was **received** by this account (counterparty sent it)
- `betrag < 0` — money was **sent** from this account (counterparty received it)

This means a salary payment appears as:
```
Referenzkonto = fixkonto    (our account, received the money)
IBAN Beguenstigter = Uber   (external sender)
Betrag = +4200.00           (positive = received)
→ Category: income  ✓
```

#### Why every internal transfer appears twice

When money moves between two own accounts (e.g. fixkonto → sparkonto), the export contains **one row per account statement** — so two rows total:

```
Row 1 (fixkonto statement):  Referenzkonto=fixkonto,   Betrag=-1000  → savings
Row 2 (sparkonto statement): Referenzkonto=sparkonto,  Betrag=+1000  → savings
```

Both rows are correctly categorized as `savings` from their respective perspectives. This is intentional — we keep both rows in the data to preserve a complete record of each account's history.

#### Category rules

| Category | Actual money flow | Example |
|---|---|---|
| `income` | external → own account | salary, freelance payment, interest |
| `expense` | own account → external | groceries, subscriptions, rent |
| `savings` | own (non-savings) → savings account | monthly transfer to depot, ETF Sparplan |
| `unsavings` | savings account → own (non-savings) | withdrawal from sparkonto |
| `savings_transfer` | savings account → savings account | rebalancing between depot and notgroschen |
| `internal_transfer` | own (non-savings) → own (non-savings) | moving money between fixkonto and flexkonto |
| `unknown` | zero amount or both external | should not occur in practice |

Own accounts: anything in `accounts` in `config.yaml`. Savings accounts: the subset listed under `savings_accounts` (depot, sparkonto, kapitalkonto, notgroschen — **not** geteiltes_sparkonto).

#### Depot/ETF purchases

DKB provides no destination IBAN for securities transactions. These would otherwise be miscategorized as `expense`. They are detected via `DEPOT_PATTERNS` in `preprocess.py` (regex on `Verwendungszweck`, specific to depot `0506508407`) and overridden to `savings` after the main categorization step.

### Bilanz Calculations

#### Why we use only betrag < 0 (sender perspective)

Since every internal transfer appears twice (once per account), naively summing all `savings` rows would double-count:

```
Row 1: fixkonto → sparkonto,  betrag=-1000  (sender)
Row 2: sparkonto ← fixkonto,  betrag=+1000  (receiver)
Sum = 0  ← wrong, should be 1000
```

Solution: **only aggregate rows where `betrag < 0`** (the sending side). The receiver row is ignored. This is consistently applied for savings, unsavings, expense, and internal transfers.

For `income` and `expense` against external parties: external accounts have no statement in our export, so these never appear twice — the sign filter is applied for consistency.

#### Net savings formula

```
saved   = abs( sum(betrag  where kategorie="savings"   and betrag < 0) )
unsaved = abs( sum(betrag  where kategorie="unsavings" and betrag < 0) )
net     = saved - unsaved
```

`savings_transfer` (e.g. depot → notgroschen) is **excluded** from net savings — the money stays within the savings pool and is simply reallocated, not actually saved or withdrawn.

A **positive** net savings means you saved more than you withdrew that month. A **negative** result means you withdrew more than you put in.
- **Deduplication**: `Buchungs-ID` from the raw export is the stable primary key (`id` in output)
- **Manual labels** never overwritten: `manual_labels.xlsx` is ground truth, auto-labels are always recomputed
- **Test strategy**: hybrid — `mini_accounts` for unit tests, `real_accounts` (from config) for integration/E2E

## Project Structure

```
finance-bilanz/
├── pyproject.toml          # uv project config + pytest settings
├── config/
│   └── config.yaml         # accounts, paths, savings accounts
├── src/
│   ├── config_loader.py    # Pydantic Config model + load_config()
│   └── preprocess.py       # Step 0: clean + normalize raw export
├── tests/
│   ├── conftest.py
│   ├── test_config_loader.py
│   ├── test_preprocess.py
│   └── fixtures/
│       ├── example_config.yaml
│       └── example_raw.xlsx        # fake bank export (15 rows, all edge cases)
└── data/
    ├── 0_raw/              # place bank Excel exports here
    ├── 1_processed/        # intermediate results
    ├── 2_labeled/          # transactions.xlsx
    └── 3_bilanz/           # final Bilanz
```

## Roadmap

- ✅ **Phase 1**: Setup (uv, YAML config) + preprocessing migration
- ✅ **Phase 2**: Categorization (income/expense/savings/...) in preprocessing
- ✅ **Phase 3**: Label system (`labels.yaml`, regex matching, hierarchical)
- ✅ **Phase 4**: Manual labels (`config/manual_labels.xlsx`, overrides auto labels)
- ⏳ **Phase 5**: Bilanz creation — step by step:
  - ✅ Step 1: Income
  - ⏳ Step 2: Expense
  - ⏳ Step 3: Savings
  - ⏳ Step 4: Labeled categories
- ⏳ **Phase 6**: Google Sheets API integration
- ⏳ **Phase 7**: Typer CLI (`run`, `preprocess`, `label`, `bilanz`, `upload`)
- ⏳ **Phase 8**: Workflow for unlabeled transactions (concept open)
