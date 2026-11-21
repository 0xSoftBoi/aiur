# STRATO hardware data

Everything in this directory is data that tools read; the prose is in
[docs/strato/hardware.md](../../docs/strato/hardware.md).

| Path | What | Maintained by |
| --- | --- | --- |
| `avionics/components.csv` | every electrical part: mass, price, voltage, power, cold rating, location, provenance | hand |
| `avionics/ports.csv` | every port on every part | hand |
| `avionics/connections.csv` | every wire: net, endpoints, kind, gauge, length, connector | hand |
| `bom-*.csv` | purchasable bill of materials per design | `python tools/strato_export.py` |
| `design-points/*.json` | full sized budget per design | `python tools/strato_export.py` |

Review the harness after any edit:

```
python -m aiur.strato.harness --check-budget
python -m aiur.strato.harness --svg docs/strato/img/harness-s2.svg
```

Prices and masses tagged `estimate` are placeholders until a quote or a
scale says otherwise; `cited` ones trace to docs/strato/references.md.
