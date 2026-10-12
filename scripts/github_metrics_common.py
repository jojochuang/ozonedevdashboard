"""Shared GitHub GraphQL helpers for Ozone dev dashboard fetch scripts."""

from __future__ import annotations

import json
import subprocess
import urllib.parse
from datetime import datetime
from typing import List, Optional, Tuple

REPO_OWNER = "apache"
REPO_NAME = "ozone"
PAGE_SIZE = 50
REPO = f"{REPO_OWNER}/{REPO_NAME}"

AUTOMATED_REVIEWER_LOGINS = frozenset({"copilot-pull-request-reviewer"})


def parse_ts(s: str) -> datetime:
  return datetime.fromisoformat(s.replace("Z", "+00:00"))


def period_keys(dt: datetime) -> Tuple[str, str, str]:
  y = dt.year
  m = dt.month
  q = (m - 1) // 3 + 1
  return (f"{y:04d}", f"{y:04d}-Q{q}", f"{y:04d}-{m:02d}")


def month_key(dt: datetime) -> str:
  return period_keys(dt)[2]


def is_automated_reviewer(login: Optional[str]) -> bool:
  if not login:
    return False
  low = login.lower()
  if low in AUTOMATED_REVIEWER_LOGINS:
    return True
  return "copilot" in low and "review" in low


def is_bot_login(login: Optional[str]) -> bool:
  if not login:
    return False
  low = login.lower()
  return low.endswith("[bot]") or low in ("dependabot", "github-actions")


def run_graphql(query: str, cursor: Optional[str] = None, attempt: int = 0) -> dict:
  cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
  if cursor:
    cmd.extend(["-f", f"cursor={cursor}"])
  try:
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
  except subprocess.CalledProcessError as e:
    if attempt < 5:
      import time
      time.sleep(15 * (attempt + 1))
      return run_graphql(query, cursor, attempt + 1)
    raise RuntimeError(e.output) from e
  data = json.loads(out)
  if data.get("errors"):
    msg = json.dumps(data["errors"])
    if attempt < 5 and ("rate limit" in msg.lower() or "secondary" in msg.lower()):
      import time
      time.sleep(60 * (attempt + 1))
      return run_graphql(query, cursor, attempt + 1)
    raise RuntimeError(data["errors"])
  return data


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
