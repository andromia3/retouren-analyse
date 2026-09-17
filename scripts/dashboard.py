#!/usr/bin/env python3
"""Erzeugt aus analysis.json ein eigenstaendiges HTML-Dashboard.

Keine externen Abhaengigkeiten, keine Netzwerkzugriffe, nur Python-Stdlib.
Charts sind inline SVG. Farblogik: eine Datenfarbe (Emerald) plus ein Akzent
(Signal) ausschliesslich fuer das, was auffaellt. Keine kategorische Palette,
weil jeder Chart genau eine Serie hat.
"""
# naming-lint: schema (liest das Schema aus retouren_analyse.py, siehe dort)

import argparse
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import befunde as befunde_mod  # noqa: E402

PAPER = "#FAFAF7"
INK = "#083A2A"
EMERALD = "#0B6E4F"
EMERALD_HELL = "#10A26B"
MOSS = "#D4EDE0"
SIGNAL = "#F2653C"


def esc(x):
    return html.escape(str(x))


def pct(x, digits=1):
    if x is None:
        return "n/a"
    return f"{x * 100:.{digits}f}".replace(".", ",") + " %"


def eur(x, digits=0):
    if x is None:
        return "n/a"
    s = f"{x:,.{digits}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".") + " EUR"


def num(x):
    return f"{x:,.0f}".replace(",", ".")


def bars(rows, value_key, label_key, fmt, highlight=None, height=26, gap=10, label_w=None):
    """Horizontale Balken als SVG. rows: Liste von dicts. highlight: Funktion -> bool.

    Das Label-Feld waechst mit dem laengsten Label mit, damit nichts ueberlaeuft.
    """
    if not rows:
        return "<p class='leer'>Keine Daten.</p>"
    vals = [abs(r[value_key] or 0) for r in rows]
    vmax = max(vals) or 1
    if label_w is None:
        laengste = max(len(str(r[label_key])) for r in rows)
        label_w = max(150, min(330, int(laengste * 7.4) + 14))
    bar_w = 430
    total_h = len(rows) * (height + gap)
    out = [f'<svg viewBox="0 0 {label_w + bar_w + 100} {total_h}" role="img" class="chart">']
    for i, r in enumerate(rows):
        y = i * (height + gap)
        v = r[value_key] or 0
        w = max(2, abs(v) / vmax * bar_w)
        farbe = SIGNAL if (highlight and highlight(r)) else "var(--serie)"
        titel = f"{r[label_key]}: {fmt(v)}"
        out.append(
            f'<text x="0" y="{y + height * 0.7}" class="lbl">{esc(r[label_key])}</text>'
            f'<g class="mark"><title>{esc(titel)}</title>'
            f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="{height}" rx="4" fill="{farbe}"/></g>'
            f'<text x="{label_w + w + 10:.1f}" y="{y + height * 0.7}" class="val">{esc(fmt(v))}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def kohorten_chart(kohorten):
    """Balken je Bestellmonat. Unvollständige Monate zeigen den Ist-Wert dunkel und
    die Hochrechnung auf den erwarteten Endwert hell darüber."""
    if not kohorten:
        return ""
    w_bar, gap, h = 66, 30, 190
    vals = [max(k.get("beta_hochgerechnet") or 0, k["beta_quote"] or 0) for k in kohorten]
    vmax = max(vals) or 1
    breite = len(kohorten) * (w_bar + gap)
    out = [f'<svg viewBox="0 0 {breite} {h + 70}" role="img" class="chart">']
    for i, k in enumerate(kohorten):
        x = i * (w_bar + gap)
        v = k["beta_quote"] or 0
        hoch = k.get("beta_hochgerechnet")
        bh = max(3, v / vmax * h)
        y = h - bh
        titel = f'{k["kohorte"]}: {pct(v)} bisher'
        if hoch:
            gesamt_h = hoch / vmax * h
            y_h = h - gesamt_h
            titel += f', hochgerechnet {pct(hoch)} bei {pct(k["reifegrad"], 0)} Reife'
            out.append(
                f'<rect x="{x}" y="{y_h:.1f}" width="{w_bar}" height="{(gesamt_h - bh):.1f}" '
                f'fill="var(--serie)" opacity="0.22"/>'
                f'<line x1="{x}" y1="{y_h:.1f}" x2="{x + w_bar}" y2="{y_h:.1f}" '
                f'stroke="var(--signal)" stroke-width="2" stroke-dasharray="4 3"/>'
                f'<text x="{x + w_bar / 2}" y="{y_h - 8:.1f}" class="mini mitte">{esc(pct(hoch))}</text>'
            )
        out.append(
            f'<g class="mark"><title>{esc(titel)}</title>'
            f'<rect x="{x}" y="{y:.1f}" width="{w_bar}" height="{bh:.1f}" fill="var(--serie)"/></g>'
            f'<text x="{x + w_bar / 2}" y="{h + 20}" class="lbl mitte">'
            f'{esc(k["kohorte"][5:])}.{esc(k["kohorte"][2:4])}</text>'
        )
        if hoch:
            out.append(f'<text x="{x + w_bar / 2}" y="{h + 38}" class="mini mitte">'
                       f'{esc(pct(k["reifegrad"], 0))} da</text>')
        else:
            out.append(f'<text x="{x + w_bar / 2}" y="{y + bh * 0.5 + 5:.1f}" class="val-inv mitte">'
                       f'{esc(pct(v))}</text>')
    out.append("</svg>")
    return "".join(out)


GRUND_NAMEN = {
    "zu_klein": "Zu klein",
    "zu_gross": "Zu groß",
    "passform_schnitt": "Passform oder Schnitt",
    "farbe_optik_gefaellt_nicht": "Farbe oder Optik gefällt nicht",
    "nicht_wie_beschrieben": "Nicht wie beschrieben",
    "qualitaet_defekt": "Qualität oder Defekt",
    "transportschaden": "Transportschaden",
    "falscher_artikel": "Falscher Artikel geliefert",
    "zu_spaet_geliefert": "Zu spät geliefert",
    "reue_nicht_benoetigt": "Doch nicht benötigt",
    "nicht_abgeholt_annahme_verweigert": "Nicht abgeholt oder verweigert",
    "sonstiges_unbekannt": "Kein Grund erfasst",
}


def kachel(label, wert, zusatz="", akzent=False, info=""):
    """Eine KPI-Kachel. info erscheint als Fragezeichen und klappt beim Draufzeigen auf."""
    kl = " akzent" if akzent else ""
    z = f'<div class="zusatz">{esc(zusatz)}</div>' if zusatz else ""
    i = (f'<span class="info" tabindex="0" aria-label="Erklärung">?'
         f'<span class="info-text">{esc(info)}</span></span>') if info else ""
    return (
        f'<div class="kachel{kl}"><div class="klabel">{esc(label)}{i}</div>'
        f'<div class="kwert">{esc(wert)}</div>{z}</div>'
    )


def build(d, titel):
    q = d["quoten"]
    meta = d["meta"]
    kosten = d["kosten_top"]
    np_ = d["nicht_abgeholt"]
    er = d.get("ertragsrechnung", {})

    # --- KPI-Zeile
    # Unter jeder Quote steht ihr Bruch. Die drei Zahlen unterscheiden sich nur im Nenner,
    # und ohne den ist auf einen Blick nicht zu sehen, worin.
    basis = q.get("basis", {})
    pv = q.get("preisvergleich", {})
    preise = (f'{eur(pv.get("schnittpreis_retourniert"), 2)} je retourniertem Artikel gegenüber '
              f'{eur(pv.get("schnittpreis_versendet"), 2)} je versendetem Artikel')
    if pv.get("faktor") and pv["faktor"] > 1:
        wert_info = (f'Gamma-Retourenquote: Anteil des retournierten Warenwerts am versendeten '
                     f'Warenwert. Sie liegt über der Mengenquote, die Rückläufer sind also im Schnitt '
                     f'wertvoller als das versendete Sortiment: {preise}, ein Unterschied von '
                     f'{pct(pv["faktor"] - 1)}.')
    elif pv.get("faktor"):
        wert_info = (f'Gamma-Retourenquote: Anteil des retournierten Warenwerts am versendeten '
                     f'Warenwert. Sie liegt unter der Mengenquote, die Rückläufer sind also im Schnitt '
                     f'günstiger als das versendete Sortiment: {preise}.')
    else:
        wert_info = "Erstatteter Warenwert geteilt durch versendeten Warenwert. Gamma-Retourenquote."

    # Aeltere analysis.json-Staende kennen die getrennten Quoten nicht. Dann auf die
    # Gesamtwerte zurueckfallen, statt mit einem KeyError auszusteigen.
    rq = q.get("retourenquote", q["gesamt_beta"])
    rq_wert = q.get("retourenquote_wert", q["gesamt_gamma"])
    rq_best = q.get("retourenquote_bestellungen", q["gesamt_bestellquote"])
    art_kunde = basis.get("artikel_retourniert_kundenretoure", basis.get("artikel_retourniert"))
    wert_kunde = basis.get("warenwert_retourniert_kundenretoure", basis.get("warenwert_retourniert"))
    best_kunde = basis.get("bestellungen_mit_kundenretoure", basis.get("bestellungen_mit_retoure"))
    nicht_abg = basis.get("artikel_retourniert_nicht_abgeholt")
    abgrenzung = (f' Nicht enthalten sind {num(nicht_abg)} Artikel aus nie abgeholten Sendungen. '
                  f'Die sind kein Widerruf und keine Retoure, kosten aber Geld und stehen '
                  f'deshalb in der Kostenrechnung.') if nicht_abg else ""

    kacheln = [
        kachel("Retourenquote", pct(rq),
               f'{num(art_kunde)} von {num(basis.get("artikel_versendet"))} Artikeln',
               info="Die Standard-Kennzahl: Anteil der zurückgeschickten Artikel an allen "
                    "versendeten Artikeln, in der Fachsystematik die Beta-Retourenquote. "
                    "Bezugsgröße ist die Stückzahl, der Warenwert bleibt unberücksichtigt. "
                    "Je Artikel berechenbar und damit die Kennzahl für die Ursachenanalyse." + abgrenzung),
        kachel("Retourenquote nach Wert", pct(rq_wert),
               f'{eur(wert_kunde)} von {eur(basis.get("warenwert_versendet"))}',
               info=wert_info),
        kachel("Bestellungen mit Retoure", pct(rq_best),
               f'{num(best_kunde)} von {num(basis.get("bestellungen"))} Bestellungen',
               info="Anteil der Bestellungen mit mindestens einer Retoure. Liegt systembedingt über "
                    "der Beta-Quote, da ein einzelner retournierter Artikel die gesamte Bestellung "
                    "ausweist. Entspricht der Alpha-Quote, die jedoch auf Sendungen bezogen ist."),
        kachel("Rohertrag nach Retouren", eur(er.get("rohertrag_nach_retouren")),
               f'Rohertrag {eur(er.get("rohertrag_vor_retouren"))} minus '
               f'{eur(er.get("retourenkosten_gesamt"))} Retourenkosten', akzent=True,
               info="Umsatz abzüglich Wareneinsatz der behaltenen Ware, Retourenbearbeitung und "
                    "abgeschriebener Defektware. Ohne Versand, Verpackung, Zahlungsgebühren und "
                    "Marketing, entspricht damit keinem vollständigen DB2 und keinem Gewinn."),
    ]

    # --- Wasserfall: vom Umsatz zum Rohertrag nach Retouren, Zeile fuer Zeile nachrechenbar
    wf_zeilen = [
        ("Umsatz der versendeten Ware", er.get("bruttoumsatz"), "summe"),
        ("minus erstatteter Umsatz", -(er.get("erstatteter_umsatz") or 0), "abzug"),
        ("Nettoumsatz", er.get("nettoumsatz"), "summe"),
        ("minus Wareneinsatz der behaltenen Ware", -(er.get("wareneinsatz_behaltene_ware") or 0), "abzug"),
        ("Rohertrag der behaltenen Ware", er.get("rohertrag_behaltene_ware"), "summe"),
        ("minus Retourenbearbeitung", -(er.get("retourenbearbeitung") or 0), "abzug"),
        ("minus abgeschriebene Defektware", -(er.get("abschreibung_defekt") or 0), "abzug"),
        ("Rohertrag nach Retouren", er.get("rohertrag_nach_retouren"), "summe"),
    ]
    wasserfall = "".join(
        f'<tr class="{kl}"><td>{esc(lbl)}</td><td class="zahl">{esc(eur(v))}</td></tr>'
        for lbl, v, kl in wf_zeilen) if er else ""

    # --- Charts
    gruende = [{"grund": GRUND_NAMEN.get(k, k.replace("_", " ")), "n": v}
               for k, v in list(d["gruende"].items())[:8]]
    chart_gruende = bars(gruende, "n", "grund", lambda v: num(v),
                         highlight=lambda r: "Nicht abgeholt" in r["grund"] or "Kein Grund" in r["grund"])

    kosten_rows = [{"art": f'{c["name"]} · {c["sku"]}', "wert": c["gesamt"],
                    "neg": c.get("deckungsbeitrag_nach_retouren") is not None
                           and c["deckungsbeitrag_nach_retouren"] < 0}
                   for c in kosten[:8]]
    chart_kosten = bars(kosten_rows, "wert", "art", lambda v: eur(v),
                        highlight=lambda r: r["neg"])

    zahlart = []
    kontrast = None
    for b in d.get("blinde_flecken", []):
        if b.get("kontraste"):
            kontrast = b["kontraste"][0]
    if kontrast:
        m = kontrast["merkmal"]
        zahlart = [
            {"was": f"{m}: Anteil an allen Bestellungen", "v": kontrast["anteil_im_gesamtgeschaeft"], "hot": False},
            {"was": f"{m}: Anteil an den nicht abgeholten", "v": kontrast["anteil_bei_nicht_abgeholt"], "hot": True},
        ]
    chart_zahlart = bars(zahlart, "v", "was", lambda v: pct(v), highlight=lambda r: r["hot"]) if zahlart else ""

    laeufer = d.get("groessen_laeufer", [])
    chart_laeufer = ""
    if laeufer:
        l = laeufer[0]
        rows = [{"g": f'Größe {g}', "n": c.get("zu_klein", 0)} for g, c in sorted(l["je_groesse"].items())]
        chart_laeufer = bars(rows, "n", "g", lambda v: num(v))

    # --- Befund-Karten: Zahl, Bedeutung, Maßnahme
    befunde = [b for b in befunde_mod.sammle(d)
               if not b["titel"].startswith("Die letzten Monate")
               and not b["titel"].startswith("Retouren ohne")]
    karten = []
    for i, b in enumerate(befunde, 1):
        schritte = "".join(f"<li>{esc(s)}</li>" for s in b["schritte"])
        unsichtbar = (
            f'<p class="unsichtbar"><span class="mini-lbl">Warum das im Standard-Report fehlt</span>'
            f'{esc(b["unsichtbar"])}</p>' if b.get("unsichtbar") else ""
        )
        beleg = (f'<p class="beleg"><span class="mini-lbl">Belegt</span>{esc(b["beleg"])}</p>'
                 if b.get("beleg") else "")
        einschr = (f'<p class="beleg"><span class="mini-lbl">Einschränkung</span>{esc(b["einschraenkung"])}</p>'
                   if b.get("einschraenkung") else "")
        chart, chart_titel, chart_hint = "", "", ""
        t = b["titel"]
        if "verdient nach Retouren" in t or "unauffällige Quote" in t:
            chart, chart_titel = chart_kosten, "Retourenkosten je Artikelvariante"
            chart_hint = ("Entgangene Marge der zurückgeschickten Stücke plus Bearbeitung plus "
                          "abgeschriebene Defektware. Orange markiert: Von dem, was die Variante im "
                          "Verkauf verdient hat, bleibt danach nichts übrig.")
        elif "abgeholt" in t:
            chart, chart_titel = chart_zahlart, "Rechnungskauf: normal gegen auffällig"
            chart_hint = ("Dieselbe Zahlart zweimal gemessen. Je weiter die Balken auseinanderliegen, "
                          "desto stärker hängt das Nichtabholen mit ihr zusammen.")
        elif "fällt" in t and chart_laeufer:
            chart = chart_laeufer
            chart_titel = b["titel"].split(" fällt")[0] + ': Retouren "zu klein" je Größe'
            chart_hint = ("Verteilt sich das über alle Größen, liegt es am Schnitt des Artikels. "
                          "Trifft es nur einzelne Größen, ist es die Gradierung.")
        chart_block = (f'<div class="metrik"><p class="metrik-titel">{esc(chart_titel)}</p>'
                       f'<p class="metrik-hint">{esc(chart_hint)}</p>{chart}</div>') if chart else ""
        karten.append(f"""
        <section class="befund-gruppe">
        {chart_block}
        <article class="befund-karte">
          <div class="bk-kopf">
            <span class="bk-nr">{i:02d}</span>
            <h3>{esc(b["titel"])}</h3>
            <span class="bk-hebel">{esc(b["hebel_text"])}</span>
          </div>
          <div class="bk-body">
            <div class="bk-spalte">
              <p class="mini-lbl">Was in den Daten steht</p>
              <p>{esc(b["was"])}</p>
              <p class="mini-lbl">Warum das zählt</p>
              <p>{esc(b["warum"])}</p>
              {unsichtbar}{beleg}{einschr}
            </div>
            <div class="bk-spalte">
              <p class="mini-lbl">Was zu tun ist</p>
              <ol>{schritte}</ol>
              <dl class="bk-meta">
                <dt>Aufwand</dt><dd>{esc(b["aufwand"])}</dd>
                <dt>Wer</dt><dd>{esc(b["wer"])}</dd>
                <dt>Woran du merkst, dass es wirkt</dt><dd>{esc(b["messung"])}</dd>
                <dt class="gegen">Was dabei nicht kaputtgehen darf</dt><dd>{esc(b["gegen"])}</dd>
              </dl>
            </div>
          </div>
        </article>
        </section>""")
    hebel_summe = sum(b["hebel"] for b in befunde if b["hebel"])

    # Retouren ohne Grund sind kein Geschäftsbefund, sondern eine Datenqualitätsaussage.
    # Sie gehört als Warnung an die Gründe-Auswertung, nicht in die Befundliste.
    og = next((f for f in d.get("blinde_flecken", []) if "keinen brauchbaren Grund" in f["titel"]), None)
    datenqualitaet = ""
    if og:
        datenqualitaet = (
            f'<div class="warnung"><span class="mini-lbl">Datenqualität</span>'
            f'Bei {num(og["anzahl"])} Retouren ({pct(og["anteil"])} aller Fälle) wurde kein verwertbarer '
            f'Grund erfasst. Die Verteilung unten ist entsprechend unsicher, und die Lücken verteilen '
            f'sich selten gleichmäßig. Lohnt zu prüfen, ob sie sich auf einzelne Artikel oder '
            f'Rückgabewege häufen, dort steckt dann meist ein eigener Fall.</div>')

    # --- Annahmen und fehlende Spalten, in Klartext
    ERKLAERT = {
        "delivered_date": ("Zustelldatum",
                           "Damit ließe sich messen, wie viele Tage zwischen Zustellung und Rücksendung "
                           "liegen. Sehr späte Rücksendungen kurz vor Fristende sind ein anderer Fall als "
                           "sofortige, und getragene Ware kommt typischerweise spät zurück."),
        "batch": ("Chargennummer",
                  "Damit wäre ein Qualitäts-Ausschlag eindeutig einer Lieferung zuzuordnen. Ohne sie "
                  "bleibt es bei der zeitlichen Vermutung: viele Defekte in einem Monat, vermutlich "
                  "dieselbe Charge."),
        "refund_type": ("Art der Erstattung",
                        "Also ob der Kunde Geld zurückbekam, einen Gutschein nahm oder umtauschte. "
                        "Damit ließe sich rechnen, wie viel Umsatz bei einer Retoure tatsächlich "
                        "verloren geht und wie viel im Haus bleibt."),
        "condition": ("Zustand der Rückware",
                      "Also ob der Artikel wieder als neu verkauft werden kann, als B-Ware rausgeht "
                      "oder entsorgt wird. Damit wäre der Wertverlust echt gerechnet statt geschätzt."),
    }
    annahmen = "".join(f"<li>{esc(a)}</li>" for a in meta["annahmen"])
    fehlend = ""
    for m in meta["fehlende_spalten"]:
        name, erkl = ERKLAERT.get(m["spalte"], (m["spalte"], m["entfallene_analyse"]))
        fehlend += (f'<li><strong>{esc(name)}</strong> <code>{esc(m["spalte"])}</code><br>{esc(erkl)}</li>')

    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titel)}</title>
<style>
  :root {{
    --paper: {PAPER}; --ink: {INK}; --serie: {EMERALD}; --moss: {MOSS}; --signal: {SIGNAL};
    --bg: var(--paper); --text: var(--ink); --panel: #fff; --linie: rgba(8,58,42,.12);
    --gedaempft: rgba(8,58,42,.62); --moss-flaeche: {MOSS}; --paper-fest: {PAPER};
    --overlay: #fff;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: {INK}; --text: {PAPER}; --serie: {EMERALD_HELL};
      --panel: rgba(212,237,224,.06); --linie: rgba(212,237,224,.16); --gedaempft: rgba(250,250,247,.66);
      --moss-flaeche: rgba(212,237,224,.14); --overlay: #0C4634; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
    font-family: ui-sans-serif, system-ui, "Inter", sans-serif; line-height: 1.55;
    font-feature-settings: "tnum" 1; }}
  .wrap {{ max-width: 1120px; margin: 0 auto; padding: 48px 24px 80px; }}
  .eyebrow {{ font-family: ui-monospace, "JetBrains Mono", monospace; font-size: 11px;
    letter-spacing: .14em; text-transform: uppercase; color: var(--gedaempft); margin: 0 0 10px; }}
  h1 {{ font-size: 30px; line-height: 1.2; margin: 0 0 6px; font-weight: 600; letter-spacing: -.01em; }}
  h1 .punkt {{ color: var(--signal); }}
  .meta {{ color: var(--gedaempft); font-size: 14px; margin: 0 0 40px; }}
  h2 {{ font-size: 19px; margin: 46px 0 4px; font-weight: 600; letter-spacing: -.005em; }}
  h2 + .hint {{ color: var(--gedaempft); font-size: 14px; margin: 0 0 18px; }}
  .kacheln {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; }}
  .kachel {{ background: var(--panel); border: 1px solid var(--linie); padding: 18px 18px 16px; }}
  .kachel.akzent {{ border-top: 3px solid var(--signal); }}
  .klabel {{ font-family: ui-monospace, monospace; font-size: 10.5px; letter-spacing: .12em;
    text-transform: uppercase; color: var(--gedaempft); }}
  .kwert {{ font-size: 32px; font-weight: 600; letter-spacing: -.02em; margin-top: 6px; }}
  .zusatz {{ font-size: 13px; color: var(--gedaempft); margin-top: 2px; }}
  /* Der Erklaertext haengt an der Kachel, nicht am Fragezeichen: so ist er genau so breit wie
     sie, kann seitlich nicht aus dem Fenster laufen, und die ganze Kachel ist die Hoverflaeche.
     Ein 14px-Ziel zu treffen und dann ueber eine Luecke nachzufassen war unbedienbar. */
  .kachel {{ position: relative; }}
  .info {{ display: inline-flex; align-items: center; justify-content: center; width: 15px;
           height: 15px; margin-left: 6px; border: 1px solid var(--linie); border-radius: 50%;
           font-size: 10px; line-height: 1; color: var(--gedaempft); cursor: help;
           vertical-align: middle; letter-spacing: 0; }}
  .kachel:hover .info, .info:focus-visible {{ color: var(--text); border-color: var(--text); }}
  .info-text {{ position: absolute; top: calc(100% + 6px); left: -1px; right: -1px;
                background: var(--overlay); color: var(--text); border: 1px solid var(--linie);
                padding: 12px 14px; font-family: ui-sans-serif, system-ui, "Inter", sans-serif;
                font-size: 13px; line-height: 1.5;
                letter-spacing: 0; text-transform: none; font-weight: 400; text-align: left;
                opacity: 0; visibility: hidden; transition: opacity .12s; z-index: 30;
                box-shadow: 0 8px 28px rgba(0,0,0,.16); }}
  /* focus-visible statt focus: ein Mausklick auf das Fragezeichen setzt sonst den Fokus und
     der Kasten bleibt offen, bis man irgendwo anders hinklickt. Mit der Tastatur geht er auf. */
  .kachel:hover .info-text, .info:focus-visible .info-text {{ opacity: 1; visibility: visible; }}
  /* Ohne Hover (Touch) gibt es nichts zum Draufzeigen. Dort steht der Text einfach fest da. */
  @media (hover: none) {{
    .info {{ display: none; }}
    .info-text {{ position: static; opacity: 1; visibility: visible; margin-top: 10px;
                  box-shadow: none; background: none; border: 0; padding: 0; font-size: 12px;
                  color: var(--gedaempft); }}
  }}
  .wasserfall td:first-child {{ text-align: left; }}
  .wasserfall tr.summe td {{ font-weight: 600; border-top: 1px solid var(--text); }}
  .wasserfall tr.abzug td.zahl {{ color: var(--gedaempft); }}
  .befund-karte {{ background: var(--panel); border: 1px solid var(--linie); }}
  .bk-kopf {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
    padding: 16px 22px; border-bottom: 1px solid var(--linie); }}
  .bk-nr {{ font-family: ui-monospace, monospace; font-size: 12px; color: var(--signal); }}
  .bk-kopf h3 {{ font-size: 17px; margin: 0; font-weight: 600; flex: 1 1 260px; letter-spacing: -.005em; }}
  .bk-hebel {{ font-family: ui-monospace, monospace; font-size: 12px; color: var(--text);
    background: var(--moss-flaeche); padding: 5px 10px; white-space: nowrap; }}
  .bk-body {{ display: grid; grid-template-columns: 1fr 1fr; gap: 26px; padding: 20px 22px 22px; }}
  @media (max-width: 720px) {{ .bk-body {{ grid-template-columns: 1fr; gap: 14px; }} }}
  .bk-spalte p {{ margin: 0 0 12px; }}
  .bk-spalte ol {{ margin: 0 0 14px; padding-left: 20px; }}
  .bk-spalte li {{ margin-bottom: 6px; }}
  .mini-lbl {{ display: block; font-family: ui-monospace, monospace; font-size: 10px;
    letter-spacing: .12em; text-transform: uppercase; color: var(--gedaempft);
    margin: 0 0 4px !important; }}
  .unsichtbar, .beleg {{ font-size: 13.5px; color: var(--gedaempft); border-left: 2px solid var(--linie);
    padding-left: 12px; }}
  .bk-meta {{ margin: 0; font-size: 13.5px; }}
  .bk-meta dt {{ font-family: ui-monospace, monospace; font-size: 10px; letter-spacing: .1em;
    text-transform: uppercase; color: var(--gedaempft); margin-top: 10px; }}
  .bk-meta dt.gegen {{ color: var(--signal); }}
  .bk-meta dd {{ margin: 2px 0 0; }}
  .chart {{ width: 100%; height: auto; overflow: visible; margin-top: 6px; }}
  .chart .lbl {{ font-size: 13px; fill: var(--text); }}
  .chart .val {{ font-size: 12.5px; fill: var(--gedaempft); }}
  .chart .mini {{ font-size: 10px; fill: var(--signal); font-family: ui-monospace, monospace; }}
  .chart .mitte {{ text-anchor: middle; }}
  .chart .mark {{ transition: opacity .12s; }}
  .chart .mark:hover {{ opacity: .72; }}
  .tabelle-wrap {{ overflow-x: auto; margin-top: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; min-width: 760px; }}
  th, td {{ text-align: left; padding: 10px 18px 10px 0; border-bottom: 1px solid var(--linie);
    vertical-align: top; }}
  th:last-child, td:last-child {{ padding-right: 0; }}
  th {{ font-family: ui-monospace, monospace; font-size: 10.5px; letter-spacing: .1em;
    text-transform: uppercase; color: var(--gedaempft); font-weight: 400; }}
  td.zahl, th.zahl {{ text-align: right; white-space: nowrap; padding-left: 22px; }}
  td.neg {{ color: var(--signal); font-weight: 600; }}
  .fuss {{ margin-top: 56px; padding-top: 22px; border-top: 1px solid var(--linie);
    font-size: 13.5px; color: var(--gedaempft); }}
  .fuss ul {{ margin: 6px 0 18px; padding-left: 18px; }}
  .leer {{ color: var(--gedaempft); font-size: 14px; }}
  .befund-gruppe {{ margin-bottom: 42px; }}
  .metrik {{ padding: 0 0 20px; }}
  .metrik-titel {{ font-size: 15px; font-weight: 600; margin: 0 0 2px; }}
  .metrik-hint {{ font-size: 13.5px; color: var(--gedaempft); margin: 0 0 14px; max-width: 720px; }}
  .metrik .chart {{ max-width: 820px; }}
  .warnung {{ background: var(--moss-flaeche); border-left: 3px solid var(--signal);
    padding: 14px 18px; margin: 10px 0 18px; font-size: 14px; }}
  .chart .val-inv {{ font-size: 12.5px; fill: var(--paper-fest); font-weight: 600; }}
  /* Zwei feste Spalten mit Trennlinie je Eintrag. Vorher lief das ueber auto-fit, dann standen
     Begriff und Erklaerung nicht auf einer Hoehe und man sah nicht, was zusammengehoert. */
  .glossar {{ margin: 8px 0 0; display: grid; grid-template-columns: minmax(190px, 290px) 1fr;
    column-gap: 32px; font-size: 14px; }}
  .glossar dt {{ grid-column: 1; font-weight: 600; margin: 0;
    border-top: 1px solid var(--linie); padding: 18px 0 18px; }}
  .glossar dd {{ grid-column: 2; margin: 0; color: var(--gedaempft);
    border-top: 1px solid var(--linie); padding: 18px 0 18px; }}
  @media (max-width: 720px) {{
    .glossar {{ grid-template-columns: 1fr; }}
    .glossar dt {{ padding-bottom: 6px; }}
    .glossar dd {{ border-top: 0; padding-top: 0; padding-bottom: 18px; }}
  }}
  /* Die Formel steht unter dem Begriff, nicht im Fliesstext: so ist auf einen Blick klar,
     was durch was geteilt wird, ohne dass der Erklaertext damit anfangen muss. */
  .dt-formel {{ display: block; font-family: ui-monospace, monospace; font-size: 12px;
    font-weight: 400; color: var(--gedaempft); margin-top: 3px; }}
  .glossar dd em {{ font-style: normal; font-weight: 600; color: var(--text); }}
  .glossar dd strong {{ color: var(--text); font-weight: 600; }}
  .glossar dd ul {{ margin: 8px 0; padding-left: 18px; }}
  .glossar dd li {{ margin-bottom: 4px; }}
  .dd-wofuer {{ display: block; margin-top: 8px; }}
  .dd-hinweis {{ display: block; margin-top: 8px; padding-left: 10px;
    border-left: 2px solid var(--linie); font-size: 13px; }}
  .fuss ul.fehlend li {{ margin-bottom: 9px; }}
  code {{ font-family: ui-monospace, monospace; font-size: .92em; }}
</style></head>
<body>
<div class="wrap">
  <p class="eyebrow">Retouren-Analyse</p>
  <h1>{esc(titel)}<span class="punkt">.</span></h1>
  <p class="meta">{num(meta["retouren_positionen"])} Retouren-Positionen aus {num(meta["bestellungen"])} Bestellungen ·
     Datenstand {esc(meta["zeitraum_bis"])}</p>

  <div class="kacheln">{"".join(kacheln)}</div>

  <h2>Vom Umsatz zum Rohertrag nach Retouren</h2>
  <p class="hint">Jede Zeile ist nachrechenbar. Der erstattete Umsatz geht ab, der Einkaufswert der
     zurückgekommenen Ware aber nicht: Die liegt wieder im Lager. Abgezogen wird nur, was wirklich
     weg ist. Nicht enthalten sind Versand, Verpackung, Zahlungsgebühren, Marketing und alle
     Fixkosten. Der Rohertrag nach Retouren ist deshalb kein Gewinn.</p>
  <div class="tabelle-wrap"><table class="wasserfall"><tbody>{wasserfall}</tbody></table></div>

  <h2>Retourenquote je Bestellmonat</h2>
  <p class="hint">Jede Retoure zählt zu dem Monat, in dem bestellt wurde, nicht zu dem, in dem sie
     eintrifft. Nur so sind Monate vergleichbar. Bei den jüngsten Monaten fehlen noch Retouren; dort
     steht der dunkle Balken für das, was da ist, und die gestrichelte Linie für den erwarteten Endwert,
     hochgerechnet aus dem zeitlichen Verlauf der abgeschlossenen Monate.</p>
  {kohorten_chart(q["je_kohorte"])}

  <h2>Befunde und was zu tun ist</h2>
  <p class="hint">Nach Geldwert sortiert, der teuerste Befund zuerst.</p>
  {"".join(karten)}

  <h2>Retourengründe</h2>
  <p class="hint">Gezählt in <strong>Retourenpositionen</strong>, also je zurückgeschicktem Artikel.
     Eine Sendung mit drei Artikeln zählt hier dreimal.</p>
  {datenqualitaet}
  {chart_gruende}

  <h2>Artikel im Detail</h2>
  <p class="hint">Die drei mittleren Spalten ergeben addiert die Retourenkosten, und Rohertrag minus
     Retourenkosten ergibt den Rohertrag nach Retouren. Der erstattete Umsatz steht bewusst nicht in
     der Rechnung: Die Ware kommt zurück ins Lager, verloren ist nur die Marge darauf. Nur als
     defekt gemeldete Stücke werden voll abgeschrieben.</p>
  <div class="tabelle-wrap"><table><thead><tr><th>Artikel</th><th>Variante</th><th class="zahl">Retouren</th>
    <th class="zahl">Rohertrag vor Retouren</th><th class="zahl">entgangene Marge</th><th class="zahl">Bearbeitung</th>
    <th class="zahl">Abschreibung</th><th class="zahl">Retourenkosten</th>
    <th class="zahl">Rohertrag nach Retouren</th></tr></thead><tbody>
    {"".join(f'<tr><td>{esc(c["name"])}</td><td><code>{esc(c["sku"])}</code></td>'
             f'<td class="zahl">{num(c["retouren_vorgaenge"])}</td>'
             f'<td class="zahl">{esc(eur(c.get("deckungsbeitrag_vor_retouren")))}</td>'
             f'<td class="zahl">{esc(eur(c["entgangene_marge"]) if c.get("entgangene_marge") is not None else "n/a")}</td>'
             f'<td class="zahl">{esc(eur(c["prozesskosten"]))}</td>'
             f'<td class="zahl">{esc(eur(c["wertverlust_defekt"]))}</td>'
             f'<td class="zahl">{esc(eur(c["gesamt"]))}</td>'
             f'<td class="zahl{" neg" if (c.get("deckungsbeitrag_nach_retouren") or 0) < 0 else ""}">'
             f'{esc(eur(c["deckungsbeitrag_nach_retouren"]) if c.get("deckungsbeitrag_nach_retouren") is not None else "n/a")}</td></tr>'
             for c in kosten)}
  </tbody></table></div>

  <h2>Die drei Retourenquoten</h2>
  <p class="hint">Dieselben Retouren, auf drei verschiedene Bezugsgrößen bezogen. Die Bezeichnungen
     stammen aus der Retourenforschung der Universität Bamberg (Asdecker) und sind im deutschen
     Onlinehandel gebräuchlich.</p>
  <dl class="glossar">
    <dt>Alpha-Retourenquote<span class="dt-formel">zurückgesendete Sendungen ÷ versendete Sendungen</span></dt>
    <dd>Anteil der zurückgesendeten Sendungen an allen versendeten Sendungen. Bezugsgröße ist der
        Versandvorgang, unabhängig von Inhalt und Warenwert. Sie ist die Planungsgröße für die
        Retourenbearbeitung, weil der Aufwand im Wareneingang je Sendung anfällt und nicht je Artikel.
        Sie liegt systembedingt über der Beta-Quote, da bereits ein einzelner zurückgesendeter Artikel
        die gesamte Sendung als Retoure ausweist.
        <span class="dd-hinweis">In diesem Report auf Bestellungen berechnet, weil der Export keine
        Sendungen ausweist. Bei Teillieferungen weichen beide Größen voneinander ab.</span></dd>
    <dt>Beta-Retourenquote<span class="dt-formel">retournierte Artikel ÷ versendete Artikel</span></dt>
    <dd>Anteil der retournierten Artikel an allen versendeten Artikeln. Bezugsgröße ist die Stückzahl,
        der Warenwert bleibt unberücksichtigt. Sie lässt sich je Artikel berechnen und ist damit die
        Kennzahl für die Ursachenanalyse auf Produktebene.</dd>
    <dt>Gamma-Retourenquote<span class="dt-formel">Wert der Retouren ÷ Wert der versendeten Ware</span></dt>
    <dd>Anteil des retournierten Warenwerts am gesamten versendeten Warenwert. Bezugsgröße ist der
        Wert, die Stückzahl bleibt unberücksichtigt. Sie beziffert die Erlösschmälerung und das in
        Rückläufern gebundene Kapital. Im Verhältnis zur Beta-Quote zeigt sie außerdem, ob
        überdurchschnittlich teure oder überdurchschnittlich günstige Artikel zurückgehen: Liegt die
        Gamma-Quote höher, sind die Rückläufer im Schnitt wertvoller als das versendete Sortiment.</dd>
  </dl>

  <h2>Weitere Begriffe</h2>
  <dl class="glossar">
    <dt>Kohortensicht (Bestellmonat statt Retourenmonat)</dt>
    <dd>Zuordnung jeder Retoure zu dem Monat, in dem die zugehörige Bestellung aufgegeben wurde, nicht
        zu dem Monat des Retoureneingangs. Nur so beziehen sich Zähler und Nenner auf denselben
        Vorgang und Monate werden vergleichbar. Nachteil: Die jüngsten Monate sind noch unvollständig
        und werden entsprechend gekennzeichnet.</dd>
    <dt>Reifegrad</dt>
    <dd>Anteil des Rückgabefensters, der für einen Bestellmonat bereits abgelaufen ist. Erst bei
        vollem Reifegrad ist die Quote endgültig. Unvollständige Monate weisen eine zu niedrige Quote
        aus, weil ausstehende Retouren fehlen.</dd>
    <dt>Rohertrag vor Retouren</dt>
    <dd>Umsatz der versendeten Ware abzüglich des zugehörigen Wareneinsatzes, ohne Berücksichtigung
        von Retouren. Dient als Vergleichswert, um die Wirkung der Retouren sichtbar zu machen.</dd>
    <dt>Rohertrag nach Retouren</dt>
    <dd>Umsatz abzüglich Wareneinsatz der vom Kunden behaltenen Ware, abzüglich Retourenbearbeitung
        und abgeschriebener Defektware. Nicht enthalten sind Versand, Verpackung, Zahlungsgebühren
        und Marketing; die Kennzahl entspricht damit keinem vollständigen DB2 und keinem Gewinn. Ein
        negativer Wert bedeutet, dass der Artikel im Zeitraum mehr gekostet als eingebracht hat.</dd>
    <dt>Retourenkosten</dt>
    <dd>Entgangene Marge der retournierten Artikel zuzüglich Bearbeitungskosten je Retourenvorgang und
        Wertverlust bei defekter Ware. Der erstattete Umsatz ist nicht enthalten, da die Ware dem
        Bestand wieder zugeht. Der Bearbeitungssatz ist eine Annahme und unten ausgewiesen.</dd>
    <dt>Entgangene Marge</dt>
    <dd>Rohertrag, den ein Artikel erwirtschaftet hätte, wäre er nicht retourniert worden. Sie ist der
        tatsächlich verlorene Anteil einer Retoure. Wird stattdessen die volle Erstattung als Kosten
        angesetzt, werden die Retourenkosten überzeichnet, besonders deutlich bei Artikeln mit
        geringer Marge.</dd>
    <dt>Retourenposition und Sendung</dt>
    <dd>Eine Retourenposition ist ein einzelner zurückgesendeter Artikel, eine Sendung das zugehörige
        Paket. Eine Sendung mit drei Artikeln entspricht drei Positionen. Die Auswertung der
        Retourengründe erfolgt je Position, die nicht abgeholten Fälle werden je Sendung gezählt.</dd>
    <dt>Mehrgrößen-Bestellung (Bracketing)</dt>
    <dd>Bestellung von zwei oder mehr Größen desselben Artikels mit der Absicht, einen Teil davon
        zurückzusenden. Gilt als eingeplante Retoure. Maßnahmen zur Größenberatung sind gegen diese
        Kennzahl zu messen, da eine sinkende Retourenquote bei gleichzeitig steigenden
        Mehrgrößen-Bestellungen keinen Vorteil ergibt.</dd>
    <dt>Mindest-N</dt>
    <dd>Mindestanzahl an Retouren, ab der ein Artikel in die Auswertung aufgenommen wird. Quoten aus
        sehr kleinen Fallzahlen sind statistisch nicht belastbar. Artikel unterhalb der Schwelle
        erscheinen in keiner Rangliste; ihre Anzahl wird im Report ausgewiesen.</dd>
    <dt>Nicht abgeholte Sendung und Annahmeverweigerung</dt>
    <dd>Rücklauf einer Sendung, ohne dass sie beim Empfänger geöffnet wurde, weil sie im Paketshop
        nicht abgeholt oder bei Zustellung abgelehnt wurde. Rechtlich kein Widerruf. Wirtschaftlich
        die aufwendigste Form der Retoure, da Hin- und Rückversand anfallen, der Umsatz vollständig
        entfällt und kein Umtausch zustande kommt. In der Versandstatistik erscheint der Vorgang als
        Zustellung mit anschließender Rücksendung und ist nur im Retourendatensatz erkennbar.</dd>
  </dl>

  <div class="fuss">
    <strong>Annahmen</strong><ul>{annahmen}</ul>
    <strong>Was mit weiteren Spalten im Export möglich wäre</strong><ul class="fehlend">{fehlend}</ul>
    <p>Jede Zahl stammt aus <code>analysis.json</code>. Nichts davon ist geschätzt.</p>
  </div>
</div>
</body></html>"""


def main():
    p = argparse.ArgumentParser(description="Dashboard aus analysis.json bauen")
    p.add_argument("--analyse", default="analysis.json")
    p.add_argument("--out", default="dashboard.html")
    p.add_argument("--titel", default="Retouren-Report")
    a = p.parse_args()

    with open(a.analyse, encoding="utf-8") as f:
        d = json.load(f)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(build(d, a.titel))
    print(f"OK: {a.out} geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
