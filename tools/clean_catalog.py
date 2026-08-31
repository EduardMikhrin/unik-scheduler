#!/usr/bin/env python3
"""Convert the hand-maintained catalog into the shape the bot imports.

Does three things:
  * drops the bookkeeping fields the bot never reads (department, credits,
    control, notes, meta) — they stay in your own copy if you want them;
  * renames `selected` to `default_selected`, which is what it actually is
    once several people use the bot: a starting point for new users;
  * fills in `api_alias` by comparing every course name against the live KPI
    schedule, so spelling drift on their side does not silently mute a course.

Usage:
    python tools/clean_catalog.py electives.json catalog.json
    python tools/clean_catalog.py electives.json catalog.json --offline
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.campus.kpi.ua/schedule/lessons?groupId={group}"

KEEP = ("id", "name", "short_name", "semester", "component", "chat_url", "conferences")
DROP_HINT = ("department", "credits", "control", "in_catalog_2026", "note")


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFKC", name)
    for src, dst in (("’", "'"), ("‘", "'"), ("`", "'"), ("–", "-"), ("—", "-")):
        text = text.replace(src, dst)
    return " ".join(text.split()).casefold()


def fetch_api_names(group_id: int) -> set[str]:
    with urllib.request.urlopen(API.format(group=group_id), timeout=30) as response:
        payload = json.load(response)
    names: set[str] = set()
    for field in ("scheduleFirstWeek", "scheduleSecondWeek"):
        for day in payload.get(field) or []:
            for pair in day.get("pairs") or []:
                if pair.get("name"):
                    names.add(pair["name"].strip())
    return names


def clean(subject: dict[str, Any], *, elective: bool) -> dict[str, Any]:
    out = {key: subject.get(key) for key in KEEP if key in subject or key == "short_name"}
    out.setdefault("short_name", None)
    out.setdefault("chat_url", "")
    out.setdefault("conferences", {"lecture": None, "practice": None, "lab": None})
    if elective:
        out["default_selected"] = bool(subject.get("selected", subject.get("default_selected")))
    else:
        out.pop("component", None)
    if subject.get("api_alias"):
        out["api_alias"] = subject["api_alias"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--group-id", type=int, default=3695)
    parser.add_argument("--offline", action="store_true", help="skip the alias lookup")
    args = parser.parse_args()

    catalog = json.loads(args.source.read_text(encoding="utf-8"))
    result = {
        "normative": [clean(s, elective=False) for s in catalog.get("normative", [])],
        "electives": [clean(s, elective=True) for s in catalog.get("electives", [])],
    }
    everything = result["normative"] + result["electives"]

    dropped = {key for s in catalog.get("normative", []) + catalog.get("electives", [])
               for key in s if key in DROP_HINT}
    if dropped:
        print(f"dropped unused fields: {', '.join(sorted(dropped))}")
    if "meta" in catalog:
        print("dropped: meta")

    if not args.offline:
        try:
            api_names = fetch_api_names(args.group_id)
        except Exception as exc:  # network is optional, the conversion is not
            print(f"! could not reach the KPI API ({exc}); skipping alias lookup", file=sys.stderr)
            api_names = set()

        if api_names:
            by_key = {normalize(s["name"]): s for s in everything}
            matched = 0
            for api_name in sorted(api_names):
                key = normalize(api_name)
                if key in by_key:
                    matched += 1
                    continue
                near = difflib.get_close_matches(key, list(by_key), n=1, cutoff=0.80)
                if not near:
                    print(f"! no catalog entry resembles {api_name!r}", file=sys.stderr)
                    continue
                subject = by_key[near[0]]
                subject["api_alias"] = api_name
                ratio = difflib.SequenceMatcher(None, key, near[0]).ratio()
                print(f"alias set (similarity {ratio:.3f})\n    {subject['name']}\n  → {api_name}")
            print(f"{matched}/{len(api_names)} names matched without an alias")

    missing_short = [s["name"] for s in everything if not s.get("short_name")]
    if missing_short:
        print(f"\n{len(missing_short)} subjects have no short_name — messages will use the")
        print("full title, which is long. Worth filling in for at least the ones you take.")

    args.target.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {args.target} ({len(everything)} subjects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
