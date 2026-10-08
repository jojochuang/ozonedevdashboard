#!/usr/bin/env python3
"""Fetch merged-PR velocity metrics for apache/ozone via GitHub GraphQL (gh CLI)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

REPO_OWNER = "apache"
REPO_NAME = "ozone"
PAGE_SIZE = 50

QUERY = """
query($cursor: String) {
  repository(owner: "%s", name: "%s") {
    pullRequests(
      states: MERGED
      first: %d
      after: $cursor
      orderBy: {field: CREATED_AT, direction: ASC}
    ) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        createdAt
        mergedAt
        reviews(first: 20) {
          nodes { submittedAt state }
        }
        commits(last: 1) {
          nodes {
            commit {
              statusCheckRollup { state }
            }
          }
        }
      }
    }
  }
}
""" % (REPO_OWNER, REPO_NAME, PAGE_SIZE)


def parse_ts(s: str) -> datetime:
  return datetime.fromisoformat(s.replace("Z", "+00:00"))


def gh_graphql(cursor: Optional[str], attempt: int = 0) -> dict:
  cmd = ["gh", "api", "graphql", "-f", f"query={QUERY}"]
  if cursor:
    cmd.extend(["-f", f"cursor={cursor}"])
  try:
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
  except subprocess.CalledProcessError as e:
    if attempt < 5:
      import time
      time.sleep(15 * (attempt + 1))
      return gh_graphql(cursor, attempt + 1)
    raise RuntimeError(e.output) from e
  data = json.loads(out)
  if data.get("errors"):
    msg = json.dumps(data["errors"])
    if attempt < 5 and ("rate limit" in msg.lower() or "secondary" in msg.lower()):
      import time
      time.sleep(60 * (attempt + 1))
      return gh_graphql(cursor, attempt + 1)
    raise RuntimeError(data["errors"])
  return data["data"]["repository"]["pullRequests"]


def first_review_time(created: datetime, reviews: List[dict]) -> Optional[float]:
  best: Optional[datetime] = None
  for r in reviews:
    sub = r.get("submittedAt")
    if not sub:
      continue
    t = parse_ts(sub)
    if t <= created:
      continue
    if best is None or t < best:
      best = t
  if best is None:
    return None
  return (best - created).total_seconds() / 3600.0


def ci_state(commits_last: List[dict]) -> Optional[str]:
  if not commits_last:
    return None
  node = commits_last[0].get("commit") or {}
  rollup = node.get("statusCheckRollup")
  if not rollup:
    return None
  return rollup.get("state")


def period_keys(dt: datetime) -> Tuple[str, str, str]:
  y = dt.year
  m = dt.month
  q = (m - 1) // 3 + 1
  return (f"{y:04d}", f"{y:04d}-Q{q}", f"{y:04d}-{m:02d}")


@dataclass
class Bucket:
  merged: int = 0
  lead_hours: List[float] = field(default_factory=list)
  review_hours: List[float] = field(default_factory=list)
  ci_success: int = 0
  ci_failure: int = 0
  ci_other: int = 0
  ci_unknown: int = 0


def percentile(sorted_vals: List[float], p: float) -> Optional[float]:
  if not sorted_vals:
    return None
  if len(sorted_vals) == 1:
    return sorted_vals[0]
  k = (len(sorted_vals) - 1) * p
  f = int(k)
  c = min(f + 1, len(sorted_vals) - 1)
  if f == c:
    return sorted_vals[f]
  return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def summarize(b: Bucket) -> dict:
  lead = sorted(b.lead_hours)
  rev = sorted(b.review_hours)
  ci_known = b.ci_success + b.ci_failure + b.ci_other
  return {
      "merged": b.merged,
      "lead_p50_h": percentile(lead, 0.50),
      "lead_p90_h": percentile(lead, 0.90),
      "review_p50_h": percentile(rev, 0.50) if rev else None,
      "review_p90_h": percentile(rev, 0.90) if rev else None,
      "review_coverage_pct": (100.0 * len(rev) / b.merged) if b.merged else 0.0,
      "ci_pass_rate_pct": (100.0 * b.ci_success / ci_known) if ci_known else None,
      "ci_known_n": ci_known,
      "ci_success": b.ci_success,
      "ci_failure": b.ci_failure,
      "ci_other": b.ci_other,
      "ci_unknown": b.ci_unknown,
  }


def add_pr(buckets: Dict[str, Bucket], key: str, lead_h: float, review_h: Optional[float], ci: Optional[str]) -> None:
  b = buckets[key]
  b.merged += 1
  b.lead_hours.append(lead_h)
  if review_h is not None:
    b.review_hours.append(review_h)
  if ci is None:
    b.ci_unknown += 1
  elif ci == "SUCCESS":
    b.ci_success += 1
  elif ci == "FAILURE":
    b.ci_failure += 1
  else:
    b.ci_other += 1


def fetch_all() -> dict:
  by_year: Dict[str, Bucket] = defaultdict(Bucket)
  by_quarter: Dict[str, Bucket] = defaultdict(Bucket)
  by_month: Dict[str, Bucket] = defaultdict(Bucket)

  cursor: Optional[str] = None
  total = 0
  nodes_seen = 0
  total_count: Optional[int] = None
  seen_cursors: set = set()
  while True:
    prs = gh_graphql(cursor)
    if total_count is None:
      total_count = prs.get("totalCount")
    nodes = prs["nodes"]
    if not nodes:
      break
    end = prs["pageInfo"]["endCursor"]
    if end in seen_cursors:
      print("Stopping: repeated GraphQL cursor", file=sys.stderr)
      break
    seen_cursors.add(end)
    nodes_seen += len(nodes)
    for p in nodes:
      merged_at = p.get("mergedAt")
      created_at = p.get("createdAt")
      if not merged_at or not created_at:
        continue
      merged = parse_ts(merged_at)
      created = parse_ts(created_at)
      lead_h = (merged - created).total_seconds() / 3600.0
      rev_h = first_review_time(created, (p.get("reviews") or {}).get("nodes") or [])
      commits = (p.get("commits") or {}).get("nodes") or []
      ci = ci_state(commits)

      y, q, mo = period_keys(merged)
      for bucket_map, key in ((by_year, y), (by_quarter, q), (by_month, mo)):
        add_pr(bucket_map, key, lead_h, rev_h, ci)
      total += 1

    if total % 1000 == 0:
      print(f"Processed {total} merged PRs...", file=sys.stderr)
    if total_count is not None and nodes_seen >= total_count:
      break
    if not prs["pageInfo"]["hasNextPage"]:
      break
    cursor = end

  year_keys = sorted(by_year.keys())
  quarter_keys = sorted(by_quarter.keys())
  month_keys = sorted(by_month.keys())
  return {
      "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
      "repository": f"{REPO_OWNER}/{REPO_NAME}",
      "total_merged_prs": total,
      "year": {k: summarize(by_year[k]) for k in year_keys},
      "quarter": {k: summarize(by_quarter[k]) for k in quarter_keys},
      "month": {k: summarize(by_month[k]) for k in month_keys},
  }


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "-o", "--output", default="data/metrics.json", help="Output JSON path (default: data/metrics.json)"
  )
  args = parser.parse_args()
  payload = fetch_all()
  with open(args.output, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
  print(f"Wrote {args.output} ({payload['total_merged_prs']} merged PRs)", file=sys.stderr)
  return 0


if __name__ == "__main__":
  sys.exit(main())
