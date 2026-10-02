"""Triage a RAN alarm log the way a NOC engineer would: collapse repeats, group by site,
and point at the likely upstream cause when several radios alarm under one DU.

Log format (one alarm per line, pipe-separated):
    2026-09-14T08:01:10 | DEN-0412 | RU-2 | CRITICAL | Link down to DU-1
    timestamp            | site     | node | severity | text

Node names: CU-n, DU-n, RU-n. The topology file maps each RU to its DU.
"""

from collections import Counter, defaultdict
from datetime import datetime

SEVERITY_RANK = {"CRITICAL": 3, "MAJOR": 2, "MINOR": 1, "WARNING": 0}


def parse_alarm_line(line):
    """Return a dict for one alarm line, or None if the line is malformed."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 5:
        return None
    ts, site, node, severity, text = parts
    severity = severity.upper()
    if severity not in SEVERITY_RANK:
        return None
    try:
        when = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return {"time": when, "site": site.upper(), "node": node.upper(),
            "severity": severity, "text": text}


def parse_log(text):
    """Parse every line. Returns (alarms, bad_line_numbers)."""
    alarms, bad = [], []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        alarm = parse_alarm_line(line)
        if alarm is None:
            bad.append(n)
        else:
            alarms.append(alarm)
    return alarms, bad


def collapse_repeats(alarms):
    """Merge identical alarms (same site, node, severity, text) into one entry with a count,
    first-seen and last-seen times. Repeats are noise during triage."""
    merged = {}
    for a in alarms:
        key = (a["site"], a["node"], a["severity"], a["text"])
        if key not in merged:
            merged[key] = {**a, "count": 0, "first": a["time"], "last": a["time"]}
        m = merged[key]
        m["count"] += 1
        m["first"] = min(m["first"], a["time"])
        m["last"] = max(m["last"], a["time"])
    return list(merged.values())


def probable_upstream(alarms, ru_to_du, min_rus=2):
    """If at least `min_rus` RUs under the same DU at one site are alarming, the DU or its
    transport is the more likely cause. Returns [(site, du, sorted RUs)]."""
    by_du = defaultdict(set)
    for a in alarms:
        if a["node"].startswith("RU") and a["severity"] in ("CRITICAL", "MAJOR"):
            du = ru_to_du.get((a["site"], a["node"]))
            if du:
                by_du[(a["site"], du)].add(a["node"])
    return [(site, du, sorted(rus)) for (site, du), rus in sorted(by_du.items())
            if len(rus) >= min_rus]


def site_summary(alarms):
    """Per site: worst severity and alarm counts by severity, worst sites first."""
    summary = defaultdict(Counter)
    for a in alarms:
        summary[a["site"]][a["severity"]] += 1

    def worst(counts):
        return max(SEVERITY_RANK[s] for s in counts)

    rows = []
    for site, counts in summary.items():
        rank = worst(counts)
        worst_name = next(s for s, r in SEVERITY_RANK.items() if r == rank)
        rows.append((site, worst_name, dict(counts)))
    rows.sort(key=lambda r: (-SEVERITY_RANK[r[1]], -sum(r[2].values()), r[0]))
    return rows
