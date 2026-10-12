#!/usr/bin/env python3
"""Fetch per-contributor PR activity for apache/ozone (submitted, reviewed, merged-by)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datetime import datetime, timezone
from typing import Dict, Optional

from github_metrics_common import (
    REPO,
    REPO_NAME,
    REPO_OWNER,
    PAGE_SIZE,
    is_automated_reviewer,
    month_key,
    parse_ts,
    run_graphql,
)

QUERY = """
query($cursor: String) {
  repository(owner: "%s", name: "%s") {
    pullRequests(
      states: [OPEN, MERGED, CLOSED]
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
        author { login }
        mergedBy { login }
        reviews(first: 50) {
          totalCount
          nodes { submittedAt author { login } }
        }
      }
    }
  }
}
""" % (REPO_OWNER, REPO_NAME, PAGE_SIZE)


def fetch_all() -> dict:
  by_month: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
      lambda: {
          "submitted_by_login": defaultdict(int),
          "reviews_by_login": defaultdict(int),
          "merges_by_login": defaultdict(int),
      }
  )
  reviews_truncated_pr_count = 0
  cursor: Optional[str] = None
  total_prs = 0
  nodes_seen = 0
  total_count: Optional[int] = None
  seen_cursors: set = set()

  while True:
    data = run_graphql(QUERY, cursor)
    prs = data["data"]["repository"]["pullRequests"]
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
      total_prs += 1
      created_at = p.get("createdAt")
      if created_at:
        author = (p.get("author") or {}).get("login")
        if author and not author.endswith("[bot]"):
          mo = month_key(parse_ts(created_at))
          by_month[mo]["submitted_by_login"][author] += 1

      merged_at = p.get("mergedAt")
      if merged_at:
        merger = (p.get("mergedBy") or {}).get("login")
        if merger:
          mo = month_key(parse_ts(merged_at))
          by_month[mo]["merges_by_login"][merger] += 1

      review_block = p.get("reviews") or {}
      review_nodes = review_block.get("nodes") or []
      review_total = review_block.get("totalCount") or len(review_nodes)
      if review_total > len(review_nodes):
        reviews_truncated_pr_count += 1
      for r in review_nodes:
        login = (r.get("author") or {}).get("login")
        if is_automated_reviewer(login):
          continue
        sub = r.get("submittedAt")
        if not sub or not login:
          continue
        mo = month_key(parse_ts(sub))
        by_month[mo]["reviews_by_login"][login] += 1

    if total_prs % 1000 == 0:
      print(f"Processed {total_prs} PRs...", file=sys.stderr)
    if total_count is not None and nodes_seen >= total_count:
      break
    if not prs["pageInfo"]["hasNextPage"]:
      break
    cursor = end

  month_out = {}
  for mo in sorted(by_month.keys()):
    bucket = by_month[mo]
    month_out[mo] = {
        "submitted_by_login": dict(sorted(bucket["submitted_by_login"].items())),
        "reviews_by_login": dict(sorted(bucket["reviews_by_login"].items())),
        "merges_by_login": dict(sorted(bucket["merges_by_login"].items())),
    }

  generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
  return {
      "generated_at": generated_at,
      "repository": REPO,
      "total_prs_scanned": total_prs,
      "review_excludes_automated": True,
      "reviews_truncated_pr_count": reviews_truncated_pr_count,
      "by_month": month_out,
      "metric_definitions": {
          "submitted_by_login": "PRs opened (author.login) in calendar month of createdAt",
          "reviews_by_login": "Formal review submissions in month of submittedAt; Copilot excluded",
          "merges_by_login": "Merged PRs in month of mergedAt credited to mergedBy.login",
      },
  }


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "-o", "--output", default="data/contributor_activity.json",
      help="Output JSON path (default: data/contributor_activity.json)",
  )
  args = parser.parse_args()
  payload = fetch_all()
  Path(args.output).parent.mkdir(parents=True, exist_ok=True)
  with open(args.output, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
  print(
      f"Wrote {args.output} ({payload['total_prs_scanned']} PRs, "
      f"{len(payload['by_month'])} months)",
      file=sys.stderr,
  )
  return 0


if __name__ == "__main__":
  sys.exit(main())
