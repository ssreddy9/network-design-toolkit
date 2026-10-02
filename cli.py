"""Command-line entry point.

Examples:
    python cli.py check data/connections.csv --optics data/optics.json
    python cli.py bom data/connections.csv --optics data/optics.json
    python cli.py diff data/connections.csv --optics data/optics.json --installed data/installed.json
    python cli.py reconcile data/sources.json
    python cli.py trace data/fiber_links.csv rtr1:Ethernet1/1 spine1:Ethernet1/1
    python cli.py triage data/alarms.log data/ran_topology.csv
"""

import argparse
import csv
import sys

from netdesign.alarms import SEVERITY_RANK, collapse_repeats, parse_log, probable_upstream, site_summary
from netdesign.bom import bom_by_site, build_bom, compare_inventory
from netdesign.checks import duplicate_ports, missing_fields, unknown_cable_types
from netdesign.paths import build_graph, fewest_hops, lowest_loss
from netdesign.reconcile import reconcile
from netdesign.records import load_connections, load_json


def run_checks(records, optics):
    """Print every problem found. Returns the number of blocking problems."""
    problems = 0
    for row, fields in missing_fields(records):
        print(f"  BLOCKER  line {row}: missing {', '.join(fields)}")
        problems += 1
    for (device, port), rows in sorted(duplicate_ports(records).items()):
        print(f"  BLOCKER  {device} {port} used on lines {rows}")
        problems += 1
    for row, cable in unknown_cable_types(records, optics):
        print(f"  BLOCKER  line {row}: no optic mapping for cable type '{cable}'")
        problems += 1
    return problems


def clean_rows(records, optics):
    """Rows that are complete and have a known cable type, safe to build a BOM from."""
    bad = {row for row, _ in missing_fields(records)}
    bad |= {row for row, _ in unknown_cable_types(records, optics)}
    return [rec for i, rec in enumerate(records, start=2) if i not in bad]


def cmd_check(args):
    records = load_connections(args.connections)
    optics = load_json(args.optics)
    print(f"Checked {len(records)} connections")
    problems = run_checks(records, optics)
    print("PASS" if problems == 0 else f"FAIL: {problems} blocking problem(s)")
    return 0 if problems == 0 else 1


def cmd_bom(args):
    records = load_connections(args.connections)
    optics = load_json(args.optics)
    usable = clean_rows(records, optics)
    print(f"BOM from {len(usable)} of {len(records)} connections (incomplete rows skipped)")
    for site, bom in bom_by_site(usable, optics).items():
        print(f"\n{site}")
        for part, qty in bom.items():
            print(f"  {qty:>4}  {part}")
    return 0


def cmd_diff(args):
    records = load_connections(args.connections)
    optics = load_json(args.optics)
    planned = build_bom(clean_rows(records, optics), optics)
    result = compare_inventory(planned, load_json(args.installed))
    for label in ("missing", "extra"):
        print(f"{label.upper()}:")
        for part, qty in result[label].items():
            print(f"  {qty:>4}  {part}")
        if not result[label]:
            print("  none")
    return 0 if not result["missing"] else 1


def cmd_reconcile(args):
    data = load_json(args.sources)
    merged, findings = reconcile(data["sources"], data["authority"])
    print("Merged record:")
    for field, value in merged.items():
        print(f"  {field}: {value}")
    print("Findings:")
    for field, severity, detail in findings:
        print(f"  {severity:<8} {field}: {detail}")
    if not findings:
        print("  none")
    return 1 if any(s == "BLOCKER" for _, s, _ in findings) else 0


def cmd_trace(args):
    with open(args.links, newline="", encoding="utf-8") as f:
        links = [(r["a"], r["b"], float(r["loss_db"])) for r in csv.DictReader(f)]
    graph = build_graph(links)
    if args.start not in graph or args.end not in graph:
        print("Start or end point not found in the link data")
        return 1
    hops = fewest_hops(graph, args.start, args.end)
    path, loss = lowest_loss(graph, args.start, args.end)
    if hops is None:
        print("No path found")
        return 1
    print("Fewest hops: " + " -> ".join(hops))
    print(f"Lowest loss: {' -> '.join(path)}  ({loss} dB)")
    if args.budget is not None:
        verdict = "within" if loss <= args.budget else "OVER"
        print(f"Loss budget {args.budget} dB: {verdict}")
    return 0


def cmd_triage(args):
    with open(args.log, encoding="utf-8") as f:
        alarms, bad = parse_log(f.read())
    with open(args.topology, newline="", encoding="utf-8") as f:
        ru_to_du = {(r["site"].upper(), r["ru"].upper()): r["du"].upper() for r in csv.DictReader(f)}

    collapsed = collapse_repeats(alarms)
    print(f"{len(alarms)} alarms -> {len(collapsed)} after collapsing repeats"
          + (f" ({len(bad)} unreadable lines: {bad})" if bad else ""))

    print("\nSites, worst first:")
    for site, worst, counts in site_summary(alarms):
        detail = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        print(f"  {site:<10} {worst:<9} {detail}")

    print("\nProbable upstream cause (several RUs alarming under one DU):")
    upstream = probable_upstream(alarms, ru_to_du)
    for site, du, rus in upstream:
        print(f"  {site} {du}: {', '.join(rus)} -> check {du} and its fronthaul/transport first")
    if not upstream:
        print("  none")

    print("\nCollapsed alarms:")
    for a in sorted(collapsed, key=lambda a: (-SEVERITY_RANK[a["severity"]], a["site"], a["node"])):
        print(f"  {a['severity']:<9} {a['site']} {a['node']:<5} x{a['count']}  {a['text']}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pre-deployment checks for network build data")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="validate connection records")
    p.add_argument("connections")
    p.add_argument("--optics", required=True)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("bom", help="build a bill of materials per site")
    p.add_argument("connections")
    p.add_argument("--optics", required=True)
    p.set_defaults(func=cmd_bom)

    p = sub.add_parser("diff", help="compare planned BOM with installed inventory")
    p.add_argument("connections")
    p.add_argument("--optics", required=True)
    p.add_argument("--installed", required=True)
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("reconcile", help="merge one record from several source systems")
    p.add_argument("sources")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("trace", help="find a fiber path and its loss")
    p.add_argument("links")
    p.add_argument("start")
    p.add_argument("end")
    p.add_argument("--budget", type=float, help="maximum allowed loss in dB")
    p.set_defaults(func=cmd_trace)

    p = sub.add_parser("triage", help="summarize a RAN alarm log and point at likely upstream causes")
    p.add_argument("log")
    p.add_argument("topology")
    p.set_defaults(func=cmd_triage)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
