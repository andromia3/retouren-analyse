"""Befunde: aus den gerechneten Zahlen werden Karten mit Bedeutung und Maßnahme.

Struktur je Befund nach dem Theme-Muster: Was passiert, warum es zählt, wie groß
der Hebel ist, was zu tun ist, Aufwand, Owner, Erfolgsmessung, Gegen-Kennzahl.
Ein Befund ohne Maßnahme ist nur eine Beobachtung.

Die Zahlen kommen aus analysis.json, die Fachlogik aus reference/massnahmen.md
und reference/evidenz.md.
"""


def _pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}".replace(".", ",") + " %"


def _eur(x, d=0):
    if x is None:
        return "n/a"
    s = f"{x:,.{d}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".") + " EUR"


def _num(x):
    return f"{x:,.0f}".replace(",", ".")


def _artikel_kosten(d, name):
    """Retourenkosten eines Artikels ueber alle Varianten.

    Nicht aus kosten_top summieren: die Liste ist auf zehn Zeilen gekuerzt, ein
    Artikel dahinter kaeme dann mit 0 EUR heraus und rutschte in der nach Geld
    sortierten Reihenfolge ans Ende.
    """
    return next((s["gesamt"] for s in d.get("kosten_je_artikel", []) if s["name"] == name), 0)


def _fleck(d, fleck_id):
    """Blinden Fleck ueber seine stabile ID holen.

    Frueher lief das ueber Teilstrings der Ueberschrift. Das ist einmal still
    gerissen (die Karte "teuer trotz normaler Quote" fehlte im Dashboard, ohne
    dass irgendwo ein Fehler auftauchte). Ueber die ID kann das nicht passieren.
    """
    return next((f for f in d.get("blinde_flecken", []) if f.get("id") == fleck_id), None)


def sammle(d):
    """Liefert eine nach Geldwert sortierte Liste von Befunden."""
    b = []
    kosten = d.get("kosten_top", [])
    flecken = {f["titel"]: f for f in d.get("blinde_flecken", [])}

    # --- Artikel ohne Deckungsbeitrag nach Retouren
    marge = _fleck(d, "marge_falle")
    if marge and marge.get("artikel"):
        arts = marge["artikel"]
        namen = sorted({a["name"] for a in arts})
        neg = [a for a in arts if a["db_nach_retouren"] < 0]
        summe = sum(_artikel_kosten(d, n) for n in namen)
        schlimmster = min(arts, key=lambda a: a["db_nach_retouren"])
        b.append({
            "titel": f'{namen[0]}: Rohertrag durch Retouren stark gesunken',
            "unsichtbar": "Retourenkosten stehen in keiner Sortimentsauswertung am Artikel. "
                          "Dort erscheint er mit normaler Marge und normalem Umsatz.",
            "was": f'{len(arts)} Varianten stehen nach Abzug der Retourenkosten unter einem Viertel '
                   f'ihres vorherigen Rohertrags, '
                   f'{len(neg)} davon im Minus. Schlechteste Variante {schlimmster["sku"]}: '
                   f'{_eur(schlimmster["db_vor_retouren"])} Rohertrag, danach {_eur(schlimmster["db_nach_retouren"])}.',
            "warum": "Die Retourenkosten haben den Rohertrag dieser Varianten stark verringert. "
                     "Ein geringer verbleibender Rohertrag ist noch kein Verlust. Ob der Rohertrag "
                     "negativ ist, zeigen die ausgewiesenen Beträge. Die Ursache muss anhand der "
                     "Retourengründe und der Kalkulation geprüft werden.",
            "hebel": summe,
            "hebel_text": f'{_eur(summe)} Retourenkosten im Zeitraum',
            "schritte": [
                "Retourengründe dieses Artikels einzeln durchgehen, bevor am Preis gedreht wird.",
                "Kalkulation prüfen: Trägt die Marge überhaupt eine normale Retourenquote?",
                "Wenn die Ursache abstellbar ist (Größe, Fotos, Qualität), zuerst dort ansetzen.",
                "Wenn nicht: Preis, Einkauf oder Auslistung. Das ist eine Sortimentsentscheidung.",
            ],
            "aufwand": "M für die Analyse, die Entscheidung liegt darüber",
            "wer": "Einkauf, Entscheidung Geschäftsführung",
            "messung": "Deckungsbeitrag nach Retouren je Variante, nächste vollständige Bestellkohorte",
            "gegen": "Sortimentsbreite und Warenkorbgröße, falls der Artikel Kombikäufe zieht",
        })

    # --- Größen-Läufer
    for l in d.get("groessen_laeufer", [])[:1]:
        gesamt = l["zu_klein"] + l["zu_gross"]
        art_kosten = _artikel_kosten(d, l["style"])
        b.append({
            "titel": f'{l["style"]} {l["richtung"]}',
            "unsichtbar": None,
            "was": f'{l["zu_klein"]} Retouren mit Grund "zu klein" gegen {l["zu_gross"]} mit "zu groß", '
                   f'durchgehend über alle Größen. Das ist kein Streuungsmuster, sondern ein '
                   f'Schnittfehler des Artikels.',
            "warum": "Wenn ein Artikel systematisch kleiner ausfällt als erwartet, bestellt ein Teil der "
                     "Kundschaft von vornherein zwei Größen und der Rest schickt zurück. Beides kostet, "
                     "und beides ist mit einer Zeile auf der Produktseite behebbar. Es ist die am besten "
                     "belegte Stellschraube im Retourenmanagement.",
            "hebel": art_kosten,
            "hebel_text": f'{gesamt} größenbedingte Retouren' +
                          (f', {_eur(art_kosten)} Retourenkosten des Artikels' if art_kosten else ''),
            "schritte": [
                'Hinweis "fällt klein aus, wir empfehlen eine Größe größer" direkt an die Größenauswahl, '
                'nicht in die Größentabelle.',
                "Artikel nachmessen und die echten Maße in die Größentabelle eintragen, nicht die "
                "Herstellerangabe.",
                "Bei durchgehender Abweichung die Gradierung mit dem Lieferanten klären.",
                "Größenberater-Software zuletzt. Sie ist nach der Datenlage vor allem ein "
                "Conversion-Werkzeug, kein Retouren-Werkzeug.",
            ],
            "aufwand": "S für Schritt 1 und 2, L für den Lieferanten",
            "wer": "Shop und Content, für die Gradierung der Einkauf",
            "messung": 'Anteil "zu klein" an den Retouren dieses Artikels, frühestens vier bis sechs '
                       "Wochen nach der Änderung",
            "gegen": "Zahl der Mehrgrößen-Bestellungen. In Zalandos A/B-Test stiegen sie durch solche "
                     "Hinweise um 11 Prozent. Steigt das stärker als die Quote fällt, ist die Maßnahme "
                     "unterm Strich negativ.",
            "beleg": "Gemessen bei Zalando (KDD 2021, A/B-Test mit über 180.000 Personen je Gruppe): "
                     "minus 4,3 bis 6,6 Prozent größenbedingte Retouren. Fremdkontext, keine Prognose.",
        })

    # --- Nicht abgeholte Sendungen
    np_ = d.get("nicht_abgeholt") or {}
    if np_.get("sendungen"):
        # Fuer die Reihenfolge zaehlt die margenbasierte Zahl, sonst wird dieser Befund gegen
        # die Artikelkosten kuenstlich gross. Im Text steht trotzdem der verlorene Umsatz,
        # weil das die Zahl ist, die im Gespraech gemeint ist.
        schaden = np_.get("schaden_vergleichbar",
                          np_["verlorener_umsatz"] + np_["zusatzkosten_versand_annahme"])
        kontrast = _fleck(d, "segment_kontrast")
        k_text = ""
        if kontrast:
            k = kontrast["kontraste"][0]
            k_text = (f' Auffällig: {k["merkmal"]} macht {_pct(k["anteil_im_gesamtgeschaeft"])} des '
                      f'Geschäfts aus, aber {_pct(k["anteil_bei_nicht_abgeholt"])} dieser Fälle.')
        b.append({
            "titel": "Sendungen, die nie abgeholt wurden",
            "unsichtbar": "Beim Versanddienstleister läuft der Fall als zugestellt und danach "
                          "retourniert. In der Versandstatistik ist alles grün. Sichtbar wird es nur "
                          "im eigenen Retourendatensatz.",
            "was": f'{_num(np_["sendungen"])} Sendungen kamen ungeöffnet zurück, '
                   f'{_pct(np_["anteil_an_bestellungen"])} aller Bestellungen und '
                   f'{_pct(np_["anteil_an_retouren_vorgaengen"])} aller Retourenvorgänge.{k_text}',
            "warum": "Das ist die teuerste Art von Retoure: Versand hin, Versand zurück, volle "
                     "Erstattung, kein Gegenwert und keine Chance auf einen Umtausch. Die Ware war "
                     "wochenlang gebunden. Und anders als bei einer normalen Retoure gibt es keine "
                     "Kaufentscheidung, die man hätte besser vorbereiten können, sondern nur einen "
                     "Zustellprozess, der nicht zu Ende gegangen ist.",
            "hebel": schaden,
            "hebel_text": f'{_eur(np_["verlorener_umsatz"])} Umsatz plus '
                          f'{_eur(np_["zusatzkosten_versand_annahme"])} Prozesskosten',
            "schritte": [
                'Abhol-Erinnerung auslösen, sobald der Status "im Paketshop hinterlegt" kommt. '
                "Die Frist beträgt bei DHL sieben Tage, dann geht das Paket automatisch zurück.",
                "Adressprüfung im Checkout aktivieren (Validierung, Vorschläge, Tippfehler-Erkennung).",
                "Zustelloptionen anbieten: Wunschort, Paketshop-Wahl, Wunschtag.",
                "Bei auffälliger Zahlart im Einzelfall das Risiko steuern, die Zahlart aber nicht "
                "abschalten. Sie zieht das Verhalten an, sie erzeugt es nicht.",
            ],
            "aufwand": "M für Erinnerung und Zustelloptionen, S bis M für die Adressprüfung",
            "wer": "Logistik, für die Adressprüfung der Shop",
            "messung": "Anzahl nicht abgeholter Sendungen pro Monat und ihr Anteil an allen Sendungen",
            "gegen": "Conversion im Checkout und der Umsatzanteil der betroffenen Zahlart",
            "beleg": "In Deutschland scheitern rund 7 Prozent der Zustellungen im ersten Versuch. "
                     "Nach einer Befragung ändern 20 Prozent der Empfänger nach der ersten "
                     "Tracking-Nachricht Zeit oder Ort der Zustellung.",
        })

    # --- Teuer trotz normaler Quote
    vol = _fleck(d, "teuer_trotz_normaler_quote")
    if vol and vol.get("artikel"):
        arts = vol["artikel"]
        namen = sorted({a["name"] for a in arts})
        summe = sum(a["kosten"] for a in arts)
        b.append({
            "titel": f'{namen[0]}: unauffällige Quote, hohe Kosten',
            "unsichtbar": "Retouren-Reports ranken nach Quote. Ein Bestseller mit durchschnittlicher "
                          "Quote taucht dort nie auf.",
            "was": f'{len(arts)} Varianten mit Quoten zwischen '
                   f'{_pct(min(a["beta_quote"] for a in arts))} und {_pct(max(a["beta_quote"] for a in arts))}, '
                   f'also im normalen Bereich. Zusammen kosten sie {_eur(summe)}.',
            "warum": "Die Quote sagt nichts über den Geldbetrag. Ein Artikel mit hohem Volumen oder "
                     "hohem Preis kostet bei völlig normaler Quote mehr als jeder Ausreißer. Wer nur "
                     "die Quotenliste anschaut, arbeitet an den falschen Artikeln.",
            "hebel": summe,
            "hebel_text": f'{_eur(summe)} Retourenkosten bei normaler Quote',
            "schritte": [
                "Nicht die Quote senken wollen, sondern die absoluten Kosten. Schon ein Prozentpunkt "
                "weniger ist hier mehr wert als zehn bei einem Nischenartikel.",
                "Retourengründe dieses Artikels ansehen: Steckt ein konkretes Muster dahinter oder "
                "ist es der normale Branchenpegel?",
                "Ist es der normale Pegel, gehört der Artikel in die laufende Kostenrechnung, nicht "
                "in die Maßnahmenliste.",
            ],
            "aufwand": "S für die Prüfung",
            "wer": "Shop und Controlling",
            "messung": "Retourenkosten dieses Artikels je Monat, nicht seine Quote",
            "gegen": "Absatz. Der Artikel ist ein Bestseller, Eingriffe wirken hier stärker als anderswo.",
        })

    # --- Chargen-Verdacht
    for c in d.get("chargen_spikes", [])[:1]:
        b.append({
            "titel": f'Qualitäts-Ausschlag bei {c["style"]}',
            "unsichtbar": None,
            "was": f'{_num(int(c["defekte"]))} Defekt-Retouren im Monat {c["monat"]}, sonst rund '
                   f'{c["basis_schnitt"]:.0f} pro Monat.'.replace(".0", ""),
            "warum": "Eine solche Häufung in einem einzelnen Monat ist selten Zufall. Meistens steckt "
                     "eine Charge dahinter. Liegt der Rest davon noch im Lager, produziert er weiter "
                     "Retouren, schlechte Bewertungen und Servicefälle, bis er verkauft ist.",
            "hebel": None,
            "hebel_text": f'{_num(int(c["defekte"]))} Retouren in einem Monat, '
                          f'davon der Großteil vermeidbar, wenn der Verdacht stimmt',
            "schritte": [
                "Restbestand prüfen und bei Bestätigung sperren, bevor weiter verkauft wird.",
                "Wareneingang des Zeitraums der Charge zuordnen.",
                "Beim Lieferanten reklamieren, mit den Retourengründen als Beleg.",
                "Bei Sicherheits- oder Qualitätsthemen betroffene Kunden proaktiv anschreiben.",
            ],
            "aufwand": "S bis M, hängt an der Rückverfolgbarkeit",
            "wer": "Einkauf und Logistik",
            "messung": "Defekt-Retouren dieses Artikels pro Monat, zurück auf das Niveau davor",
            "gegen": "Lieferfähigkeit. Eine gesperrte Charge ohne Nachschub ist ein Umsatzloch.",
            "einschraenkung": "Ohne Chargennummer im Export ist die Zuordnung eine zeitliche Näherung, "
                              "kein Beweis.",
        })

    # --- Kohorten-Scheintrend
    koh = _fleck(d, "kohorten_scheintrend")
    if koh:
        unreif = koh.get("unreife_kohorten", [])
        b.append({
            "titel": "Die letzten Monate sehen besser aus, als sie sind",
            "unsichtbar": "Die übliche Auswertung zählt Retouren in dem Monat, in dem sie im Lager "
                          "ankommen. Dann steckt in jedem Monat eine Mischung aus alten und neuen "
                          "Bestellungen, und die letzten Monate wirken automatisch gut.",
            "was": "So ist hier gerechnet: Jede Retoure wird der Bestellung zugerechnet, aus der sie "
                   "stammt. Eine Retoure aus einer Januar-Bestellung zählt zum Januar, auch wenn sie "
                   "erst im März eintrifft. Das macht Monate vergleichbar, hat aber eine Folge: "
                   + koh["befund"] + " Betroffen sind "
                   + (", ".join(unreif) if unreif else "die jüngsten Monate")
                   + ", dort läuft die Rückgabefrist noch.",
            "warum": "Aus einer scheinbar fallenden Quote folgen falsche Entscheidungen. Eine Maßnahme "
                     "sieht aus, als hätte sie gewirkt. Ein Problem scheint sich von selbst zu erledigen. "
                     "Beides stimmt nicht, und man merkt es erst Monate später, wenn die Nachzügler da "
                     "sind. Deshalb sind unfertige Monate hier gekennzeichnet und fließen in keinen "
                     "Vergleich ein.",
            "hebel": None,
            "hebel_text": "kein Eurobetrag, aber die Grundlage jeder anderen Zahl hier",
            "schritte": [
                "Im eigenen Reporting prüfen, ob Retouren nach Bestell- oder nach Eingangsmonat "
                "gezählt werden. Bei Eingangsmonat ist jeder Monatsvergleich verzerrt.",
                "Einen Monat erst bewerten, wenn Rückgabefrist plus Bearbeitungszeit abgelaufen sind.",
                "Unfertige Monate im Report sichtbar kennzeichnen, statt sie kommentarlos mitzuzeigen.",
                "Erfolge von Maßnahmen erst an vollständigen Monaten festmachen.",
            ],
            "aufwand": "S, eine Frage der Auswertungslogik",
            "wer": "Controlling",
            "messung": "Dieselbe Kohorte nach Ablauf der Reifezeit gegen die Zahl, die vorher gemeldet wurde",
            "gegen": "keine, das ist eine reine Korrektur der Rechenweise",
        })

    # --- Retouren ohne Grund
    og = _fleck(d, "gruende_fehlen")
    if og:
        b.append({
            "titel": "Retouren ohne verwertbaren Grund",
            "unsichtbar": og["warum_uebersehen"],
            "was": f'{_num(og["anzahl"])} Retouren, {_pct(og["anteil"])} aller Fälle, ohne brauchbare '
                   f'Grundangabe.',
            "warum": "Jede fehlende Angabe ist eine Analyse, die nicht stattfinden kann. Und die Lücken "
                     "verteilen sich selten gleichmäßig: Wenn ein Artikel oder ein Rückgabeweg auffällig "
                     "oft ohne Grund erfasst wird, steckt dort meist ein eigener Fall, den niemand sieht.",
            "hebel": None,
            "hebel_text": "nicht bezifferbar, aber Voraussetzung für jede weitere Auswertung",
            "schritte": [
                "Prüfen, an welcher Stelle der Grund verloren geht: Retourenportal, Wareneingang, "
                "manuelle Erfassung.",
                "Pflichtfeld mit wenigen, klaren Auswahlmöglichkeiten statt Freitext.",
                "Freitext zusätzlich anbieten, aber nicht als einzige Option.",
                "Prüfen, ob sich die Lücken auf bestimmte Artikel oder Rückgabewege häufen.",
            ],
            "aufwand": "M, hängt am System",
            "wer": "Logistik und Kundenservice",
            "messung": "Anteil der Retouren ohne Grund, Ziel unter 5 Prozent",
            "gegen": "Bearbeitungszeit im Wareneingang",
        })

    b.sort(key=lambda x: x["hebel"] if x["hebel"] else -1, reverse=True)
    return b
