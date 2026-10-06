---
name: retouren-analyse
description: Findet Muster in E-Commerce-Retourendaten (CSV-Export aus ERP oder Shop-System) und leitet priorisierte Maßnahmen ab. Anwenden bei "Retouren analysieren", "Retourenquote", "warum kommen Produkte zurück", "Retouren-Report", "Retourenkosten", "Serien-Retournierer", "Größe stimmt nicht" und immer, wenn eine CSV mit Spalten zu Retouren oder Rücksendungen vorliegt, auch ohne die Wörter "Retoure" oder "Skill", etwa wenn der Nutzer nur den Export schickt. System-agnostisch (Xentral, Shopify, WooCommerce, generisch), ohne API und ohne sensible Live-Zugänge.
---

# Retouren-Analyse

Analysiert Retourendaten eines E-Commerce-Shops auf Muster, die Dashboards nicht zeigen: Größen-Läufer, Chargen-Probleme, Serien-Retournierer, nicht abgeholte Sendungen, Kostentreiber.

Grundregel: **Das Script rechnet, du interpretierst.** Keine Quote und keine Summe selbst rechnen; jede Zahl im Report stammt aus `analysis.json`.

## Ablauf

### Phase 1: Mapping (immer zuerst)

1. Kopfzeilen der gelieferten CSV-Dateien lesen (Retouren-Positionen und Verkaufs-Positionen). Ohne Verkaufsbasis keine Quoten: nur Struktur-Analyse, und das deutlich sagen.
2. Spalten auf das kanonische Schema mappen (`reference/schema.md`). Bei Mehrdeutigkeit nachfragen, nicht raten.
3. Vor dem Rechnen drei Punkte klären (entfällt beim Demo-Datensatz):
   - Retourengründe kundengewählt, servicegewählt oder Freitext?
   - Länge des Rückgabefensters laut Policy?
   - Deckt der Verkaufs-Export den Retouren-Zeitraum plus Rückgabefenster nach vorn ab?
4. Fehlende optionale Spalten nennen und auflisten, welche Analysen dadurch entfallen.
5. **Ergebnis dieser Phase sofort ausgeben, vor dem Rechnen:** gemappte Spalten, Zeilenzahl, Zeitraum, Lücken. Drei bis vier Zeilen. In einer Live-Session ist das der erste sichtbare Inhalt und soll nach Sekunden stehen.

### Phase 2: Rechnen

```bash
python3 scripts/retouren_analyse.py --retouren <retouren.csv> --verkaeufe <verkaeufe.csv> --out analysis.json
```

Parameter (Defaults sind markierte Annahmen):

| Parameter | Bedeutung | Default |
|---|---|---|
| `--prozesskosten` | EUR je Retoure (EHI-Kernbereich 5 bis 20) | 10.00 |
| `--rueckgabefenster` | Tage | 60 |
| `--min-retouren` | Mindest-N je SKU | 3 |
| `--reifepuffer` | Tage | 21 |

### Phase 3: Interpretieren und berichten

- Der Report kommt vor dem Dashboard. Er ist der Kern und in einer Live-Session das Einzige, was beim Entstehen mitlesbar ist.
- `analysis.json` **einmal komplett** lesen, nicht abschnittsweise.
- **Verdict, Kennzahlen und Findings zuerst ausgeben**, dann weiterschreiben. So steht das Wichtigste früh da, und der Nutzer liest, während der Rest entsteht.

Struktur des Reports aus `analysis.json`:

1. **Verdict:** zwei bis drei Sätze, das teuerste Muster zuerst, in Euro.
2. **Kennzahlen:** Beta-, Gamma- und Bestellquote je Bestell-Kohorte. Unreife Kohorten (Flag `mature: false`) immer als vorläufig kennzeichnen.
3. **Muster-Findings:** je Finding eine Zeile Kernaussage, dann der Beleg. Jedes Finding hat ein Evidenz-Tag:
   - `export`: direkt aus den Daten belegt (Zahl aus analysis.json)
   - `hypothesis`: plausible Deutung, aus den Daten allein nicht beweisbar
   - `needs_data`: erst mit zusätzlicher Spalte oder Quelle prüfbar
4. **Was sonst untergegangen wäre:** der Abschnitt `blinde_flecken` aus der Analyse. Befunde, die ein normaler Retouren-Report strukturell nicht zeigt, etwa ein Scheintrend durch unreife Kohorten, ein Merkmal, das erst in der Kreuzung auffällt, oder ein Artikel, der brutto verdient und nach Retouren nichts übrig lässt.
   - Je Befund beides nennen: was vorliegt und warum der Standard-Report es nicht zeigt.
   - Vollwertiger Abschnitt, keine Fußnote; er ist der Hauptgrund für die Analyse.
5. **Maßnahmen:** je bestätigtem Muster eine Maßnahme im Format aus `reference/massnahmen.md`.
   - Pflichtfelder: Was passiert, Warum es zählt, Größe des Hebels in Euro, Was zu tun ist (nummerierte Schritte), Aufwand, Wer, Woran du merkst dass es wirkt, Was dabei nicht kaputtgehen darf.
   - Reihenfolge nach Geld und Aufwand: teuer und schnell zuerst.
   - Jede Maßnahme gegen `reference/evidenz.md` prüfen: nur empfehlen, was dort als gemessen wirksam gilt. Dort widerlegte Maßnahmen (etwa Größenberater-Software, Streichen von Zahlarten) nie vorschlagen.
6. **Was auffällig aussieht, aber in Ordnung ist:** Pflichtabschnitt. Mindestens zwei geprüfte, unbedenkliche Punkte mit Zahl (etwa Kanäle oder Zahlarten, die dicht beieinander liegen). Ein leerer Abschnitt heißt: nicht genau genug geprüft. Er verhindert, dass jede Zahl zum Problem wird.
7. **Offene Fragen:** was die Daten allein nicht entscheiden und der Mensch beantworten muss (etwa ob ein Ausschlag eine Charge oder eine Kampagne war). Fragen statt Behauptungen.
8. **Annahmen und fehlende Daten:** alle Default-Annahmen (Prozesskostensatz usw.) und was weitere Spalten ermöglichen würden.

### Phase 4: Dashboard erzeugen

```bash
python3 scripts/dashboard.py --analyse analysis.json --out dashboard.html --titel "<Shop> · <Zeitraum>"
```

- Ergebnis: eigenständige HTML-Datei ohne externe Abhängigkeiten, mit Dunkelmodus, im Browser zu öffnen und weiterzugeben.
- Inhalt: Kennzahlen, blinde Flecken, Kohorten-Chart, Kosten je Artikel, Retourengründe, Zahlart-Kontrast, Größen-Verteilung, alle Zahlen als Tabelle.
- Zeigt dieselben Befunde wie der Report, visuell, deshalb am Schluss: erst der Text, dann das Bild zum Weitergeben.
- Dem Nutzer den Dateipfad nennen.

## Tempo

Beide Scripts laufen zusammen in unter einer Sekunde; die Laufzeit entsteht beim Lesen und Schreiben. Vier Regeln:

- **`analysis.json` in einem Read lesen.** Rund 20 KB; Abschnitte kosten nur Roundtrips.
- **`reference/massnahmen.md` und `reference/evidenz.md` mit dem Read-Tool laden, nicht per `cat`.** Über die Shell gehen große Dateien in eine Zwischendatei, die erneut gelesen werden muss.
- **Dashboard nicht im Browser gegenprüfen.** Es ist deterministischer Script-Output; ein Screenshot beweist nichts und kostet in einer Live-Session eine Minute.
- **Ausgabe-Dateien nicht aufräumen** (keine Diffs gegen alte Stände, kein Verschieben), solange der Nutzer nicht danach fragt.

## Guardrails (hart)

- Keine SKU-Quote ranken oder hervorheben, deren Verkaufsbasis unter dem Mindest-N liegt.
- Kohorten-Quoten nie mit Perioden-Quoten mischen; unreife Kohorten nie als Trend darstellen.
- Serien-Retournierer und Wardrobing sind eine Review-Liste für Menschen, nie eine automatische Sanktion, nie eine Beschuldigung.
- Eine strengere Retouren-Policy ist nie die Default-Empfehlung.
- Keine Versprechen zu Conversion oder Ersparnis ("spart X Prozent"). Impact immer als "bis zu, wenn Muster abgestellt", mit der Zahl aus den Daten.
- Jede Zahl im Report steht in analysis.json. Fehlt sie dort, kommt sie nicht in den Report.
- Eine Ursache, eine Maßnahme. Sechs auffällige Varianten desselben Artikels sind ein Größenproblem, nicht sechs Aufgaben.
- Jede Maßnahme bekommt eine Gegen-Kennzahl, weil fast jeder Retouren-Hebel Conversion oder Umsatz kosten kann.
- Eine benannte Lücke ist eine vollständige Antwort. Nie eine Zahl schätzen, damit der Report vollständig wirkt.

## Demo

- `demo/generate_demo_data.py` erzeugt einen synthetischen Datensatz im Stil eines ERP-Berichte-Exports (Spalten wie bei Xentral üblich, generisch nutzbar) mit eingebauten Mustern.
- Ablauf der Live-Demo: Daten generieren, Script laufen lassen, Report schreiben, Dashboard zum Schluss.
- `demo/beispiel-report.md` zeigt einen kompletten Beispiel-Report in der finalen Struktur; bei Unsicherheit über Ton oder Tiefe eines Abschnitts dort nachsehen.
