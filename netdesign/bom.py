"""Build a bill of materials and compare it with what was installed."""

from collections import Counter, defaultdict


def build_bom(records, optic_for_cable, spare_pct=0):
    """Each connection needs one cable and one optic at each end.

    optic_for_cable maps a cable type (e.g. "SM-LC") to an optic part number.
    spare_pct adds spares to optics, rounded up (10 means +10%).
    """
    bom = Counter()
    for rec in records:
        cable = rec["cable_type"]
        bom[f"CABLE {cable}"] += 1
        bom[f"OPTIC {optic_for_cable[cable]}"] += 2

    if spare_pct:
        for part in list(bom):
            if part.startswith("OPTIC"):
                bom[part] += -(-bom[part] * spare_pct // 100)  # ceiling division
    return dict(sorted(bom.items()))


def bom_by_site(records, optic_for_cable):
    """Same BOM, split per site, so each site's shipment can be checked on its own."""
    by_site = defaultdict(list)
    for rec in records:
        by_site[rec["site"]].append(rec)
    return {site: build_bom(recs, optic_for_cable) for site, recs in sorted(by_site.items())}


def compare_inventory(planned, installed):
    """Return parts that are missing (planned > installed) and extra (installed > planned)."""
    p, i = Counter(planned), Counter(installed)
    return {"missing": dict(sorted((p - i).items())),
            "extra": dict(sorted((i - p).items()))}
