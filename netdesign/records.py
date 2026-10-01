"""Load connection and inventory records from CSV and JSON files."""

import csv
import io
import json
import re


CONNECTION_FIELDS = ["site", "rack", "a_device", "a_port", "z_device", "z_port", "cable_type"]


def normalize_port(name):
    """Turn Eth1/1, ethernet1/1 or et1/1 into Ethernet1/1. Other names are kept as-is."""
    name = name.strip()
    match = re.fullmatch(r"(?i)(eth|ethernet|et)\s*([\d/]+)", name)
    if match:
        return "Ethernet" + match.group(2)
    return name


def clean_connection(row):
    """Strip spaces, lowercase device names and normalize port names."""
    rec = {k.strip(): (v or "").strip() for k, v in row.items() if k}
    for side in ("a", "z"):
        if rec.get(f"{side}_device"):
            rec[f"{side}_device"] = rec[f"{side}_device"].lower()
        if rec.get(f"{side}_port"):
            rec[f"{side}_port"] = normalize_port(rec[f"{side}_port"])
    return rec


def parse_connections_csv(text):
    """Parse CSV text into a list of cleaned connection dicts."""
    return [clean_connection(row) for row in csv.DictReader(io.StringIO(text))]


def load_connections(path):
    with open(path, newline="", encoding="utf-8") as f:
        return parse_connections_csv(f.read())


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
