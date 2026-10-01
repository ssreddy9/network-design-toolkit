"""Validation checks to run before a design package is released."""

from collections import defaultdict

from .records import CONNECTION_FIELDS


def missing_fields(records, required=CONNECTION_FIELDS):
    """Return (row_number, [missing fields]) for every incomplete record.

    Row numbers start at 2 so they match the line in the CSV file (line 1 is the header).
    """
    errors = []
    for i, rec in enumerate(records, start=2):
        missing = [f for f in required if not str(rec.get(f, "")).strip()]
        if missing:
            errors.append((i, missing))
    return errors


def duplicate_ports(records):
    """Find any (device, port) used by more than one connection, on either end."""
    usage = defaultdict(list)
    for i, rec in enumerate(records, start=2):
        for side in ("a", "z"):
            device, port = rec.get(f"{side}_device"), rec.get(f"{side}_port")
            if device and port:
                usage[(device, port)].append(i)
    return {key: rows for key, rows in usage.items() if len(rows) > 1}


def unknown_cable_types(records, known_types):
    """Return rows whose cable type has no optic mapping."""
    return [(i, rec.get("cable_type", "")) for i, rec in enumerate(records, start=2)
            if rec.get("cable_type") and rec["cable_type"] not in known_types]
