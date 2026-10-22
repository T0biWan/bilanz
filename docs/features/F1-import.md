# F1 – Export einlesen

Status: ✅ fertig. Alle Tests grün. Der echte Export (6.534 Zeilen) ergibt 6.514 Buchungen und 0 Warnungen.
Nachtrag 1: Feld `konto_name` und Test `test_ok_gesamtergebnis`.

## 1. Ziel

bilanz liest einen Finanzguru-Export und liefert eine Liste von Buchungen, auf die man sich verlassen kann.

- Jede Zeile wird eine Buchung: ID, Konto, Kontoname, Datum (nur der Tag), Betrag (exakt als `Decimal`), Gegenpartei, Gegen-IBAN, Verwendungszweck.
- Split-Teile (Teilbuchung, Restbetrag) werden verworfen. Es zählt nur das Original, also die echte Bankbuchung.
- **Abbruch** mit Zeilennummer und Grund bei:
  - fehlender Pflichtspalte
  - doppelter Buchungs-ID
  - leerem oder ungültigem Pflichtfeld (ID, Konto, Datum, Betrag, Kontostand)
  - einer Währung ungleich EUR
- **Warnung** mit Konto und Zeile, wenn pro Konto ein Kontostand nicht zum vorherigen plus Betrag passt.

Nicht in F1: Kategorien, Transfers, Bilanz.

## 2. Testdaten

`tests/fixtures/f1_ok.xlsx` hat dieselben 30 Spalten wie der Finanzguru-Export. Die neueste Zeile steht oben. Gebaut wird die Datei mit `tests/fixtures/build_f1.py`.

| Zeile | Konto | Datum | Betrag | Kontostand | Gegenpartei | Fall |
|---|---|---|---|---|---|---|
| 2 | Giro | 02.10. | −15.000,00 | −219,55 | Autohaus | negativer Kontostand |
| 3 | PayPal | 01.10. 00:00:01 | +59,99 | 0 | Steam Games | Aufladung, Uhrzeit, Kontostand 0 |
| 4 | Giro | 01.10. | +12.345,67 | 14.780,45 | Finanzamt | großer Betrag |
| 5 | PayPal | 30.09. 23:59:59 | −59,99 | −59,99 | Steam Games | Uhrzeit kurz vor Monatsende |
| 6 | Giro | 30.09. | 0,00 | 2.434,78 | Bank | Nullbetrag |
| 7 | Giro | 15.09. | −0,20 | 2.434,78 | Kiosk | Float-Falle |
| 8 | Giro | 15.09. | −0,10 | 2.434,98 | Kiosk | Float-Falle |
| 9 | Giro | 10.09. | −107,91 | 2.435,08 | Amazon | Split: Original |
| 10 | Giro | 10.09. | −50,92 | 2.435,08 | Amazon | Split: Teilbuchung |
| 11 | Giro | 10.09. | −56,99 | 2.486,00 | Amazon | Split: Restbetrag (eigene Kontostand-Kette wie im echten Export) |
| 12 | Giro | 03.09. | −3,50 | 2.542,99 | Bäckerei Körner | echte Doppelbuchung (2/2) |
| 13 | Giro | 03.09. | −3,50 | 2.546,49 | Bäckerei Körner | echte Doppelbuchung (1/2), Umlaute und „€“ im Zweck |
| 14 | Giro | 03.09. | −0,01 | 2.549,99 | EDEKA | Kleinstbetrag, Gegen-IBAN und Zweck leer |
| 15 | Giro | 02.09. | −950,00 | 2.550,00 | Hausverwaltung | Dauerauftrag |
| 16 | Giro | 01.09. | +2.500,00 | 3.500,00 | Arbeitgeber GmbH | ganzzahliger Betrag (int-Zelle) |
| 17 | Spar | 01.09. | +1,23 | 501,23 | Bank | Konto mit nur einer Buchung |

Fehler-Fixtures, jeweils eine Kopie von `f1_ok` mit genau einem Defekt:

| Datei | Defekt |
|---|---|
| `f1_fehlende_spalte` | Spalte „Betrag“ fehlt |
| `f1_doppelte_id` | Zeile 7 und 8 haben dieselbe ID |
| `f1_kontostand_luecke` | Zeile 15 (Miete) fehlt |
| `f1_leer` | nur die Kopfzeile |
| `f1_leeres_pflichtfeld` | Betrag in Zeile 13 leer |
| `f1_nachkommastellen` | Betrag in Zeile 13 ist −3,505 |
| `f1_fremdwaehrung` | Zeile 5 hat die Währung USD |

## 3. Erwartetes Ergebnis

```python
load_export(pfad) -> ImportErgebnis

Buchung:        zeile, id, konto, konto_name, datum, betrag, gegenpartei, gegen_iban, zweck
ImportErgebnis: buchungen: list[Buchung], warnungen: list[Warnung]
Warnung:        konto, zeile, erwartet, gefunden
ImportFehler:   grund, zeilen          # Exception = Abbruch
```

- `konto_name` kommt aus Finanzguru (Spalte „Name Referenzkonto“). Er dient nur als Namensvorschlag. Den eigentlichen Namen vergibt der Nutzer in `accounts.yaml` (F2). Ist die Spalte leer, wird `konto_name` zu `None`.

- `datum` ist ein `date`, die Uhrzeit fällt weg.
- Leere Textfelder werden `None`, alle anderen Texte bleiben unverändert.
- Die Reihenfolge bleibt wie in der Datei.
- Split-Teile werden vor allen Prüfungen verworfen.

**Beträge: Es wird nie gerundet.**

- Banken buchen mit genau 2 Nachkommastellen. Excel speichert die Zahlen aber binär, −0,10 zum Beispiel als −0,1000000000000000055….
- Wir lesen über `str()`, also als „−0.1“, machen daraus ein `Decimal` und setzen 2 Stellen: „−0.10“. Das ist exakt.
- Hat ein Wert mehr als 2 Stellen, wird er nicht gerundet. Der Import bricht dann ab (`ungueltiges_feld`).
- Geprüft am echten Export: Alle 6.534 Beträge und Kontostände haben höchstens 2 Stellen.

| Fixture | Ergebnis |
|---|---|
| `f1_ok` | 14 Buchungen (Zeilen 2–9 und 12–17), 0 Warnungen. Summe der Giro-Beträge = −1219.55 (Endstand − Anfangsstand) |
| `f1_kontostand_luecke` | 13 Buchungen, 1 Warnung: Giro, Zeile 14, erwartet 3499.99, gefunden 2549.99 |
| `f1_leer` | 0 Buchungen, 0 Warnungen |
| `f1_fehlende_spalte` | `ImportFehler("fehlende_spalte")`, die Meldung nennt „Betrag“ |
| `f1_doppelte_id` | `ImportFehler("doppelte_id", zeilen=[7, 8])` |
| `f1_leeres_pflichtfeld` | `ImportFehler("leeres_feld", zeilen=[13])` |
| `f1_nachkommastellen` | `ImportFehler("ungueltiges_feld", zeilen=[13])` |
| `f1_fremdwaehrung` | `ImportFehler("waehrung", zeilen=[5])` |

## 4. Tests

- `tests/test_f1_import.py` prüft alle Punkte aus Abschnitt 3.
  - `test_ok_gesamtergebnis` vergleicht alle Felder aller 14 Buchungen aus `f1_ok` mit einer von Hand geschriebenen Erwartung.
- `tests/test_fixture_struktur.py` vergleicht Kopfzeile und Zelltypen von `f1_ok` mit einem echten Export. Er läuft nur, wenn `BILANZ_EXPORT` gesetzt ist.

## 5. Code

`src/bilanz/importer.py`, fertig.
