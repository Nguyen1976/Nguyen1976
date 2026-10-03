"""Fetches the last 53 weeks of daily contributions into data/calendar.json.

Adapted from https://github.com/georgekobaidze/georgekobaidze (tools/profile/fetch.py).

Environment variables:
  PROFILE_TOKEN  optional personal access token; lets the city include private work.
  GITHUB_TOKEN   the token GitHub Actions provides automatically (public data only).

If the fetch fails, the previous calendar.json is left untouched.
"""
import datetime
import json
import os
import pathlib
import sys
import urllib.request

USER = "Nguyen1976"
DATA = pathlib.Path(__file__).resolve().parent / "data"


def graphql(token, query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": f"{USER}-contribution-city"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read().decode())
    if res.get("errors"):
        raise RuntimeError("GraphQL error: " + "; ".join(e.get("message", "?") for e in res["errors"]))
    return res["data"]


def calendar_query(start, today):
    # a contributionsCollection may span at most one year, so ask once per calendar year
    parts = []
    for y in range(start.year, today.year + 1):
        lo, hi = max(start, datetime.date(y, 1, 1)), min(today, datetime.date(y, 12, 31))
        parts.append(f"""
    y{y}: contributionsCollection(from: "{lo}T00:00:00Z", to: "{hi}T23:59:59Z") {{
      contributionCalendar {{ weeks {{ contributionDays {{ date contributionCount }} }} }}
    }}""")
    return "query($login: String!) {\n  user(login: $login) {\n    name" + "".join(parts) + "\n  }\n}"


def fetch(token, today):
    # last 53 weeks, starting on a Sunday like GitHub's own graph
    start = today - datetime.timedelta(weeks=52)
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)
    user = graphql(token, calendar_query(start, today), {"login": USER})["user"]
    name = user.pop("name") or USER
    days = {}
    for coll in user.values():
        for w in coll["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[datetime.date.fromisoformat(d["date"])] = d["contributionCount"]
    return name, [[d.isoformat(), days.get(d, 0)] for d in
                  (start + datetime.timedelta(days=i) for i in range((today - start).days + 1))]


def main():
    token = os.environ.get("PROFILE_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("error: set PROFILE_TOKEN or GITHUB_TOKEN")
    today = datetime.datetime.now(datetime.timezone.utc).date()
    try:
        name, days = fetch(token, today)
    except Exception as ex:  # noqa: BLE001
        sys.exit(f"error: GitHub fetch failed, keeping previous calendar: {ex}")
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "calendar.json").write_text(json.dumps({"updated": today.isoformat(), "name": name, "days": days},
                                                   indent=1, ensure_ascii=False) + "\n")
    print(f"calendar: {len(days)} days, {sum(n for _, n in days)} contributions")


if __name__ == "__main__":
    main()
