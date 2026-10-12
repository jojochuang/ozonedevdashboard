# Ozone Dev Dashboard

Static dashboard for [apache/ozone](https://github.com/apache/ozone) pull-request velocity:

- PRs **opened** vs **merged**, flow ratio, open-PR snapshot (stale &gt;30d)
- **Approval → merge** (human `APPROVED`, Copilot excluded), **slow merges (&gt;14d)**, **open PR queue** history
- PR lead time and **post-review → merge** wait (p50 / p90)
- **CI fail-before-merge** (FAILURE on last 15 commits) alongside head pass rate
- Time to first review (p50 / p90)
- **Unique contributors**, PR **size** (files/lines), **reviews** and **comments** per PR
- **Revert rate**, **issues closed** (GitHub)
- CI pass rate (GitHub check rollup on PR head)

Published at **https://jojochuang.github.io/ozonedevdashboard/** (GitHub Pages).

Pages:

- **Velocity** (`index.html`) — PR flow, lead time, CI
- **Contributors** (`contributors.html`) — ranked submitted / reviewed / merged-by by month, quarter, or year

## Local preview

```bash
python3 scripts/fetch_pr_velocity.py -o data/metrics.json   # requires `gh auth login`
python3 -m http.server 8080
# open http://localhost:8080/
```

## Automation

Workflow [`.github/workflows/update-dashboard.yml`](.github/workflows/update-dashboard.yml) runs on the **1st of each month** (09:00 UTC) and via **workflow_dispatch**. It fetches metrics with `GITHUB_TOKEN`, builds the site, and deploys to GitHub Pages.

Repository **Settings → Pages → Build and deployment** must use **GitHub Actions** as the source.
