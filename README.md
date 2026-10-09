# Ozone Dev Dashboard

Static dashboard for [apache/ozone](https://github.com/apache/ozone) pull-request velocity:

- PRs **opened** vs **merged**, flow ratio, open-PR snapshot (stale &gt;30d)
- PR lead time and **post-review → merge** wait (p50 / p90)
- Time to first review (p50 / p90)
- **Unique contributors**, PR **size** (files/lines), **reviews** and **comments** per PR
- **Revert rate**, **issues closed** (GitHub)
- CI pass rate (GitHub check rollup on PR head)

Published at **https://jojochuang.github.io/ozonedevdashboard/** (GitHub Pages).

## Local preview

```bash
python3 scripts/fetch_pr_velocity.py -o data/metrics.json   # requires `gh auth login`
python3 -m http.server 8080
# open http://localhost:8080/
```

## Automation

Workflow [`.github/workflows/update-dashboard.yml`](.github/workflows/update-dashboard.yml) runs on the **1st of each month** (09:00 UTC) and via **workflow_dispatch**. It fetches metrics with `GITHUB_TOKEN`, builds the site, and deploys to GitHub Pages.

Repository **Settings → Pages → Build and deployment** must use **GitHub Actions** as the source.
