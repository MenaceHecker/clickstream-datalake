# Phase 8 — Dashboard: Notebook Fallback (chosen over QuickSight)

## Decision

Built as a Python script (`dashboard_notebook.py`) querying Athena
directly via boto3 and rendering charts with matplotlib, instead of a
QuickSight dashboard.

**Why**: QuickSight bills on its own separate pricing/trial structure
outside the $200 AWS Free Tier credit pool this entire project is scoped
against (flagged explicitly in the project's risk register). Since this
project's cost story is part of its own resume value — cost guardrails,
budget tracking, tagged Cost Explorer views — introducing a
billing surface that sits *outside* that tracked pool undercuts the
premise. The notebook route keeps 100% of this project's spend inside
one pool, one set of Budgets alerts, one Cost Explorer tag filter.

This is also documented as an itself-valid trade-off: "chose a
boto3+matplotlib fallback over QuickSight specifically to keep cost
tracking unified" is a real, defensible engineering decision — and if
asked in an interview whether you've used QuickSight, the honest answer
here is straightforward: no, deliberately, and here's why.

## What it does

`dashboard_notebook.py` runs three Athena queries and produces the same
three visuals a QuickSight dashboard would show:

1. **Funnel chart** — product_view → add_to_cart → checkout_start →
   purchase, as a horizontal bar chart with counts labeled
2. **Revenue trend** — daily revenue over time, line chart
3. **Revenue by country/device** — stacked bar chart

All three chart-building functions were tested locally against
synthetic data shaped exactly like the real query results (including
edge cases: a country/device combination that doesn't exist renders as
zero rather than crashing pivot_table; a date gap in the trend renders
as a visible gap in the line rather than an error) before ever pointing
this at a live Athena connection.

## Structure

Uses `# %%` cell markers so it opens as a notebook-like experience in
VS Code or Jupyter (each `# %%` block runs as its own cell), but also
executes top-to-bottom as a plain script — no notebook runtime
dependency required.

## Running it

```bash
source venv/bin/activate
pip install -r quicksight/requirements.txt
cd quicksight
python dashboard_notebook.py
```

Requires:
- The curated Glue table (Phase 6) to exist and be populated
- Athena's query result location already configured (Phase 7)
- `clickstream-dev`'s existing IAM permissions cover this — Athena query
  execution and S3 read on `athena-results/` were already granted in
  earlier phases, no policy changes needed for this one

Output: three PNGs written to `docs/` —
`dashboard-funnel.png`, `dashboard-revenue-trend.png`,
`dashboard-device-country.png` — ready to drop into the Phase 10 README.

## Definition of done

- [ ] Script runs end-to-end against live Athena data without error
- [ ] All three PNGs generated in `docs/`
- [ ] Charts show real numbers from the pipeline (not synthetic test data)
- [ ] Decision rationale documented (this file)