# bilanz

Monatsbilanz aus Finanzguru-Exporten: Einnahmen, Ausgaben und Sparen pro Monat, kategorisiert.

## Einrichten (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Tests

```
pytest
```

Strukturvergleich der Fixtures mit einem echten Export (der Export bleibt lokal):

```
set BILANZ_EXPORT=daten\20261022-Export-Alle_Buchungen.xlsx
pytest tests/test_fixture_struktur.py
```

Fixtures neu bauen: `python tests\fixtures\build_f1.py`

## Ablauf pro Feature

Jedes Feature hat eine Datei `docs/features/Fx-*.md`. Die Schritte laufen in dieser Reihenfolge:

1. Ziel
2. Testdaten
3. Erwartetes Ergebnis
4. Tests
5. Code

## Daten

- Echte Exporte gehören nach `daten/`. Der Ordner ist per `.gitignore` ausgeschlossen.
- `tools/inspect_export.py` und `tools/anonymize.py` dienen zum Anonymisieren von Beispieldaten.
