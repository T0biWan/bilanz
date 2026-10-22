"""F1 – Export einlesen. Spezifikation: docs/features/F1-import.md"""

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from bilanz.importer import Buchung, ImportFehler, Warnung, load_export

FIXTURES = Path(__file__).parent / "fixtures"
GIRO = "DE00111111111111111111"
SPAR = "DE00222222222222222222"
PAYPAL = "ID_PAYPALTEST"


def lade(name):
    return load_export(FIXTURES / f"{name}.xlsx")


def nach_zeile(ergebnis):
    return {b.zeile: b for b in ergebnis.buchungen}


@pytest.fixture(scope="module")
def ok():
    return lade("f1_ok")


# --- f1_ok: 14 Buchungen, 0 Warnungen ---------------------------------------

def test_ok_14_buchungen_in_dateireihenfolge(ok):
    assert [b.zeile for b in ok.buchungen] == [2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16, 17]


def test_ok_keine_warnungen(ok):
    assert ok.warnungen == []


def fid(label):
    """Buchungs-ID einer Fixture-Zeile (Regel wie in build_f1.py)."""
    return hashlib.sha1(f"f1:{label}".encode()).hexdigest()


G, P, S = (GIRO, "Girokonto"), (PAYPAL, "PayPal"), (SPAR, "Sparkonto")
AMAZON = "302-1234567-7654321 Amazon.de"
BAECKER = "Brötchen & Kaffee – 2× 1,75 €"

GESAMTERGEBNIS = [  # von Hand geschrieben, NICHT aus der Code-Ausgabe kopiert
    # zeile, label,        konto, datum,              betrag,      gegenpartei,        gegen_iban,               zweck
    (2,  "auto",           G, date(2026, 10, 2),  "-15000.00", "Autohaus",         "DE00333333333333333333", "Kaufvertrag Fahrzeug"),
    (3,  "pp_aufladung",   P, date(2026, 10, 1),  "59.99",     "Steam Games",      None,                     "Automatische Aufladung"),
    (4,  "steuer",         G, date(2026, 10, 1),  "12345.67",  "Finanzamt",        "DE00444444444444444444", "Erstattung Einkommensteuer 2025"),
    (5,  "pp_steam",       P, date(2026, 9, 30),  "-59.99",    "Steam Games",      None,                     None),
    (6,  "abschluss",      G, date(2026, 9, 30),  "0.00",      "Bank",             None,                     "Rechnungsabschluss 30.09.2026"),
    (7,  "kiosk2",         G, date(2026, 9, 15),  "-0.20",     "Kiosk",            None,                     None),
    (8,  "kiosk1",         G, date(2026, 9, 15),  "-0.10",     "Kiosk",            None,                     None),
    (9,  "amazon",         G, date(2026, 9, 10),  "-107.91",   "Amazon",           None,                     AMAZON),
    (12, "baecker2",       G, date(2026, 9, 3),   "-3.50",     "Bäckerei Körner",  None,                     BAECKER),
    (13, "baecker1",       G, date(2026, 9, 3),   "-3.50",     "Bäckerei Körner",  None,                     BAECKER),
    (14, "edeka",          G, date(2026, 9, 3),   "-0.01",     "EDEKA",            None,                     None),
    (15, "miete",          G, date(2026, 9, 2),   "-950.00",   "Hausverwaltung",   "DE00555555555555555555", "Miete September"),
    (16, "gehalt",         G, date(2026, 9, 1),   "2500.00",   "Arbeitgeber GmbH", "DE00666666666666666666", "Gehalt September 2026"),
    (17, "zinsen",         S, date(2026, 9, 1),   "1.23",      "Bank",             None,                     "Zinsen"),
]


def test_ok_gesamtergebnis(ok):
    erwartet = [
        Buchung(zeile=z, id=fid(label), konto=konto, konto_name=name, datum=datum,
                betrag=Decimal(betrag), gegenpartei=gp, gegen_iban=iban, zweck=zweck)
        for z, label, (konto, name), datum, betrag, gp, iban, zweck in GESAMTERGEBNIS
    ]
    assert ok.buchungen == erwartet


ERWARTET = {  # Excel-Zeile: (Konto, Datum, Betrag als String)
    2: (GIRO, date(2026, 10, 2), "-15000.00"),
    3: (PAYPAL, date(2026, 10, 1), "59.99"),
    4: (GIRO, date(2026, 10, 1), "12345.67"),
    5: (PAYPAL, date(2026, 9, 30), "-59.99"),    # 23:59:59 -> bleibt 30.09.
    6: (GIRO, date(2026, 9, 30), "0.00"),        # Nullbetrag bleibt
    7: (GIRO, date(2026, 9, 15), "-0.20"),       # keine Float-Reste
    8: (GIRO, date(2026, 9, 15), "-0.10"),
    9: (GIRO, date(2026, 9, 10), "-107.91"),     # Split-Original
    12: (GIRO, date(2026, 9, 3), "-3.50"),
    13: (GIRO, date(2026, 9, 3), "-3.50"),
    14: (GIRO, date(2026, 9, 3), "-0.01"),
    15: (GIRO, date(2026, 9, 2), "-950.00"),
    16: (GIRO, date(2026, 9, 1), "2500.00"),     # aus int-Zelle
    17: (SPAR, date(2026, 9, 1), "1.23"),
}


@pytest.mark.parametrize("zeile", ERWARTET)
def test_ok_konto_datum_betrag(ok, zeile):
    b = nach_zeile(ok)[zeile]
    konto, datum, betrag = ERWARTET[zeile]
    assert b.konto == konto
    assert type(b.datum) is date and b.datum == datum
    assert type(b.betrag) is Decimal and str(b.betrag) == betrag  # Wert UND 2 Stellen


def test_ok_split_original_bleibt_teile_verworfen(ok):
    zeilen = nach_zeile(ok)
    assert 9 in zeilen
    assert 10 not in zeilen and 11 not in zeilen


def test_ok_echte_doppelbuchung_bleibt(ok):
    a, b = nach_zeile(ok)[12], nach_zeile(ok)[13]
    assert (a.betrag, a.gegenpartei, a.zweck) == (b.betrag, b.gegenpartei, b.zweck)
    assert a.id != b.id


def test_ok_texte_unveraendert_leere_felder_none(ok):
    z = nach_zeile(ok)
    assert z[13].gegenpartei == "Bäckerei Körner"
    assert z[13].zweck == "Brötchen & Kaffee – 2× 1,75 €"
    assert z[14].gegen_iban is None and z[14].zweck is None


def test_ok_summenprobe_giro(ok):
    summe = sum((b.betrag for b in ok.buchungen if b.konto == GIRO), Decimal("0"))
    assert summe == Decimal("-219.55") - Decimal("1000.00")  # Endstand - Anfangsstand


# --- Warnung: Import läuft weiter --------------------------------------------

def test_kontostand_luecke_warnt_und_importiert_trotzdem():
    e = lade("f1_kontostand_luecke")
    assert len(e.buchungen) == 13
    assert e.warnungen == [
        Warnung(konto=GIRO, zeile=14, erwartet=Decimal("3499.99"), gefunden=Decimal("2549.99"))
    ]


def test_leerer_export():
    e = lade("f1_leer")
    assert e.buchungen == [] and e.warnungen == []


# --- Abbruch -----------------------------------------------------------------

@pytest.mark.parametrize("datei, grund, zeilen", [
    ("f1_fehlende_spalte", "fehlende_spalte", []),
    ("f1_doppelte_id", "doppelte_id", [7, 8]),
    ("f1_leeres_pflichtfeld", "leeres_feld", [13]),
    ("f1_nachkommastellen", "ungueltiges_feld", [13]),
    ("f1_fremdwaehrung", "waehrung", [5]),
])
def test_abbruch(datei, grund, zeilen):
    with pytest.raises(ImportFehler) as fehler:
        lade(datei)
    assert fehler.value.grund == grund
    assert fehler.value.zeilen == zeilen


def test_fehlende_spalte_nennt_spalte():
    with pytest.raises(ImportFehler, match="Betrag"):
        lade("f1_fehlende_spalte")
