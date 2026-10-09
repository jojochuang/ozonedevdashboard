#!/usr/bin/env python3
"""Fetch merged-PR velocity metrics for apache/ozone via GitHub GraphQL (gh CLI)."""

from __future__ import annotations

import argparse
import calendar
import json
import subprocess
import sys
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

REPO_OWNER = "apache"
REPO_NAME = "ozone"
PAGE_SIZE = 50
REPO = f"{REPO_OWNER}/{REPO_NAME}"

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
        title
        createdAt
        mergedAt
        author { login }
        additions
        deletions
        changedFiles
        reviews(first: 20) {
          totalCount
          nodes { submittedAt state }
        }
        comments { totalCount }
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


def gh_search_count(query: str, attempt: int = 0) -> int:
  try:
    path = f"search/issues?q={urllib.parse.quote(query)}"
    out = subprocess.check_output(
        ["gh", "api", path, "--jq", ".total_count"],
        text=True,
        stderr=subprocess.STDOUT,
    )
    return int(out.strip())
  except subprocess.CalledProcessError as e:
    if attempt < 3:
      import time
      time.sleep(10 * (attempt + 1))
      return gh_search_count(query, attempt + 1)
    raise RuntimeError(e.output) from e


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


def month_range(start: datetime, end: datetime) -> List[str]:
  keys: List[str] = []
  y, m = start.year, start.month
  while (y, m) <= (end.year, end.month):
    keys.append(f"{y:04d}-{m:02d}")
    m += 1
    if m > 12:
      m = 1
      y += 1
  return keys


def aggregate_opened_issues(month_map: Dict[str, int]) -> Tuple[Dict[str, int], Dict[str, int]]:
  quarters: Dict[str, int] = defaultdict(int)
  years: Dict[str, int] = defaultdict(int)
  for mo, count in month_map.items():
    y = mo[:4]
    qn = (int(mo[5:7]) - 1) // 3 + 1
    quarters[f"{y}-Q{qn}"] += count
    years[y] += count
  return dict(quarters), dict(years)


@dataclass
class Bucket:
  merged: int = 0
  lead_hours: List[float] = field(default_factory=list)
  review_hours: List[float] = field(default_factory=list)
  post_review_hours: List[float] = field(default_factory=list)
  ci_success: int = 0
  ci_failure: int = 0
  ci_other: int = 0
  ci_unknown: int = 0
  authors: Set[str] = field(default_factory=set)
  changed_files: List[float] = field(default_factory=list)
  lines_changed: List[float] = field(default_factory=list)
  review_counts: List[float] = field(default_factory=list)
  comment_counts: List[float] = field(default_factory=list)
  reverts: int = 0
  bot_merges: int = 0
  opened: int = 0
  issues_closed: int = 0


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
  post = sorted(b.post_review_hours)
  files = sorted(b.changed_files)
  lines = sorted(b.lines_changed)
  rc = sorted(b.review_counts)
  cc = sorted(b.comment_counts)
  ci_known = b.ci_success + b.ci_failure + b.ci_other
  return {
      "merged": b.merged,
      "opened": b.opened,
      "flow_ratio": (b.merged / b.opened) if b.opened else None,
      "issues_closed": b.issues_closed,
      "unique_contributors": len(b.authors),
      "reverts": b.reverts,
      "revert_rate_pct": (100.0 * b.reverts / b.merged) if b.merged else None,
      "bot_merge_pct": (100.0 * b.bot_merges / b.merged) if b.merged else None,
      "lead_p50_h": percentile(lead, 0.50),
      "lead_p90_h": percentile(lead, 0.90),
      "review_p50_h": percentile(rev, 0.50) if rev else None,
      "review_p90_h": percentile(rev, 0.90) if rev else None,
      "post_review_p50_h": percentile(post, 0.50) if post else None,
      "post_review_p90_h": percentile(post, 0.90) if post else None,
      "review_coverage_pct": (100.0 * len(rev) / b.merged) if b.merged else 0.0,
      "files_p50": percentile(files, 0.50),
      "files_p90": percentile(files, 0.90),
      "lines_p50": percentile(lines, 0.50),
      "lines_p90": percentile(lines, 0.90),
      "reviews_per_pr_p50": percentile(rc, 0.50),
      "reviews_per_pr_p90": percentile(rc, 0.90),
      "comments_p50": percentile(cc, 0.50),
      "comments_p90": percentile(cc, 0.90),
      "ci_pass_rate_pct": (100.0 * b.ci_success / ci_known) if ci_known else None,
      "ci_known_n": ci_known,
      "ci_success": b.ci_success,
      "ci_failure": b.ci_failure,
      "ci_other": b.ci_other,
      "ci_unknown": b.ci_unknown,
  }


def is_bot_login(login: Optional[str]) -> bool:
  if not login:
    return False
  low = login.lower()
  return low.endswith("[bot]") or low in ("dependabot", "github-actions")


def add_merged_pr(
    buckets: Dict[str, Bucket],
    key: str,
    lead_h: float,
    review_h: Optional[float],
    ci: Optional[str],
    author: Optional[str],
    changed_files: int,
    lines: int,
    review_count: int,
    comment_count: int,
    is_revert: bool,
    is_bot: bool,
) -> None:
  b = buckets[key]
  b.merged += 1
  b.lead_hours.append(lead_h)
  if review_h is not None:
    b.review_hours.append(review_h)
    b.post_review_hours.append(max(0.0, lead_h - review_h))
  if author:
    b.authors.add(author)
  b.changed_files.append(float(changed_files))
  b.lines_changed.append(float(lines))
  b.review_counts.append(float(review_count))
  b.comment_counts.append(float(comment_count))
  if is_revert:
    b.reverts += 1
  if is_bot:
    b.bot_merges += 1
  if ci is None:
    b.ci_unknown += 1
  elif ci == "SUCCESS":
    b.ci_success += 1
  elif ci == "FAILURE":
    b.ci_failure += 1
  else:
    b.ci_other += 1


def fetch_search_counts_by_month(kind: str, start: datetime, end: datetime) -> Dict[str, int]:
  """kind: prs_opened or issues_closed."""
  result: Dict[str, int] = {}
  for mo in month_range(start, end):
    y = int(mo[:4])
    m = int(mo[5:7])
    last = calendar.monthrange(y, m)[1]
    end_day = f"{y}-{m:02d}-{last:02d}"
    if kind == "prs_opened":
      q = f"repo:{REPO} is:pr created:{mo}-01..{end_day}"
    elif kind == "issues_closed":
      q = f"repo:{REPO} is:issue is:closed closed:{mo}-01..{end_day}"
    else:
      raise ValueError(kind)
    result[mo] = gh_search_count(q)
    print(f"  {mo}: {result[mo]}", file=sys.stderr)
    import time
    time.sleep(0.5)
  return result


def fetch_snapshot() -> dict:
  out = subprocess.check_output(
      [
          "gh", "api", "graphql", "-f",
          "query={ repository(owner:\"apache\", name:\"ozone\") { open: pullRequests(states: OPEN) { totalCount } } }",
      ],
      text=True,
  )
  open_total = json.loads(out)["data"]["repository"]["open"]["totalCount"]
  open_json = subprocess.check_output(
      [
          "gh", "pr", "list", "--repo", REPO, "--state", "open", "--limit", "500",
          "--json", "updatedAt",
      ],
      text=True,
  )
  open_prs = json.loads(open_json)
  now = datetime.now(timezone.utc)
  stale_30 = 0
  for pr in open_prs:
    updated = parse_ts(pr["updatedAt"])
    if (now - updated).total_seconds() > 30 * 86400:
      stale_30 += 1
  return {
      "open_prs_total": open_total,
      "open_prs_stale_30d_in_sample": stale_30,
      "open_prs_sample_size": len(open_prs),
  }


def merge_flow_counts(
    by_year: Dict[str, Bucket],
    by_quarter: Dict[str, Bucket],
    by_month: Dict[str, Bucket],
    opened_month: Dict[str, int],
    opened_quarter: Dict[str, int],
    opened_year: Dict[str, int],
    issues_month: Dict[str, int],
    issues_quarter: Dict[str, int],
    issues_year: Dict[str, int],
) -> None:
  for k, v in opened_month.items():
    by_month[k].opened = v
  for k, v in opened_quarter.items():
    by_quarter[k].opened = v
  for k, v in opened_year.items():
    by_year[k].opened = v
  for k, v in issues_month.items():
    by_month[k].issues_closed = v
  for k, v in issues_quarter.items():
    by_quarter[k].issues_closed = v
  for k, v in issues_year.items():
    by_year[k].issues_closed = v


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
      review_nodes = (p.get("reviews") or {}).get("nodes") or []
      rev_h = first_review_time(created, review_nodes)
      review_total = (p.get("reviews") or {}).get("totalCount") or len(review_nodes)
      commits = (p.get("commits") or {}).get("nodes") or []
      ci = ci_state(commits)
      author = (p.get("author") or {}).get("login")
      title = (p.get("title") or "").strip()
      additions = int(p.get("additions") or 0)
      deletions = int(p.get("deletions") or 0)
      changed = int(p.get("changedFiles") or 0)
      comments = int((p.get("comments") or {}).get("totalCount") or 0)

      y, q, mo = period_keys(merged)
      for bucket_map, key in ((by_year, y), (by_quarter, q), (by_month, mo)):
        add_merged_pr(
            bucket_map,
            key,
            lead_h,
            rev_h,
            ci,
            author,
            changed,
            additions + deletions,
            review_total,
            comments,
            title.lower().startswith("revert"),
            is_bot_login(author),
        )
      total += 1

    if total % 1000 == 0:
      print(f"Processed {total} merged PRs...", file=sys.stderr)
    if total_count is not None and nodes_seen >= total_count:
      break
    if not prs["pageInfo"]["hasNextPage"]:
      break
    cursor = end

  print("Fetching PRs opened by month (search API)...", file=sys.stderr)
  start = datetime(2019, 10, 1, tzinfo=timezone.utc)
  end = datetime.now(timezone.utc)
  opened_month = fetch_search_counts_by_month("prs_opened", start, end)
  opened_quarter, opened_year = aggregate_opened_issues(opened_month)

  print("Fetching issues closed by month (search API)...", file=sys.stderr)
  issues_month = fetch_search_counts_by_month("issues_closed", start, end)
  issues_quarter, issues_year = aggregate_opened_issues(issues_month)

  merge_flow_counts(
      by_year, by_quarter, by_month,
      opened_month, opened_quarter, opened_year,
      issues_month, issues_quarter, issues_year,
  )

  snapshot = fetch_snapshot()

  year_keys = sorted(by_year.keys())
  quarter_keys = sorted(by_quarter.keys())
  month_keys = sorted(by_month.keys())
  return {
      "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
      "repository": REPO,
      "total_merged_prs": total,
      "snapshot": snapshot,
      "metric_definitions": {
          "merged": "PRs merged in period (by mergedAt)",
          "opened": "PRs created in period (GitHub search, includes unmerged)",
          "flow_ratio": "merged / opened in same calendar period",
          "issues_closed": "GitHub issues closed in period",
          "unique_contributors": "Distinct PR authors among merges in period",
          "post_review_p50_h": "Median hours from first review submission to merge",
          "files_p50": "Median changed files per merged PR",
          "lines_p50": "Median lines added+deleted per merged PR",
          "reviews_per_pr_p50": "Median formal review submissions per merged PR",
          "comments_p50": "Median issue-style PR comments (not review threads)",
          "revert_rate_pct": "Share of merges whose title starts with Revert",
          "bot_merge_pct": "Share of merges authored by *bot accounts",
      },
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
  from pathlib import Path
  Path(args.output).parent.mkdir(parents=True, exist_ok=True)
  with open(args.output, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
  print(f"Wrote {args.output} ({payload['total_merged_prs']} merged PRs)", file=sys.stderr)
  return 0


if __name__ == "__main__":
  sys.exit(main())
