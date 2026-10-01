# network-design-toolkit

Small Python tools for checking network build data before it goes to a field team.

I built this to practice the pre-deployment side of network builds: the checks that should happen before anyone racks a device or runs a cable. In my field and transport work, most delays I've seen come from the design and the site not lining up, like a port used twice, a missing optic, or a cable that isn't on the shipment. These scripts try to catch that kind of problem earlier.

Standard library only (Python 3.9+). The sample data in `data/` is made up.

## What it does

| Command | What it checks |
| --- | --- |
| `check` | Missing fields, ports assigned twice (either end), cable types with no optic mapping |
| `bom` | Bill of materials per site: one cable and two optics per connection |
| `diff` | Planned BOM vs installed inventory: what's missing and what's extra |
| `reconcile` | Merges one record from several source systems using field ownership |
| `trace` | Fewest-hop and lowest-loss path through panels, trunks and splices, with a loss budget check |

## Run it

```bash
python cli.py check data/connections.csv --optics data/optics.json
python cli.py bom data/connections.csv --optics data/optics.json
python cli.py diff data/connections.csv --optics data/optics.json --installed data/installed.json
python cli.py reconcile data/sources.json
python cli.py trace data/fiber_links.csv rtr1:Ethernet1/1 spine1:Ethernet1/1 --budget 2.0
python -m unittest discover -s tests
```

`check`, `diff` and `reconcile` exit with code 1 when something should block a release, so they could be used in a CI pipeline.

## Sample output

```
$ python cli.py check data/connections.csv --optics data/optics.json
Checked 8 connections
  BLOCKER  line 7: missing z_device
  BLOCKER  spine1 Ethernet1/49 used on lines [4, 6]
  BLOCKER  line 9: no optic mapping for cable type 'DAC'
FAIL: 3 blocking problem(s)
```

The duplicate on lines 4 and 6 is only caught because port names are normalized first. One row says `Ethernet1/49` and the other says `et1/49`.

```
$ python cli.py trace data/fiber_links.csv rtr1:Ethernet1/1 spine1:Ethernet1/1 --budget 2.0
Fewest hops: rtr1:Ethernet1/1 -> ODF-A:01 -> TRUNK7:F01 -> ODF-B:01 -> spine1:Ethernet1/1
Lowest loss: rtr1:Ethernet1/1 -> ODF-A:01 -> MMR:P14 -> TRUNK9:F05 -> ODF-B:01 -> spine1:Ethernet1/1  (1.8 dB)
Loss budget 2.0 dB: within
```

The shortest path isn't always the best one. Here the direct trunk has a lossy segment, so the route through the meet-me room has less total loss.

## Design choices

- **Collect every error, don't stop at the first.** Whoever fixes the data should see all of it in one pass.
- **Normalize before comparing.** `Eth1/1`, `et1/1` and `Ethernet1/1` are the same port. Without this, duplicates hide.
- **Field ownership, not "newest wins".** In `reconcile`, each field has one owning system. Its value is used, and any system that disagrees is reported as a finding instead of being silently overwritten. A field whose owner has no value is a blocker.
- **BFS for hops, Dijkstra for loss.** Fewest hops treats every segment the same. Lowest loss uses each segment's insertion loss as the weight.

## Layout

```
netdesign/
  records.py    CSV/JSON loading, port name normalization
  checks.py     missing fields, duplicate ports, unknown cable types
  bom.py        BOM per site, planned vs installed
  reconcile.py  merge by field ownership
  paths.py      fewest-hop and lowest-loss path
cli.py          command-line entry point
tests/          unit tests
data/           sample data
```

## Next

- Real loss model: per-km fiber loss plus connector and splice counts
- Polarity check through each segment
- Route diversity check so redundant links don't share a trunk
