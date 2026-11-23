#!/usr/bin/env python3
# ============================================================================
# P37 (Sinar Lembah Grid, Meter Watch and Demand Forecast) - PBIR report generator, 5 pages, 1280 x 720.
#
# Built to the approved mockup 01_Design/P37_Mockup_V1.html (G2 "Go", 2026-11-23) with the design-review fixes:
# 12 px type floor at page scale, the operator view separated from the answer-key check, the previous-7-day comparison,
# a data dictionary that names the model's own tables, and every finding in a DAX title (owner rule: no number typed
# into report text). Visual primitives: _ENGINE/lib/pbir_kit.py (lifted from P34; visualContainer 2.11.0, page 2.1.0,
# pagesMetadata 1.1.0, report 3.3.0). Model names re-read from build_model.py (TABLES and MEAS) at build time.
#
# Binding: byPath to ../SM_SinarLembah.SemanticModel, the shape Fabric Git integration writes for a report and its
# model in one workspace; fabric-cicd rebinds it on publish (probed on Dev first; fallback byConnection + parameter.yml).
#
# DEVIATIONS FROM THE MOCKUP (recorded, not hidden):
#   1. The forecast range is drawn as two thin lines (low, high), not a shaded band: no proven PBIR shape for an error band.
#   2. The substation x day matrix has no colour scale: no proven PBIR shape for gradient rules (manual follow-up).
#   3. Feeder Detail opens on all feeders and its title asks for one: no proven default slicer selection in PBIR.
#   4. Forecast error is the 9-week backtest figure (pooled WAPE), not a 4-week figure: the model keeps one window.
# ============================================================================
import json
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kit")
sys.path.insert(0, KIT)
import pbir_kit as K                                    # noqa: E402
from pbir_kit import (SCHEMA, b, s, pos, textbox, nav, rule, kpi_card, chart, table_ex, matrix, xmatrix,  # noqa: E402,F401
                      takeaway, slicer, measure, column, by_measure, by_column, write_json)
sys.path.insert(0, HERE)
import build_model as BM                                # noqa: E402

REPORT_NAME = "P37_SinarLembah"
MODEL_FOLDER = "SM_SinarLembah.SemanticModel"
THEME_FILE = "MyLifeInLegoBricks_Theme.json"
INK, SEC, TER, CARD_BG, BORDER = K.INK, K.SEC, K.TER, K.CARD_BG, K.BORDER
D1, D2, D3, D4, D5 = K.D1, K.D2, K.D3, K.D4, K.D5
AL, RD, FC, FG, PE, DM, FD, DT, HR = "Alert", "Reading", "Forecast", "Forecast group", "Planted event", "Detector metric", "Feeder", "Date", "Hour"

# --- every field the report binds must exist in the model (checked before anything is written) -----------------------
_COLS = {(t, c) for t, (_, _, cols) in BM.TABLES.items() for c, _, _ in cols}
_MEAS = {(t, n) for t, n, *_ in BM.MEAS}
USED = []


def M(entity, name, display=None):
    USED.append(("m", entity, name))
    return measure(entity, name, display)


def C(entity, prop, display=None):
    USED.append(("c", entity, prop))
    return column(entity, prop, display)


def KM(entity, name, label=None):
    USED.append(("m", entity, name))
    return (entity, name, label) if label else (entity, name)


def T(name, p, entity, prop, **kw):
    USED.append(("m", entity, prop))
    return takeaway(name, p, entity, prop, **kw)


TOP = 148


def header(title, tmeasure=None, t_entity=None, sub_text=None):
    v = [textbox("Title", pos(24, 2, 520, 42, 3000, 100), [(title, 18, INK, True, False)]),
         nav("Nav", pos(548, 10, 708, 32, 6000, 300)),
         rule("Rule", pos(24, 86, 1232, 2, 5000, 400)),
         T("Disc", pos(18, 686, 1238, 30, 8000, 9000), AL, "Disclaimer", size=9, colr=TER,
           alt="Footer: synthetic data, the cut-off hour and the units, read from the data.")]
    if tmeasure:
        v.append(T("Take", pos(18, 44, 1238, 40, 2000, 200), t_entity, tmeasure, size=12))
    else:
        v.append(textbox("Take", pos(24, 48, 1000, 30, 2000, 200), [(sub_text, 12, SEC, False, False)]))
    return v


def slicer_row(spec):
    """spec: list of (label, entity, prop, x, label_w, slicer_w, alt)."""
    v = []
    for i, (lbl, ent, prop, x, lw, sw, alt) in enumerate(spec):
        v.append(textbox("SlLbl%d" % i, pos(x, 104, lw, 24, 7050 + i, 490 + i), [(lbl, 10, SEC, True, False)]))
        USED.append(("c", ent, prop))
        v.append(slicer("Sl%d" % i, pos(x + lw, 92, sw, 48, 7100 + i, 500 + i), ent, prop, alt))
    return v


SUBST = ("Substation", FD, "substation_name", 24, 92, 220, "Slicer: main distribution substation.")


# ---------------------------------------------------------------------------------------------------------- pages
def page_home():
    v = header("Sinar Lembah Grid", sub_text="Meter Watch and Demand Forecast")
    v += [T("Eyebrow", pos(18, 100, 620, 30, 2400, 450), AL, "Eyebrow Home", size=12, colr=D1, bold=True,
            alt="As-of hour, read from the data."),
          textbox("Hero", pos(24, 130, 620, 100, 2300, 500), [("Watch every feeder.", 22, D3, True, False),
                                                            ("Plan tomorrow's load.", 22, D3, True, False)]),
          T("HeroSub", pos(18, 232, 620, 84, 2200, 550), AL, "Subtitle Home", size=12,
            alt="What the report watches: feeders, substations, alerts and the day-ahead forecast."),
          kpi_card("Kpi", pos(660, 100, 596, 112, 7000, 600),
                   [KM(AL, "Incidents last 24 h", "Incidents, last 24 hours"), KM(FC, "Tomorrow peak MW", "Peak tomorrow, MW"), KM(FC, "Forecast error", "Forecast error, backtest")],
                   "Home KPI cards: incidents in the last 24 hours, tomorrow's peak and the backtest forecast error.", vsize=18)]
    # kpi_card already called measure(); register the fields for the model check
    v.append(chart("PerDay", "columnChart", pos(660, 224, 596, 214, 1100, 700), C(DT, "date", "Day"),
                   [M(AL, "Alert hours, last 30 days", "Alert hours")], "Alert hours per day", "Last 30 days, all substations",
                   "Column chart of alert hours per day over the last 30 days.", colors=[D1], labels=False, value_axis=True,
                   sort=by_column(DT, "date")))
    tiles = [("Meter Watch", "Which feeders are unusual now, and why", D1, (24, 324, 300, 112)),
             ("Demand Forecast", "Tomorrow by hour and substation; how good the forecast has been", D3, (336, 324, 300, 112)),
             ("Feeder Detail", "One feeder: load against its usual profile, alerts, forecast", D3, (24, 448, 300, 112)),
             ("Report Guide", "How to read it, and the data dictionary", D1, (336, 448, 300, 112))]
    for i, (t, d, col, (x, y, w, h)) in enumerate(tiles):
        tb = textbox("Tile%d" % i, pos(x, y, w, h, 2000 + i, 700 + i), [(t, 14, CARD_BG, True, False), (d, 12, CARD_BG, False, False)],
                     panel=True, accent=col)
        tb["visual"]["visualContainerObjects"]["background"] = [{"properties": {"show": b(True), "color": K.color(col), "transparency": K.num(0)}}]
        v.append(tb)
    v.append(chart("BySub", "barChart", pos(660, 450, 596, 228, 1200, 710), C(FD, "substation_name", "Substation"),
                   [M(AL, "Alert hours last 7 days", "Alert hours")], "Where the alerts are", "Alert hours in the last 7 days, by substation",
                   "Bar chart of alert hours in the last 7 days by substation, sorted descending.", colors=[D2],
                   sort=by_measure(AL, "Alert hours last 7 days"), margin=45))
    return v


def page_meter():
    v = header("Meter Watch", "Title Meter Watch", AL)
    v += slicer_row([SUBST, ("Feeder type", FD, "feeder_type", 360, 92, 160, "Slicer: feeder type."),
                     ("Alert type", AL, "alert_type", 636, 84, 140, "Slicer: alert type, spike, drop or flat meter.")])
    v.append(kpi_card("Kpi", pos(24, TOP, 1232, 76, 7000, 600),
                      [KM(AL, "Incidents last 24 h", "Incidents, last 24 hours"), KM(AL, "Incidents last 7 days", "Incidents, last 7 days"),
                       KM(AL, "Incidents previous 7 days", "Incidents, 7 days before"), KM(AL, "Feeders with alerts 7 days", "Feeders with alerts, 7 days"),
                       KM(AL, "Switching share 7 days", "In planned switching, 7 days"), KM(PE, "Recall", "Planted events caught")],
                      "Meter Watch KPI row: incidents last 24 hours, last 7 days and the 7 days before, feeders with alerts, "
                      "share in planned switching, and the detector's recall on planted events.", vsize=17))
    hm = xmatrix("Heat", pos(24, 234, 600, 256, 1100, 700), [C(FD, "substation_name", "Substation")], [C(DT, "weekday_name", "Day")],
                 [M(AL, "Alert hours by day, last 7 days", "Alert hours")], "Alert hours by substation and day",
                 "Last 7 days up to the cut-off, Monday to Sunday", "Matrix of alert hours by substation and weekday for the last 7 days.")
    hm["filterConfig"] = {"filters": [K.not_blank("fNotBlank%02d" % next(K._NB), FD, "substation_name")]}   # Direct Lake blank member (render pass 1)
    v.append(hm)
    v.append(table_ex("Latest", pos(636, 234, 620, 256, 1200, 710),
                      [C(AL, "reading_hour", "Hour"), C(FD, "feeder_name", "Feeder"), C(AL, "alert_type", "Type"),
                       C(AL, "demand_mw", "MW"), C(AL, "usual_mw", "Usual MW"), C(AL, "z", "Score"), C(AL, "cause", "Explained by")],
                      "Latest alerts", "Newest first; score = spreads from the usual load for that hour and day type",
                      "Table of alerts, newest first.", sort=by_column(AL, "reading_hour", desc=True)))
    v.append(chart("Cause", "barChart", pos(24, 500, 600, 180, 1300, 720), C(AL, "cause", "Explained by"),
                   [M(AL, "Alert hours")], "What explains the alerts", "All scored hours; planned switching comes from the switching log",
                   "Bar chart of alert hours by cause: planned switching or not explained.", colors=[D1],
                   sort=by_measure(AL, "Alert hours"), margin=40))
    v.append(chart("Caught", "clusteredColumnChart", pos(636, 500, 410, 180, 1400, 730), C(PE, "event_label", "Event type"),
                   [M(PE, "Events matured", "Planted"), M(PE, "Events caught", "Caught")], "Detector check: planted events caught",
                   "Answer key; events ended a day before the cut-off",
                   "Clustered column chart of planted events and events caught, by event type.", colors=[D4, D1], legend=True,
                   sort=by_measure(PE, "Events matured"), margin=40))
    v.append(kpi_card("Control", pos(1056, 500, 200, 180, 7100, 740), [KM(DM, "Control hits", "Control hits"), KM(DM, "Control windows", "Control windows")],
                      "Control: planted windows moved one week later, and how many drew an alert.", vsize=16))
    return v


def page_forecast():
    v = header("Demand Forecast", "Title Demand Forecast", FC)
    v += slicer_row([SUBST, ("Feeder type", FD, "feeder_type", 360, 92, 160, "Slicer: feeder type.")])
    v.append(kpi_card("Kpi", pos(24, TOP, 1232, 76, 7000, 600),
                      [KM(FC, "Tomorrow peak MW", "Peak tomorrow, MW"), KM(FC, "Tomorrow peak hour", "Peak hour"), KM(FC, "Tomorrow MWh", "Energy tomorrow, MWh"),
                       KM(FC, "Forecast error", "Model error"), KM(FC, "Same hour last week error", "Benchmark error"), KM(FC, "Gain pts", "Gain, points"),
                       KM("Model metric", "Gain interval low", "Gain, 95% low"), KM("Model metric", "Gain interval high", "Gain, 95% high")],
                      "Demand Forecast KPI row: tomorrow's peak, its hour and energy; backtest error of the model and of same hour "
                      "last week; the gain in points and its 95% interval.", vsize=16))
    v.append(chart("Tomorrow", "lineChart", pos(24, 234, 760, 256, 1100, 700), C(HR, "hour_of_day", "Hour"),
                   [M(FC, "Forecast MW, forecast day", "Forecast"), M(FC, "Range low MW, forecast day", "Range low"),
                    M(FC, "Range high MW, forecast day", "Range high")],
                   "Tomorrow, hour by hour", "MW; range = 10th to 90th percentile of past misses, for one feeder, one substation or all feeders",
                   "Line chart of tomorrow's forecast by hour with the low and high ends of its range.",
                   colors=[D1, D4, D4], legend=True, labels=False, value_axis=True, sort=by_column(HR, "hour_of_day")))
    v.append(chart("PeakSub", "barChart", pos(796, 234, 460, 256, 1200, 710), C(FD, "substation_name", "Substation"),
                   [M(FC, "Tomorrow peak MW", "Peak MW")], "Tomorrow's peak by substation", "MW at each substation's own peak hour",
                   "Bar chart of tomorrow's peak by substation, sorted descending.", colors=[D2],
                   sort=by_measure(FC, "Tomorrow peak MW"), margin=45))
    v.append(chart("Err", "lineChart", pos(24, 500, 1232, 180, 1300, 720), C(DT, "date", "Day"),
                   [M(FC, "Forecast error", "Model"), M(FC, "Same hour last week error", "Same hour last week")],
                   "Daily forecast error over the backtest", "Absolute miss over actual demand, per day; lower is better",
                   "Line chart of daily forecast error for the model and for same hour last week across the backtest.",
                   colors=[D1, D5], legend=True, labels=False, value_axis=True, sort=by_column(DT, "date")))
    return v


def page_feeder():
    v = header("Feeder Detail", "Title Feeder Detail", FC)
    v += slicer_row([SUBST, ("Feeder", FD, "feeder_name", 360, 60, 220, "Slicer: one feeder.")])
    v.append(kpi_card("Kpi", pos(24, TOP, 1232, 76, 7000, 600),
                      [KM(FD, "Rated peak MW", "Rated peak, MW"), KM(RD, "Peak demand MW, last 7 days", "Highest hour, 7 days, MW"),
                       KM(AL, "Alert hours last 7 days", "Alert hours, 7 days"), KM(AL, "Incidents last 7 days", "Incidents, 7 days"),
                       KM(FC, "Tomorrow peak MW", "Peak tomorrow, MW"), KM(FC, "Tomorrow peak hour", "Peak hour")],
                      "Feeder Detail KPI row: rated peak, highest hour this week, alert hours and incidents this week, tomorrow's peak and its hour.",
                      vsize=17))
    v.append(chart("Week", "lineChart", pos(24, 234, 1232, 256, 1100, 700), C(RD, "reading_hour", "Hour"),
                   [M(RD, "Demand MW, last 7 days", "Actual"), M(RD, "Usual MW, last 7 days", "Usual")],
                   "Last 7 days against the usual load", "Hourly MW; usual = median for that hour and day type over the 12 weeks before",
                   "Line chart of hourly demand against the usual load over the last 7 days.",
                   colors=[D1, D4], legend=True, labels=False, value_axis=True, sort=by_column(RD, "reading_hour")))
    v.append(chart("Tom", "lineChart", pos(24, 500, 600, 180, 1200, 710), C(HR, "hour_of_day", "Hour"),
                   [M(FC, "Forecast MW, forecast day", "Forecast"), M(FC, "Range low MW, forecast day", "Range low"),
                    M(FC, "Range high MW, forecast day", "Range high")],
                   "Tomorrow for this selection", "Forecast with the low and high ends of its range",
                   "Line chart of tomorrow's forecast by hour for the selection, with its range.",
                   colors=[D1, D4, D4], legend=True, labels=False, value_axis=True, sort=by_column(HR, "hour_of_day")))
    v.append(table_ex("Alerts", pos(636, 500, 620, 180, 1300, 720),
                      [C(AL, "reading_hour", "Hour"), C(FD, "feeder_name", "Feeder"), C(AL, "alert_type", "Type"),
                       C(AL, "demand_mw", "MW"), C(AL, "usual_mw", "Usual MW"), C(AL, "z", "Score"), C(AL, "cause", "Explained by")],
                      "Alerts for this selection", "Newest first", "Table of alerts for the selected feeder, newest first.",
                      sort=by_column(AL, "reading_hour", desc=True)))
    return v


def page_guide():
    v = header("Report Guide", sub_text="What each number means, and where it comes from")
    p = lambda t, sz=11, c=INK, bold=False: (t, sz, c, bold, False)   # noqa: E731  (11 pt body: render pass 2, 12 pt overflowed)
    v.append(textbox("Read", pos(24, 100, 600, 404, 1100, 600), [
        p("How to read this report", 14, INK, True),
        p("Usual load: the median reading for the same feeder, hour and day type (weekday, Saturday, Sunday or public holiday) over the 12 weeks before."),
        p("Alert: a reading five typical spreads above or below the usual load, or a meter that repeats one value for six hours. Alerts arrive with each hourly batch."),
        p("Incident: alerts on one feeder in back-to-back hours; one quiet hour ends it."),
        p("Explained by: planned switching when the switching log covers the hour (a planned load transfer), otherwise not explained."),
        p("Forecast: made after the last hourly batch for the next day, from the last day, the same hour in the last four weeks, the hour, day type, public holidays and the temperature forecast."),
        p("Forecast error: absolute miss over actual demand (WAPE). Same hour last week is the simple forecast the model has to beat; the gain is the difference in points."),
        p("Detector check: the generator planted spikes, drops, stuck meters and slow drifts; only this check reads that answer key.")],
        panel=True, accent=BORDER))
    v.append(textbox("Dict", pos(636, 100, 620, 404, 1200, 610), [
        p("Data dictionary", 14, INK, True),
        p("Reading: one row per feeder per hour, scored against the usual load (Eventhouse table reading_scored, by shortcut)."),
        p("Alert: one row per alert hour, with its incident and cause (Lakehouse gold_alert)."),
        p("Forecast: one row per feeder per hour for the backtest and the forecast day, with the range (gold_forecast_hourly)."),
        p("Forecast group: the same for each substation and for all feeders, with their own ranges (gold_forecast_group)."),
        p("Planted event: the generator's answer key, graded (gold_event_grade)."),
        p("Model metric and Detector metric: backtest and detector figures with their intervals (gold_model_metric, gold_detector_metric)."),
        p("Feeder, Date, Hour: feeders and their main distribution substation; calendar with day type and public holidays for Kuala Lumpur and Selangor; hours.")],
        panel=True, accent=BORDER))
    v.append(textbox("Sources", pos(24, 512, 1232, 168, 1300, 620), [
        p("Where the numbers come from", 14, INK, True),
        p("Hourly batches land in the Eventhouse EH_SinarLembah. Update policies score each batch against the usual load and raise alerts as it arrives. "
          "OneLake availability exposes the tables to the Lakehouse LH_SinarLembah through shortcuts. The notebooks NB_SinarLembah_Gold and "
          "NB_SinarLembah_Forecast build the Gold tables and the day-ahead forecast, run by the pipeline PL_SinarLembah_Daily with a verdict gate "
          "after each step. This report reads them in Direct Lake through SM_SinarLembah."),
        p("The data is synthetic, from a deterministic generator: load shapes by feeder type, temperature, growth and public holidays, plus planted events.", 11, SEC)],
        panel=True, accent=BORDER))
    return v


PAGES = [("PageHome", "Home", page_home), ("PageMeter", "Meter Watch", page_meter), ("PageForecast", "Demand Forecast", page_forecast),
         ("PageFeeder", "Feeder Detail", page_feeder), ("PageGuide", "Report Guide", page_guide)]


def check_fields():
    missing = []
    for kind, ent, name in USED:
        if (kind == "m" and (ent, name) not in _MEAS) or (kind == "c" and (ent, name) not in _COLS):
            missing.append((kind, ent, name))
    return missing


def build(out_root, theme_src):
    rep = os.path.join(out_root, REPORT_NAME + ".Report")
    pages = []
    for name, display, fn in PAGES:
        vis = fn()
        names = [x["name"] for x in vis]
        assert len(names) == len(set(names)), "duplicate visual name on %s" % name
        pages.append((name, display, vis))
    miss = check_fields()
    if miss:
        raise SystemExit("fields not in the model: %s" % miss)
    write_json(os.path.join(out_root, REPORT_NAME + ".pbip"), {
        "$schema": SCHEMA["pbip"], "version": "1.0", "artifacts": [{"report": {"path": REPORT_NAME + ".Report"}}],
        "settings": {"enableAutoRecovery": True}})
    write_json(os.path.join(rep, ".platform"), {
        "$schema": SCHEMA["platform"], "metadata": {"type": "Report", "displayName": REPORT_NAME,
                                                    "description": "P37 Meter Watch and Demand Forecast, five pages, Direct Lake on SM_SinarLembah."},
        "config": {"version": "2.0", "logicalId": "37a00000-0000-4000-8000-000000000007"}})
    write_json(os.path.join(rep, "definition.pbir"), {"$schema": SCHEMA["pbir"], "version": "4.0",
                                                       "datasetReference": {"byPath": {"path": "../" + MODEL_FOLDER}}})
    write_json(os.path.join(rep, "definition", "version.json"), {"$schema": SCHEMA["version"], "version": "2.0.0"})
    theme = json.load(open(theme_src, encoding="utf-8-sig")); theme["name"] = THEME_FILE
    write_json(os.path.join(rep, "StaticResources", "RegisteredResources", THEME_FILE), theme)
    write_json(os.path.join(rep, "definition", "report.json"), {
        "$schema": SCHEMA["report"],
        "themeCollection": {"customTheme": {"name": THEME_FILE, "reportVersionAtImport": {"visual": "2.11.0", "report": "3.3.0", "page": "2.1.0"},
                                            "type": "RegisteredResources"}},
        "objects": {"section": [{"properties": {"verticalAlignment": s("Top")}}], "outspacePane": [{"properties": {"expanded": b(False)}}]},
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": THEME_FILE, "path": THEME_FILE, "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized", "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True, "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}})
    order = [p[0] for p in pages]
    write_json(os.path.join(rep, "definition", "pages", "pages.json"), {"$schema": SCHEMA["pages"], "pageOrder": order,
                                                                        "activePageName": order[0], "landingPageName": order[0]})
    counts = {}
    for name, display, vis in pages:
        pdir = os.path.join(rep, "definition", "pages", name)
        write_json(os.path.join(pdir, "page.json"), {"$schema": SCHEMA["page"], "name": name, "displayName": display,
                                                     "displayOption": "FitToPage", "height": 720, "width": 1280})
        for x in vis:
            write_json(os.path.join(pdir, "visuals", x["name"], "visual.json"), x)
        counts[name] = len(vis)
    return rep, counts


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "estate", "fabric")
    theme_src = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "fabric", REPORT_NAME + ".Report", "StaticResources", "RegisteredResources", THEME_FILE)
    rep, counts = build(out, theme_src)
    files = sum(len(f) for _, _, f in os.walk(rep))
    print("[scan] built %s (%d files)" % (rep, files))
    for k, n in counts.items():
        print("  %-14s %2d visuals" % (k, n))
    print("  TOTAL %d visuals across %d pages; %d fields checked against the model" % (sum(counts.values()), len(counts), len(USED)))
