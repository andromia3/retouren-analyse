#!/usr/bin/env python3
"""Retouren-Analyse: deterministische Berechnung aller Kennzahlen und Muster.

Das Script rechnet, die AI interpretiert. Ausgabe ist ein analysis.json,
aus dem der Report geschrieben wird. Nur Python-Stdlib.
"""
# naming-lint: schema (deutsche Handels- und Buchhaltungsbegriffe, 64 von 131 Schluesseln: Retourenquote, Rohertrag, Zahlart; keine brauchbare Uebersetzung, und dashboard.py plus analysis.json lesen sie)
# brauchbare Uebersetzung, und dashboard.py plus analysis.json lesen sie.)

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

# Kanonische Gruende; Normalisierung deckt deutsche ERP-Exporte und Shopify-Enums ab
REASON_MAP = {
    "zu klein": "zu_klein",
    "zu klein / eng": "zu_klein",
    "size_too_small": "zu_klein",
    "zu gross": "zu_gross",
    "zu groß": "zu_gross",
    "zu gross / weit": "zu_gross",
    "size_too_large": "zu_gross",
    "passform": "passform_schnitt",
    "schnitt gefaellt nicht": "passform_schnitt",
    "style": "passform_schnitt",
    "gefaellt nicht": "farbe_optik_gefaellt_nicht",
    "gefällt nicht": "farbe_optik_gefaellt_nicht",
    "farbe weicht ab": "farbe_optik_gefaellt_nicht",
    "color": "farbe_optik_gefaellt_nicht",
    "entspricht nicht dem foto": "nicht_wie_beschrieben",
    "entspricht nicht der beschreibung": "nicht_wie_beschrieben",
    "not_as_described": "nicht_wie_beschrieben",
    "defekt": "qualitaet_defekt",
    "mangelhafte qualitaet": "qualitaet_defekt",
    "mangelhafte qualität": "qualitaet_defekt",
    "defective": "qualitaet_defekt",
    "beschaedigt angekommen": "transportschaden",
    "beschädigt angekommen": "transportschaden",
    "transportschaden": "transportschaden",
    "falscher artikel": "falscher_artikel",
    "wrong_item": "falscher_artikel",
    "zu spaet geliefert": "zu_spaet_geliefert",
    "zu spät geliefert": "zu_spaet_geliefert",
    "nicht mehr benoetigt": "reue_nicht_benoetigt",
    "nicht mehr benötigt": "reue_nicht_benoetigt",
    "unwanted": "reue_nicht_benoetigt",
    "nicht abgeholt": "nicht_abgeholt_annahme_verweigert",
    "annahme verweigert": "nicht_abgeholt_annahme_verweigert",
    "unknown": "sonstiges_unbekannt",
    "other": "sonstiges_unbekannt",
    "": "sonstiges_unbekannt",
}

SIZE_REASONS = {"zu_klein", "zu_gross"}
CONTENT_REASONS = {"nicht_wie_beschrieben", "farbe_optik_gefaellt_nicht"}


def parse_date(value):
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value.strip()[: len(fmt) + 2], fmt)
        except (ValueError, AttributeError):
            continue
    return None


def to_float(value):
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 0.0


def de(x):
    """Prozentwert in deutscher Schreibweise, etwa 0.176 -> "17,6 Prozent"."""
    return f"{x * 100:.1f}".replace(".", ",") + " Prozent"


def month_key(dt):
    return f"{dt.year:04d}-{dt.month:02d}"


def normalize_reason(raw):
    return REASON_MAP.get((raw or "").strip().lower(), "sonstiges_unbekannt")


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def analyze(returns_rows, sales_rows, args):
    assumptions = [
        f"Prozesskostensatz {args.prozesskosten:.2f} EUR je Retouren-Vorgang (EHI-Kernbereich 5 bis 20 EUR, anpassbar)",
        f"Rückgabefenster {args.rueckgabefenster} Tage, Reifepuffer {args.reifepuffer} Tage",
        f"Mindest-N je SKU: {args.min_retouren} Retouren",
        "Retourenkosten = entgangene Marge der zurückgeschickten Stücke plus Prozesskosten plus "
        "abgeschriebene Defektware. Der erstattete Umsatz zählt nicht als Kosten, weil die Ware "
        "wieder ins Lager geht; als defekt gemeldete Stücke werden voll abgeschrieben.",
    ]
    warnings = []

    # ---- Verkaufsbasis indizieren
    orders = defaultdict(list)          # order -> sale positions
    sku_sold = Counter()
    sku_revenue = defaultdict(float)
    sku_name = {}
    sku_unit_cost = {}
    order_month = {}
    order_dates = {}
    order_payment = {}
    order_channel = {}
    customer_orders = defaultdict(set)
    total_shipped_qty = 0
    total_shipped_value = 0.0

    for row in sales_rows:
        oid = row.get("sales_order_number", "").strip()
        d = parse_date(row.get("order_date", ""))
        if not oid or d is None:
            continue
        qty = to_float(row.get("quantity")) or 1.0
        rev = to_float(row.get("net_revenue"))
        sku = row.get("product_number", "").strip()
        orders[oid].append(row)
        order_month[oid] = month_key(d)
        order_dates[oid] = d
        order_payment[oid] = row.get("payment_method", "").strip() or "unbekannt"
        order_channel[oid] = row.get("channel", "").strip() or "unbekannt"
        cust = row.get("customer_number", "").strip()
        if cust:
            customer_orders[cust].add(oid)
        sku_sold[sku] += qty
        sku_revenue[sku] += rev
        sku_name.setdefault(sku, row.get("product_name", sku))
        if row.get("unit_cost"):
            sku_unit_cost[sku] = to_float(row.get("unit_cost"))
        total_shipped_qty += qty
        total_shipped_value += rev

    # ---- Retouren durchgehen
    max_date = None
    ret_qty_by_cohort = Counter()
    ret_value_by_cohort = defaultdict(float)
    orders_with_return = set()
    sku_returned = Counter()
    sku_refund = defaultdict(float)
    sku_return_events = Counter()
    sku_defect_qty = Counter()
    reason_counter = Counter()
    sku_reasons = defaultdict(Counter)
    style_size_reasons = defaultdict(lambda: defaultdict(Counter))  # style -> size -> reason
    customer_return_orders = defaultdict(set)
    customer_return_count = Counter()
    nonpickup = []
    return_latencies = []   # (Tage zwischen Bestellung und Retoure, Bestellmonat)
    defect_by_sku_month = defaultdict(Counter)
    unmatched_orders = 0
    # Eine nicht abgeholte Sendung ist keine Retoure: rechtlich kein Widerruf, und die Ware
    # wurde nie ausgepackt. Sie kostet trotzdem Geld und bleibt deshalb in der Kostenrechnung.
    # Fuer die ausgewiesene Retourenquote wird sie getrennt gezaehlt, sonst meldet der Report
    # eine Quote, die der Haendler so nirgends wiedererkennt.
    ret_qty_customer = 0.0
    ret_qty_nonpickup = 0.0
    ret_value_customer = 0.0
    orders_with_customer_return = set()

    for row in returns_rows:
        oid = row.get("sales_order_number", "").strip()
        d = parse_date(row.get("return_date", ""))
        if d and (max_date is None or d > max_date):
            max_date = d
        qty = to_float(row.get("quantity_returned")) or 1.0
        sku = row.get("product_number", "").strip()
        refund = to_float(row.get("refund_amount"))
        reason = normalize_reason(row.get("return_reason"))
        rtype = (row.get("return_type", "") or "").strip().lower()
        if rtype in ("nicht_abgeholt", "annahme_verweigert", "not_picked_up"):
            reason = "nicht_abgeholt_annahme_verweigert"

        cohort = order_month.get(oid)
        if cohort is None:
            unmatched_orders += 1
        else:
            od = order_dates.get(oid)
            if od and d:
                return_latencies.append(((d - od).days, cohort))
            orders_with_return.add(oid)
            # Die Kohorten-Tabelle muss dieselbe Groesse messen wie die Retourenquote oben,
            # sonst steht im Kopf 14 Prozent und in der Zeile darunter 17.
            if reason != "nicht_abgeholt_annahme_verweigert":
                ret_qty_by_cohort[cohort] += qty
                ret_value_by_cohort[cohort] += refund
                orders_with_customer_return.add(oid)

        if reason == "nicht_abgeholt_annahme_verweigert":
            ret_qty_nonpickup += qty
        else:
            ret_qty_customer += qty
            ret_value_customer += refund

        sku_returned[sku] += qty
        sku_refund[sku] += refund
        sku_return_events[sku] += 1
        reason_counter[reason] += 1
        sku_reasons[sku][reason] += 1

        style = row.get("product_name", sku)
        size = (row.get("variant_size", "") or "").strip()
        if size and reason in SIZE_REASONS:
            style_size_reasons[style][size][reason] += 1

        cust = row.get("customer_number", "").strip()
        if cust:
            customer_return_orders[cust].add(oid)
            customer_return_count[cust] += 1

        if reason == "nicht_abgeholt_annahme_verweigert":
            nonpickup.append({"order": oid, "refund": refund, "sku": sku, "qty": qty,
                              "payment": order_payment.get(oid, row.get("payment_method", "unbekannt"))})
        if reason == "qualitaet_defekt" and d:
            defect_by_sku_month[style][month_key(d)] += qty
            sku_defect_qty[sku] += qty

    if unmatched_orders:
        warnings.append(
            f"{unmatched_orders} Retouren-Positionen ohne Treffer in der Verkaufsbasis; "
            "Quoten könnten untererfasst sein, bitte den Zeitraum des Verkaufs-Exports prüfen."
        )
    today = max_date or datetime.now()

    # ---- Kohorten-Quoten
    cohort_sold_qty = Counter()
    cohort_sold_value = defaultdict(float)
    cohort_orders = Counter()
    cohort_orders_ret = Counter()
    for oid, rows in orders.items():
        ck = order_month[oid]
        cohort_orders[ck] += 1
        if oid in orders_with_customer_return:
            cohort_orders_ret[ck] += 1
        for r in rows:
            cohort_sold_qty[ck] += to_float(r.get("quantity")) or 1.0
            cohort_sold_value[ck] += to_float(r.get("net_revenue"))

    # Reifekurve: Wie viel Prozent der Retouren eines Bestellmonats sind nach X Tagen da?
    # Abgeleitet aus den abgeschlossenen Monaten, danach Hochrechnung der jungen.
    lat_reif = []           # Latenzen (Tage) aus reifen Kohorten
    cohort_mature_flag = {}
    for ck in sorted(cohort_sold_qty):
        year, month = int(ck[:4]), int(ck[5:7])
        month_end = datetime(year + (month == 12), (month % 12) + 1, 1)
        cohort_mature_flag[ck] = month_end + timedelta(days=args.rueckgabefenster + args.reifepuffer) <= today
    for lat, ck in return_latencies:
        if cohort_mature_flag.get(ck):
            lat_reif.append(lat)
    lat_reif.sort()

    def reifegrad(tage):
        """Anteil der Retouren, der nach so vielen Tagen typischerweise da ist."""
        if not lat_reif or tage is None:
            return None
        n = sum(1 for l in lat_reif if l <= tage)
        return n / len(lat_reif)

    cohorts = []
    for ck in sorted(cohort_sold_qty):
        year, month = int(ck[:4]), int(ck[5:7])
        month_start = datetime(year, month, 1)
        month_end = datetime(year + (month == 12), (month % 12) + 1, 1)
        mature = cohort_mature_flag[ck]
        sold_q, sold_v = cohort_sold_qty[ck], cohort_sold_value[ck]
        beta = ret_qty_by_cohort[ck] / sold_q if sold_q else None
        eintrag = {
            "kohorte": ck,
            "beta_quote": round(beta, 4) if beta is not None else None,
            "gamma_quote": round(ret_value_by_cohort[ck] / sold_v, 4) if sold_v else None,
            "bestell_quote": round(cohort_orders_ret[ck] / cohort_orders[ck], 4) if cohort_orders[ck] else None,
            "mature": mature,
        }
        if not mature and beta is not None:
            # mittleres Bestellalter dieser Kohorte zum Datenstand
            mitte = month_start + (min(month_end, today) - month_start) / 2
            alter = (today - mitte).days
            grad = reifegrad(alter)
            if grad and grad > 0.15:
                eintrag["reifegrad"] = round(grad, 3)
                eintrag["beta_hochgerechnet"] = round(beta / grad, 4)
        cohorts.append(eintrag)

    # ---- SKU-Quoten mit Mindest-N
    sku_rates = []
    for sku, ret in sku_returned.items():
        sold = sku_sold.get(sku, 0)
        entry = {
            "sku": sku, "name": sku_name.get(sku, sku),
            "verkauft": sold, "retourniert": ret,
            "beta_quote": round(ret / sold, 4) if sold else None,
            "unter_mindest_n": ret < args.min_retouren or sold < 10,
            "top_gruende": dict(sku_reasons[sku].most_common(3)),
        }
        sku_rates.append(entry)
    sku_rates.sort(key=lambda e: (e["beta_quote"] or 0), reverse=True)
    rankable = [e for e in sku_rates if not e["unter_mindest_n"]]

    # ---- Groessen-Laeufer
    size_runners = []
    for style, sizes in style_size_reasons.items():
        klein = sum(c["zu_klein"] for c in sizes.values())
        gross = sum(c["zu_gross"] for c in sizes.values())
        total = klein + gross
        # Schwelle bewusst hoch: ein Groessen-Laeufer ist ein klares Ungleichgewicht,
        # kein leichtes Uebergewicht. Sonst wird jeder Artikel gemeldet.
        if total >= 25 and max(klein, gross) >= 3 * max(1, min(klein, gross)):
            size_runners.append({
                "style": style, "zu_klein": klein, "zu_gross": gross,
                "richtung": "fällt klein aus" if klein > gross else "fällt groß aus",
                "je_groesse": {s: dict(c) for s, c in sorted(sizes.items())},
            })
    size_runners.sort(key=lambda e: e["zu_klein"] + e["zu_gross"], reverse=True)

    # ---- Bracketing
    bracketing_orders = 0
    bracketing_with_return = 0
    for oid, rows in orders.items():
        by_style = defaultdict(set)
        for r in rows:
            size = (r.get("variant_size", "") or "").strip()
            if size:
                by_style[r.get("product_name", "")].add(size)
        if any(len(s) > 1 for s in by_style.values()):
            bracketing_orders += 1
            if oid in orders_with_return:
                bracketing_with_return += 1

    # ---- Serien-Retournierer (Review-Liste, keine Sanktion)
    # Schwellen bewusst konservativ: OTTO greift laut eigener Auskunft erst bei rund 90 Prozent
    # Retourenquote ein, und der real gemessene Missbrauchsanteil (3,6 Prozent) liegt weit unter
    # dem von Haendlern geschaetzten (19,1 Prozent). Zu niedrige Schwellen produzieren
    # Verdaechtigungen gegen normale Kunden.
    serial = []
    for cust, ret_orders in customer_return_orders.items():
        n_orders = len(customer_orders.get(cust, set()))
        rate = len(ret_orders) / n_orders if n_orders else None
        if (n_orders >= 5 and rate is not None and rate >= 0.7) or customer_return_count[cust] >= 10:
            serial.append({"kunde": cust, "bestellungen": n_orders,
                           "bestellungen_mit_retoure": len(ret_orders),
                           "retouren_positionen": customer_return_count[cust],
                           "quote": round(rate, 3) if rate is not None else None})
    serial.sort(key=lambda e: e["retouren_positionen"], reverse=True)

    # ---- Nicht abgeholte Sendungen
    def marge_je_stueck(sku):
        """Rohertrag je verkauftem Stueck. None, wenn kein Einkaufspreis geliefert wurde."""
        if sku not in sku_unit_cost or not sku_sold.get(sku):
            return None
        return (sku_revenue[sku] - sku_sold[sku] * sku_unit_cost[sku]) / sku_sold[sku]

    np_orders = {e["order"] for e in nonpickup if e["order"]}
    np_value = sum(e["refund"] for e in nonpickup)
    # Auch hier gilt: die Ware kommt ungeoeffnet zurueck ins Lager. Verlorener Umsatz ist die
    # richtige Zahl fuers Gespraech, vergleichbar mit den Artikelkosten ist aber nur die Marge.
    np_marge = sum((e["qty"] * m) for e in nonpickup
                   if (m := marge_je_stueck(e["sku"])) is not None)
    np_payment = Counter()
    seen_np = set()
    for e in nonpickup:
        if e["order"] and e["order"] not in seen_np:
            seen_np.add(e["order"])
            np_payment[e["payment"]] += 1
    overall_payment = Counter(order_payment.values())
    nonpickup_block = {
        "sendungen": len(np_orders),
        "anteil_an_bestellungen": round(len(np_orders) / len(orders), 4) if orders else None,
        "anteil_an_retouren_vorgaengen": round(len(np_orders) / len(orders_with_return), 4) if orders_with_return else None,
        "verlorener_umsatz": round(np_value, 2),
        "entgangene_marge": round(np_marge, 2),
        "zusatzkosten_versand_annahme": round(len(np_orders) * args.prozesskosten, 2),
        "schaden_vergleichbar": round(np_marge + len(np_orders) * args.prozesskosten, 2),
        "zahlart_verteilung_nicht_abgeholt": dict(np_payment),
        "zahlart_verteilung_alle_bestellungen": dict(overall_payment),
    }

    # ---- Chargen-Spikes (Defekt-Haeufung in einem Monat, aggregiert je Style)
    batch_spikes = []
    for style, months in defect_by_sku_month.items():
        if len(months) < 2:
            peak_month, peak = (list(months.items()) or [("", 0)])[0]
            if peak >= 8:
                batch_spikes.append({"style": style, "monat": peak_month,
                                     "defekte": peak, "basis_schnitt": 0})
            continue
        peak_month, peak = months.most_common(1)[0]
        rest = [v for m, v in months.items() if m != peak_month]
        mean_rest = sum(rest) / len(rest)
        if peak >= 5 and peak >= 3 * max(mean_rest, 1):
            batch_spikes.append({"style": style, "monat": peak_month,
                                 "defekte": peak, "basis_schnitt": round(mean_rest, 1)})

    # ---- Zahlart- und Kanal-Split (Bestellquote)
    def split_by(mapping):
        totals, rets = Counter(), Counter()
        for oid in orders:
            key = mapping.get(oid, "unbekannt")
            totals[key] += 1
            if oid in orders_with_return:
                rets[key] += 1
        return {k: {"bestellungen": totals[k], "mit_retoure": rets[k],
                    "quote": round(rets[k] / totals[k], 4)} for k in totals}

    # ---- Kosten-Attribution je SKU
    costs = []
    ohne_ek = 0
    for sku, events in sku_return_events.items():
        writeoff = sku_defect_qty.get(sku, 0) * sku_unit_cost.get(sku, 0.0)
        prozess = events * args.prozesskosten
        entry = {"sku": sku, "name": sku_name.get(sku, sku), "retouren_vorgaenge": events,
                 "retournierte_menge": round(sku_returned[sku], 2),
                 "erstatteter_umsatz": round(sku_refund[sku], 2),
                 "prozesskosten": round(prozess, 2),
                 "wertverlust_defekt": round(writeoff, 2),
                 "umsatz": round(sku_revenue.get(sku, 0.0), 2),
                 "verkauft": sku_sold.get(sku, 0)}
        if sku in sku_unit_cost and sku_sold.get(sku):
            # Der erstattete Umsatz ist kein Verlust, die Ware kommt zurueck ins Lager.
            # Verloren ist die Marge, die auf dem Stueck nicht verdient wurde. Damit ist
            # gesamt exakt der Rueckgang des Deckungsbeitrags: DB nach = DB vor minus gesamt.
            marge_vor = sku_revenue[sku] - sku_sold[sku] * sku_unit_cost[sku]
            entgangene_marge = sku_returned[sku] * (marge_vor / sku_sold[sku])
            total = entgangene_marge + prozess + writeoff
            entry["entgangene_marge"] = round(entgangene_marge, 2)
            entry["kostenbasis"] = "entgangene_marge"
            entry["deckungsbeitrag_vor_retouren"] = round(marge_vor, 2)
            entry["deckungsbeitrag_nach_retouren"] = round(marge_vor - total, 2)
        else:
            # Ohne unit_cost ist die Marge nicht rechenbar. Ersatzgroesse ist der erstattete
            # Umsatz, der die Kosten deutlich ueberzeichnet. Steht als Warnung im Report.
            total = sku_refund[sku] + prozess + writeoff
            entry["kostenbasis"] = "erstatteter_umsatz"
            ohne_ek += 1
        entry["gesamt"] = round(total, 2)
        if sku_revenue.get(sku):
            entry["kosten_anteil_am_umsatz"] = round(total / sku_revenue[sku], 4)
        costs.append(entry)
    costs.sort(key=lambda e: e["gesamt"], reverse=True)
    if ohne_ek:
        warnings.append(
            f"{ohne_ek} Artikel ohne unit_cost: dort ist ersatzweise der erstattete Umsatz als "
            f"Kostenbasis angesetzt. Das ueberzeichnet die Retourenkosten deutlich, weil die "
            f"zurueckgeschickte Ware wieder im Lager liegt.")

    # Dieselben Kosten je Artikel statt je Variante. Sechs auffaellige Varianten desselben
    # Artikels sind eine Ursache und eine Massnahme, nicht sechs. Ausserdem ist kosten_top
    # auf zehn Zeilen gekuerzt, ein Artikel dahinter haette sonst gar keinen Eurobetrag.
    style_costs = {}
    for c in costs:
        s = style_costs.setdefault(c["name"], {"name": c["name"], "varianten": 0,
                                               "retouren_vorgaenge": 0, "entgangene_marge": 0.0,
                                               "prozesskosten": 0.0, "wertverlust_defekt": 0.0,
                                               "gesamt": 0.0})
        s["varianten"] += 1
        s["retouren_vorgaenge"] += c["retouren_vorgaenge"]
        s["entgangene_marge"] += c.get("entgangene_marge", 0.0)
        s["prozesskosten"] += c["prozesskosten"]
        s["wertverlust_defekt"] += c["wertverlust_defekt"]
        s["gesamt"] += c["gesamt"]
    kosten_je_artikel = sorted(style_costs.values(), key=lambda e: e["gesamt"], reverse=True)
    for s in kosten_je_artikel:
        for k in ("entgangene_marge", "prozesskosten", "wertverlust_defekt", "gesamt"):
            s[k] = round(s[k], 2)

    # ---- Ertragsrechnung ueber alle Artikel, nicht nur die teuersten zehn
    # Ohne Einkaufspreis laesst sich kein Rohertrag rechnen, deshalb zaehlt nur, wofuer
    # unit_cost geliefert wurde. Wie viel Umsatz das abdeckt, steht als Quote dabei.
    ek_skus = [s for s in sku_sold if s in sku_unit_cost]
    e_umsatz = sum(sku_revenue.get(s, 0.0) for s in ek_skus)
    e_erstattet = sum(sku_refund.get(s, 0.0) for s in ek_skus)
    e_we_behalten = sum(max(sku_sold[s] - sku_returned.get(s, 0), 0) * sku_unit_cost[s] for s in ek_skus)
    e_we_gesamt = sum(sku_sold[s] * sku_unit_cost[s] for s in ek_skus)
    e_costs = [c for c in costs if c.get("kostenbasis") == "entgangene_marge"]
    e_prozess = sum(c["prozesskosten"] for c in e_costs)
    e_abschr = sum(c["wertverlust_defekt"] for c in e_costs)
    e_marge_weg = sum(c["entgangene_marge"] for c in e_costs)
    ertragsrechnung = {
        "bruttoumsatz": round(e_umsatz, 2),
        "erstatteter_umsatz": round(e_erstattet, 2),
        "nettoumsatz": round(e_umsatz - e_erstattet, 2),
        "wareneinsatz_behaltene_ware": round(e_we_behalten, 2),
        "rohertrag_vor_retouren": round(e_umsatz - e_we_gesamt, 2),
        "rohertrag_behaltene_ware": round(e_umsatz - e_erstattet - e_we_behalten, 2),
        "entgangene_marge": round(e_marge_weg, 2),
        "retourenbearbeitung": round(e_prozess, 2),
        "abschreibung_defekt": round(e_abschr, 2),
        "retourenkosten_gesamt": round(e_marge_weg + e_prozess + e_abschr, 2),
        "rohertrag_nach_retouren": round(e_umsatz - e_erstattet - e_we_behalten - e_prozess - e_abschr, 2),
        "umsatzabdeckung": round(e_umsatz / total_shipped_value, 4) if total_shipped_value else None,
    }

    # ---- Blinde Flecken: was ohne diese Analyse untergegangen waere
    # Jeder Eintrag sagt, WAS uebersehen wird und WARUM es der Standard-Report nicht zeigt.
    blind_spots = []

    # 1. Scheintrend durch unreife Kohorten
    mature_betas = [c["beta_quote"] for c in cohorts if c["mature"] and c["beta_quote"] is not None]
    unripe = [c for c in cohorts if not c["mature"] and c["beta_quote"] is not None]
    if mature_betas and unripe:
        mature_avg = sum(mature_betas) / len(mature_betas)
        youngest = unripe[-1]
        delta = mature_avg - youngest["beta_quote"]
        if delta > 0.02:
            blind_spots.append({
                "id": "kohorten_scheintrend",
                "titel": "Die Retourenquote sieht aus, als würde sie sinken. Tut sie nicht.",
                "warum_uebersehen": "Wer Retouren eines Monats durch Verkaeufe desselben Monats teilt, misst junge "
                                    "Bestellungen mit, deren Rueckgabefrist noch laeuft. Der Report zeigt eine "
                                    "Verbesserung, die nur ein Zeitversatz ist.",
                "befund": f"Die abgeschlossenen Bestellmonate liegen im Schnitt bei {de(mature_avg)}, "
                          f"der jüngste Monat {youngest['kohorte']} zeigt {de(youngest['beta_quote'])}. "
                          f"Das sind {de(delta)}punkte Unterschied, allein weil dort noch Retouren fehlen.",
                "unreife_kohorten": [c["kohorte"] for c in unripe],
            })

    # 2. Teuer trotz unauffaelliger Quote (taucht in keiner Top-Quoten-Liste auf)
    top_rate_skus = {e["sku"] for e in rankable[:10]}
    avg_beta = (sum(sku_returned.values()) / total_shipped_qty) if total_shipped_qty else 0
    hidden_cost = []
    for c in costs[:15]:
        if c["sku"] in top_rate_skus:
            continue
        sold = sku_sold.get(c["sku"], 0)
        rate = (sku_returned.get(c["sku"], 0) / sold) if sold else None
        if rate is not None and rate <= avg_beta * 1.2:
            hidden_cost.append({"sku": c["sku"], "name": c["name"], "beta_quote": round(rate, 4),
                                "kosten": c["gesamt"]})
    if hidden_cost:
        blind_spots.append({
            "id": "teuer_trotz_normaler_quote",
                "titel": "Artikel mit normaler Quote, die trotzdem viel Geld kosten",
            "warum_uebersehen": "Standard-Reports ranken nach Quote. Ein Artikel mit durchschnittlicher Quote, "
                                "aber hohem Volumen oder Preis fällt dort nie auf, kostet aber mehr als die "
                                "Ausreißer.",
            "artikel": hidden_cost[:5],
        })

    # 3. Segment-Kontrast: unauffaellig gesamt, auffaellig bei nicht abgeholten Sendungen
    if np_orders and orders:
        contrasts = []
        for zahlart, anzahl in np_payment.items():
            anteil_np = anzahl / len(np_orders)
            gesamt = overall_payment.get(zahlart, 0)
            anteil_gesamt = gesamt / len(orders) if orders else 0
            quote_gesamt = split_by(order_payment).get(zahlart, {}).get("quote")
            if anteil_gesamt > 0 and anteil_np >= 1.5 * anteil_gesamt and anzahl >= 10:
                contrasts.append({
                    "merkmal": zahlart,
                    "anteil_bei_nicht_abgeholt": round(anteil_np, 4),
                    "anteil_im_gesamtgeschaeft": round(anteil_gesamt, 4),
                    "retourenquote_gesamt_unauffaellig": quote_gesamt,
                })
        if contrasts:
            blind_spots.append({
                "id": "segment_kontrast",
                "titel": "Ein Merkmal, das erst in der Kreuzung auffällt",
                "warum_uebersehen": "In der Gesamtsicht liegen alle Zahlarten dicht beieinander, da ist nichts zu "
                                    "sehen. Erst wenn man nur die nicht abgeholten Sendungen anschaut, kippt das "
                                    "Bild deutlich.",
                "kontraste": contrasts,
            })

    # 4. Retouren ohne belastbaren Grund
    unknown = reason_counter.get("sonstiges_unbekannt", 0)
    total_ret = sum(reason_counter.values())
    if total_ret and unknown / total_ret >= 0.08:
        blind_spots.append({
            "id": "gruende_fehlen",
                "titel": "Ein relevanter Teil der Retouren hat keinen brauchbaren Grund",
            "warum_uebersehen": "Leere Gründe und Sonstiges landen im Report als Restposten und werden nicht weiter "
                                "angeschaut. Dahinter steckt häufig ein eigener Fall, etwa nicht abgeholte "
                                "Sendungen oder ein Prozessfehler.",
            "anteil": round(unknown / total_ret, 4),
            "anzahl": unknown,
        })

    # 5. Marge-Falle: Deckungsbeitrag bricht durch Retouren weg
    margin_traps = [c for c in costs
                    if c.get("deckungsbeitrag_vor_retouren", 0) > 0
                    and c.get("deckungsbeitrag_nach_retouren") is not None
                    and c["deckungsbeitrag_nach_retouren"] < 0.25 * c["deckungsbeitrag_vor_retouren"]]
    if margin_traps:
        blind_spots.append({
            "id": "marge_falle",
            "titel": "Artikel, die brutto verdienen und nach Retouren fast nichts übrig lassen",
            "warum_uebersehen": "Retourenkosten stehen in der Regel nicht am Artikel. In der Sortimentsauswertung "
                                "sieht der Artikel gesund aus.",
            "artikel": [{"sku": c["sku"], "name": c["name"],
                         "db_vor_retouren": c["deckungsbeitrag_vor_retouren"],
                         "db_nach_retouren": c["deckungsbeitrag_nach_retouren"]}
                        for c in margin_traps[:5]],
        })

    missing = []
    sample = returns_rows[0] if returns_rows else {}
    for col, analysis in [("delivered_date", "Zeit zwischen Zustellung und Rücksendung"),
                          ("batch", "Chargen eindeutig zuordnen statt zeitlich schätzen"),
                          ("refund_type", "Umtausch gegen Erstattung unterscheiden"),
                          ("condition", "Wertverlust echt rechnen statt schätzen")]:
        if col not in sample:
            missing.append({"spalte": col, "entfallene_analyse": analysis})

    return {
        "meta": {
            "retouren_positionen": len(returns_rows),
            "verkaufs_positionen": len(sales_rows),
            "bestellungen": len(orders),
            "zeitraum_bis": today.strftime("%Y-%m-%d"),
            "annahmen": assumptions,
            "warnungen": warnings,
            "fehlende_spalten": missing,
        },
        "quoten": {
            # Sechs Nachkommastellen, nicht vier: das Dashboard rundet danach nochmal auf eine
            # Nachkommastelle in Prozent. Bei vier Stellen wurde daraus zweimal gerundet und
            # 22,3461 Prozent kamen als 22,4 heraus.
            # Die Kennzahl, die ein Haendler "Retourenquote" nennt: zurueckgeschickte Artikel
            # geteilt durch versendete Artikel, ohne die nie abgeholten Sendungen. Sie steht
            # vorn, weil jede Standard-Auswertung mit ihr anfaengt.
            "retourenquote": round(ret_qty_customer / total_shipped_qty, 6) if total_shipped_qty else None,
            "retourenquote_wert": round(ret_value_customer / total_shipped_value, 6) if total_shipped_value else None,
            "retourenquote_bestellungen": round(len(orders_with_customer_return) / len(orders), 6) if orders else None,
            "nichtabholquote": round(ret_qty_nonpickup / total_shipped_qty, 6) if total_shipped_qty else None,
            # Dieselben drei Quoten inklusive Nichtabholung, also ueber alle Rueckläufer.
            # Sie sind der Bezug fuer die Kostenrechnung, denn Kosten fallen bei beidem an.
            "gesamt_beta": round(sum(sku_returned.values()) / total_shipped_qty, 6) if total_shipped_qty else None,
            "gesamt_gamma": round(sum(sku_refund.values()) / total_shipped_value, 6) if total_shipped_value else None,
            "gesamt_bestellquote": round(len(orders_with_return) / len(orders), 6) if orders else None,
            # Zaehler und Nenner offen ausweisen. Eine Quote ohne ihren Bruch ist im Gespraech
            # nicht verteidigbar, und die drei unterscheiden sich nur durch den Nenner.
            "basis": {
                "artikel_versendet": round(total_shipped_qty, 2),
                "artikel_retourniert": round(sum(sku_returned.values()), 2),
                "warenwert_versendet": round(total_shipped_value, 2),
                "warenwert_retourniert": round(sum(sku_refund.values()), 2),
                "bestellungen": len(orders),
                "bestellungen_mit_retoure": len(orders_with_return),
                "artikel_retourniert_kundenretoure": round(ret_qty_customer, 2),
                "artikel_retourniert_nicht_abgeholt": round(ret_qty_nonpickup, 2),
                "warenwert_retourniert_kundenretoure": round(ret_value_customer, 2),
                "bestellungen_mit_kundenretoure": len(orders_with_customer_return),
            },
            # Gamma geteilt durch Beta ist rechnerisch das Verhaeltnis der Durchschnittspreise.
            # Liegt der Faktor ueber 1, kommt ueberdurchschnittlich Teures zurueck.
            "preisvergleich": {
                "schnittpreis_versendet": round(total_shipped_value / total_shipped_qty, 2)
                if total_shipped_qty else None,
                "schnittpreis_retourniert": round(sum(sku_refund.values()) / sum(sku_returned.values()), 2)
                if sum(sku_returned.values()) else None,
                "faktor": round((sum(sku_refund.values()) / sum(sku_returned.values()))
                                / (total_shipped_value / total_shipped_qty), 4)
                if sum(sku_returned.values()) and total_shipped_qty and total_shipped_value else None,
            },
            "je_kohorte": cohorts,
        },
        "ertragsrechnung": ertragsrechnung,
        "blinde_flecken": blind_spots,
        "gruende": dict(reason_counter.most_common()),
        "sku_quoten_top": rankable[:10],
        "sku_unter_mindest_n": len(sku_rates) - len(rankable),
        "groessen_laeufer": size_runners[:5],
        "bracketing": {
            "bestellungen_mehrgroessen": bracketing_orders,
            "davon_mit_retoure": bracketing_with_return,
            "quote": round(bracketing_with_return / bracketing_orders, 4) if bracketing_orders else None,
        },
        "serien_retournierer_review": serial[:10],
        "nicht_abgeholt": nonpickup_block,
        "chargen_spikes": batch_spikes,
        "zahlart_split": split_by(order_payment),
        "kanal_split": split_by(order_channel),
        "kosten_top": costs[:10],
        "kosten_je_artikel": kosten_je_artikel,
    }


def main():
    p = argparse.ArgumentParser(description="Retouren-Analyse (deterministisch)")
    p.add_argument("--retouren", required=True)
    p.add_argument("--verkaeufe", required=True)
    p.add_argument("--out", default="analysis.json")
    p.add_argument("--prozesskosten", type=float, default=10.0)
    p.add_argument("--rueckgabefenster", type=int, default=60)
    p.add_argument("--min-retouren", dest="min_retouren", type=int, default=3)
    p.add_argument("--reifepuffer", type=int, default=21)
    args = p.parse_args()

    result = analyze(read_csv(args.retouren), read_csv(args.verkaeufe), args)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"OK: {args.out} geschrieben "
          f"({result['meta']['retouren_positionen']} Retouren-Positionen, "
          f"{result['meta']['bestellungen']} Bestellungen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
