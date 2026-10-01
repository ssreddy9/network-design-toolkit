"""Command-line entry point.

Examples:
    python cli.py check data/connections.csv --optics data/optics.json
    python cli.py bom data/connections.csv --optics data/optics.json
    python cli.py diff data/connections.csv --optics data/optics.json --installed data/installed.json
    python cli.py reconcile data/sources.json
    python cli.py trace data/fiber_links.csv rtr1:Ethernet1/1 spine1:Ethernet1/1
"""

import argparse
import csv
import sys

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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
