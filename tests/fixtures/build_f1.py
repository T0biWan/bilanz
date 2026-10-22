"""Baut die F1-Testdaten (tests/fixtures/f1_*.xlsx) im exakten Finanzguru-Format.

Aufruf:  python tests/fixtures/build_f1.py
Die Fälle sind in docs/features/F1-import.md beschrieben.
"""

import hashlib
from datetime import datetime as dt
from pathlib import Path

from openpyxl import Workbook

HIER = Path(__file__).parent

# Kopfzeile exakt wie im Finanzguru-Export
SPALTEN = [
    "Buchungstag", "Referenzkonto", "Name Referenzkonto", "Betrag", "Kontostand",
    "Waehrung", "Beguenstigter/Auftraggeber", "IBAN Beguenstigter/Auftraggeber",
    "Verwendungszweck", "E-Ref", "Mandatsreferenz", "Glaeubiger-ID",
    "Analyse-Hauptkategorie", "Analyse-Unterkategorie", "Analyse-Vertrag",
    "Analyse-Vertragsturnus", "Analyse-Vertrags-ID", "Analyse-Umbuchung",
    "Analyse-Vom frei verfuegbaren Einkommen ausgeschlossen", "Analyse-Umsatzart",
    "Analyse-Betrag", "Analyse-Woche", "Analyse-Monat", "Analyse-Quartal",
    "Analyse-Jahr", "Buchungs-ID", "Referenz-Original-ID", "Split-Typ", "Tags", "Notiz",
]

GIRO = "DE00111111111111111111"
SPAR = "DE00222222222222222222"
PAYPAL = "ID_PAYPALTEST"
KONTONAMEN = {GIRO: "Girokonto", SPAR: "Sparkonto", PAYPAL: "PayPal"}


def buchungs_id(label: str) -> str:
    return hashlib.sha1(f"f1:{label}".encode()).hexdigest()


def zeile(label, konto, tag, betrag, kontostand, gegenpartei, *, gegen_iban=None,
          zweck=None, umsatzart="Kartenzahlung", umbuchung="nein", split=None, original=None):
    jahr, woche, _ = tag.isocalendar()
    return {
        "_label": label,
        "Buchungstag": tag,
        "Referenzkonto": konto,
        "Name Referenzkonto": KONTONAMEN[konto],
        "Betrag": betrag,
        "Kontostand": kontostand,
        "Waehrung": "EUR",
        "Beguenstigter/Auftraggeber": gegenpartei,
        "IBAN Beguenstigter/Auftraggeber": gegen_iban,
        "Verwendungszweck": zweck,
        "Analyse-Hauptkategorie": "Sonstiges",
        "Analyse-Unterkategorie": "Sonstige Ausgaben" if betrag < 0 else "Sonstige Einnahmen",
        "Analyse-Vertrag": "nein",
        "Analyse-Umbuchung": umbuchung,
        "Analyse-Vom frei verfuegbaren Einkommen ausgeschlossen": "nein",
        "Analyse-Umsatzart": umsatzart,
        "Analyse-Betrag": "Ausgaben" if betrag < 0 else "Einnahmen",
        "Analyse-Woche": f"{jahr}-{woche:02d}",
        "Analyse-Monat": f"{tag.year}-{tag.month:02d}",
        "Analyse-Quartal": f"{tag.year}-Q{(tag.month - 1) // 3 + 1}",
        "Analyse-Jahr": float(tag.year),
        "Buchungs-ID": buchungs_id(label),
        "Referenz-Original-ID": buchungs_id(original) if original else None,
        "Split-Typ": split,
    }


AMAZON_ZWECK = "302-1234567-7654321 Amazon.de"
BAECKER_ZWECK = "Brötchen & Kaffee – 2× 1,75 €"

# Reihenfolge wie im Export: neueste zuerst. Kommentar = Excel-Zeile.
OK = [
    zeile("auto", GIRO, dt(2026, 10, 2), -15000.00, -219.55, "Autohaus",           # 2
          gegen_iban="DE00333333333333333333", zweck="Kaufvertrag Fahrzeug", umsatzart="Ueberweisung"),
    zeile("pp_aufladung", PAYPAL, dt(2026, 10, 1, 0, 0, 1), 59.99, 0, "Steam Games",  # 3
          zweck="Automatische Aufladung", umsatzart=None, umbuchung="ja"),
    zeile("steuer", GIRO, dt(2026, 10, 1), 12345.67, 14780.45, "Finanzamt",          # 4
          gegen_iban="DE00444444444444444444", zweck="Erstattung Einkommensteuer 2025",
          umsatzart="Ueberweisung"),
    zeile("pp_steam", PAYPAL, dt(2026, 9, 30, 23, 59, 59), -59.99, -59.99,            # 5
          "Steam Games", umsatzart="Sonstige"),
    zeile("abschluss", GIRO, dt(2026, 9, 30), 0.00, 2434.78, "Bank",                  # 6
          zweck="Rechnungsabschluss 30.09.2026", umsatzart="Zinsen/Entgelt"),
    zeile("kiosk2", GIRO, dt(2026, 9, 15), -0.20, 2434.78, "Kiosk"),                  # 7
    zeile("kiosk1", GIRO, dt(2026, 9, 15), -0.10, 2434.98, "Kiosk"),                  # 8
    zeile("amazon", GIRO, dt(2026, 9, 10), -107.91, 2435.08, "Amazon",                # 9
          zweck=AMAZON_ZWECK, umsatzart="SEPA-Lastschrift", split="Original"),
    zeile("amazon_teil", GIRO, dt(2026, 9, 10), -50.92, 2435.08, "Amazon",            # 10
          zweck=AMAZON_ZWECK, umsatzart="SEPA-Lastschrift", split="Teilbuchung", original="amazon"),
    zeile("amazon_rest", GIRO, dt(2026, 9, 10), -56.99, 2486.00, "Amazon",            # 11
          zweck=AMAZON_ZWECK, umsatzart="SEPA-Lastschrift", split="Restbetrag", original="amazon"),
    zeile("baecker2", GIRO, dt(2026, 9, 3), -3.50, 2542.99, "Bäckerei Körner",        # 12
          zweck=BAECKER_ZWECK),
    zeile("baecker1", GIRO, dt(2026, 9, 3), -3.50, 2546.49, "Bäckerei Körner",        # 13
          zweck=BAECKER_ZWECK),
    zeile("edeka", GIRO, dt(2026, 9, 3), -0.01, 2549.99, "EDEKA"),                    # 14
    zeile("miete", GIRO, dt(2026, 9, 2), -950.00, 2550.00, "Hausverwaltung",          # 15
          gegen_iban="DE00555555555555555555", zweck="Miete September", umsatzart="Dauerauftrag"),
    zeile("gehalt", GIRO, dt(2026, 9, 1), 2500, 3500.00, "Arbeitgeber GmbH",          # 16
          gegen_iban="DE00666666666666666666", zweck="Gehalt September 2026", umsatzart="Ueberweisung"),
    zeile("zinsen", SPAR, dt(2026, 9, 1), 1.23, 501.23, "Bank",                       # 17
          zweck="Zinsen", umsatzart="Zinsen/Entgelt"),
]


def aendere(zeilen, label, felder):
    """Kopie der Zeilen, in der die Zeile `label` die angegebenen Felder bekommt."""
    return [{**z, **felder} if z["_label"] == label else z for z in zeilen]


def schreibe(name, zeilen, spalten=SPALTEN):
    wb = Workbook()
    ws = wb.active
    ws.title = "20261022_Export_Alle_Buchungen"
    ws.append(spalten)
    for z in zeilen:
        ws.append([z.get(s) for s in spalten])
    wb.save(HIER / f"{name}.xlsx")


def main():
    schreibe("f1_ok", OK)
    schreibe("f1_fehlende_spalte", OK, [s for s in SPALTEN if s != "Betrag"])
    schreibe("f1_doppelte_id", aendere(OK, "kiosk1", {"Buchungs-ID": buchungs_id("kiosk2")}))
    schreibe("f1_kontostand_luecke", [z for z in OK if z["_label"] != "miete"])
    schreibe("f1_leer", [])
    schreibe("f1_leeres_pflichtfeld", aendere(OK, "baecker1", {"Betrag": None}))
    schreibe("f1_nachkommastellen", aendere(OK, "baecker1", {"Betrag": -3.505}))
    schreibe("f1_fremdwaehrung", aendere(OK, "pp_steam", {"Waehrung": "USD"}))
    print(f"Fixtures geschrieben nach {HIER}")


if __name__ == "__main__":
    main()
