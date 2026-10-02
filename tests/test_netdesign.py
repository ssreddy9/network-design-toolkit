import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from netdesign.bom import build_bom, compare_inventory
from netdesign.checks import duplicate_ports, missing_fields, unknown_cable_types
from netdesign.paths import build_graph, fewest_hops, lowest_loss
from netdesign.reconcile import reconcile
from netdesign.records import normalize_port, parse_connections_csv

OPTICS = {"SM-LC": "LR4", "MM-MPO": "SR4"}

CSV = """site,rack,a_device,a_port,z_device,z_port,cable_type
DEN1,R12,RTR1,Eth1/1,spine1,Ethernet1/1,SM-LC
DEN1,R12,spine1, et1/1 ,leaf1,Eth1/49,MM-MPO
DEN1,R14,leaf2,Eth1/49,,Eth1/50,DAC
"""


class TestRecords(unittest.TestCase):
    def test_normalize_port(self):
        self.assertEqual(normalize_port("Eth1/1"), "Ethernet1/1")
        self.assertEqual(normalize_port(" et1/2 "), "Ethernet1/2")
        self.assertEqual(normalize_port("ETHERNET1/3"), "Ethernet1/3")
        self.assertEqual(normalize_port("mgmt0"), "mgmt0")

    def test_parse_cleans_names(self):
        rows = parse_connections_csv(CSV)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["a_device"], "rtr1")
        self.assertEqual(rows[1]["a_port"], "Ethernet1/1")


class TestChecks(unittest.TestCase):
    def setUp(self):
        self.rows = parse_connections_csv(CSV)

    def test_missing_fields(self):
        self.assertEqual(missing_fields(self.rows), [(4, ["z_device"])])

    def test_duplicate_found_after_normalizing(self):
        # spine1 Ethernet1/1 is the Z end of line 2 and the A end of line 3
        self.assertEqual(duplicate_ports(self.rows), {("spine1", "Ethernet1/1"): [2, 3]})

    def test_unknown_cable_type(self):
        self.assertEqual(unknown_cable_types(self.rows, OPTICS), [(4, "DAC")])

    def test_empty_input(self):
        self.assertEqual(missing_fields([]), [])
        self.assertEqual(duplicate_ports([]), {})


class TestBom(unittest.TestCase):
    def test_two_optics_per_connection(self):
        rows = parse_connections_csv(CSV)[:2]
        self.assertEqual(build_bom(rows, OPTICS),
                         {"CABLE MM-MPO": 1, "CABLE SM-LC": 1, "OPTIC LR4": 2, "OPTIC SR4": 2})

    def test_spares_round_up(self):
        rows = parse_connections_csv(CSV)[:1]
        self.assertEqual(build_bom(rows, OPTICS, spare_pct=10)["OPTIC LR4"], 3)

    def test_compare_inventory(self):
        result = compare_inventory({"A": 4, "B": 2}, {"A": 3, "C": 1})
        self.assertEqual(result, {"missing": {"A": 1, "B": 2}, "extra": {"C": 1}})


class TestReconcile(unittest.TestCase):
    def test_owner_wins_and_conflict_reported(self):
        merged, findings = reconcile(
            {"design": {"rack": "R12"}, "dcim": {"rack": "R14"}},
            {"rack": "dcim"})
        self.assertEqual(merged, {"rack": "R14"})
        self.assertEqual(findings[0][1], "WARNING")

    def test_missing_owner_value_blocks(self):
        merged, findings = reconcile({"design": {"rack": "R12"}}, {"rack": "dcim"})
        self.assertEqual(merged, {})
        self.assertEqual(findings[0][1], "BLOCKER")


class TestPaths(unittest.TestCase):
    def setUp(self):
        # Short path is lossy; the longer path has less loss.
        self.graph = build_graph([
            ("A", "B", 2.0), ("B", "D", 2.0),
            ("A", "C", 0.5), ("C", "E", 0.5), ("E", "D", 0.5),
            ("X", "Y", 0.1),
        ])

    def test_fewest_hops(self):
        self.assertEqual(fewest_hops(self.graph, "A", "D"), ["A", "B", "D"])

    def test_lowest_loss(self):
        self.assertEqual(lowest_loss(self.graph, "A", "D"), (["A", "C", "E", "D"], 1.5))

    def test_no_path(self):
        self.assertIsNone(fewest_hops(self.graph, "A", "Y"))
        self.assertEqual(lowest_loss(self.graph, "A", "Y"), (None, None))

    def test_start_equals_end(self):
        self.assertEqual(fewest_hops(self.graph, "A", "A"), ["A"])



from netdesign.alarms import collapse_repeats, parse_alarm_line, parse_log, probable_upstream, site_summary

LOG = """# comment
2026-09-14T08:01:10 | DEN-1 | RU-1 | CRITICAL | Link down
2026-09-14T08:01:12 | DEN-1 | RU-2 | critical | Link down
2026-09-14T08:01:40 | DEN-1 | RU-1 | CRITICAL | Link down
2026-09-14T08:05:00 | DEN-2 | RU-1 | MINOR | VSWR high
bad line
2026-09-14T08:06:00 | DEN-2 | RU-1 | NOPE | unknown severity
"""
TOPO = {("DEN-1", "RU-1"): "DU-1", ("DEN-1", "RU-2"): "DU-1", ("DEN-2", "RU-1"): "DU-1"}


class TestAlarms(unittest.TestCase):
    def test_parse_skips_bad_lines(self):
        alarms, bad = parse_log(LOG)
        self.assertEqual(len(alarms), 4)
        self.assertEqual(bad, [6, 7])

    def test_severity_normalized(self):
        self.assertEqual(parse_alarm_line("2026-09-14T08:01:12 | den-1 | ru-2 | critical | x")["severity"], "CRITICAL")

    def test_collapse_counts_repeats(self):
        alarms, _ = parse_log(LOG)
        collapsed = {(a["site"], a["node"]): a["count"] for a in collapse_repeats(alarms)}
        self.assertEqual(collapsed[("DEN-1", "RU-1")], 2)

    def test_probable_upstream(self):
        alarms, _ = parse_log(LOG)
        self.assertEqual(probable_upstream(alarms, TOPO), [("DEN-1", "DU-1", ["RU-1", "RU-2"])])

    def test_minor_alarms_do_not_trigger_upstream(self):
        alarms, _ = parse_log(LOG)
        self.assertEqual(probable_upstream(alarms, TOPO, min_rus=1)[-1][0], "DEN-1")

    def test_site_summary_worst_first(self):
        alarms, _ = parse_log(LOG)
        self.assertEqual([r[0] for r in site_summary(alarms)], ["DEN-1", "DEN-2"])

if __name__ == "__main__":
    unittest.main()
