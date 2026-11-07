#!/usr/bin/env python3
"""Offline Devpost submission readiness checks for CircleSplit AI.

Run locally with no credentials:
    python tools/submission_preflight.py
    python tools/submission_preflight.py --video-url https://youtu.be/VIDEO_ID

This tool cannot read Devpost submission state, watch videos, run the hosted
Gemini/PayPal Sandbox, or verify private judge credentials. It never reports
"submitted" or silently treats publishing a Devpost project as submitting to
the hackathon. No network requests and no payment operations are made.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit

PROJECT_URL = "https://devpost.com/software/circlesplit-ai"
PUBLIC_DEMO = "https://circlesplit-ai-demo.onrender.com/"
SOURCE_REPOSITORY = "https://github.com/betterlifestyle04-commits/circlesplit-ai"
DEADLINE_UTC = "2026-11-12T20:00:00Z"
ROOT = Path(__file__).resolve().parent.parent


def youtube_video_id(value):
    """Check the URL's syntax, not its visibility, length or ownership."""
    if not isinstance(value, str) or not value or value.strip() != value:
        return None
    if len(value) > 2048 or not value.isascii() or re.search(r"\s|[\x00-\x1f\x7f]", value):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.fragment or parsed.port not in (None, 443)):
            return None
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if host in ("youtu.be", "www.youtu.be"):
        if parsed.query or not re.fullmatch(r"/[A-Za-z0-9_-]{11}/?", parsed.path):
            return None
        return parsed.path.strip("/")
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if parsed.path != "/watch":
            return None
        query = parse_qs(parsed.query, keep_blank_values=True)
        if set(query) != {"v"} or len(query["v"]) != 1:
            return None
        vid = query["v"][0]
        return vid if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) else None
    return None


def inspect(root=ROOT, video_url=""):
    root = Path(root)
    tests = []

    def check(name, condition, detail, blocking=True):
        tests.append({
            "name": name,
            "status": "pass" if condition else ("blocker" if blocking else "manual_review"),
            "detail": detail,
        })

    def source(filename):
        path = root / filename
        if not path.is_file() or path.is_symlink():
            return ""
        try:
            if path.stat().st_size > 1024 * 1024:
                return ""
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""

    license_text = source("LICENSE")
    readme = source("README.md")
    guide = source("docs/JUDGE_HANDOFF.md")
    script = source("docs/VIDEO_DEMO_SCRIPT.md")
    public = source("static/public.html")
    judge = source("static/judge.html")

    check(
        "Public open-source license",
        license_text.startswith("MIT License\n")
        and "Permission is hereby granted" in license_text
        and "THE SOFTWARE IS PROVIDED" in license_text,
        "The repo must expose a visible approved open-source LICENSE."
    )
    check(
        "README and reproducible setup",
        readme.startswith("# CircleSplit AI")
        and "pip install -r requirements.txt" in readme
        and "uvicorn app:app" in readme
        and SOURCE_REPOSITORY in readme,
        "The public README must include source, installation and run instructions."
    )
    check(
        "AI and PayPal technology explanation",
        all(term in readme.lower() for term in ("gemini", "paypal", "sandbox", "ai")),
        "Explain the meaningfully implemented Gemini and PayPal Sandbox flows."
    )
    check(
        "Working entrypoint and public judge walkthrough",
        bool(source("app.py")) and bool(source("paypal.py"))
        and bool(source("static/judge_walkthrough.js"))
        and "Judge walkthrough" in judge
        and "CircleSplit AI" in public,
        "Include executable app code plus functional public guest/judge pages."
    )
    check(
        "Judge testing and safety handoff",
        PUBLIC_DEMO in guide and "/workspace" in guide
        and "sandbox" in guide.lower()
        and "Never" in guide,
        "Judge instructions must distinguish public simulation from private testing and forbid sharing credentials."
    )
    check(
        "Recorded-demo filming plan",
        "00:00" in script and ("YouTube" in script)
        and ("PayPal" in script) and ("Gemini" in script),
        "The video plan must cover both required technologies and remain under 3 minutes."
    )
    vid = youtube_video_id(video_url)
    check(
        "Public YouTube demo URL supplied",
        vid is not None,
        ("A syntactically valid YouTube video URL was provided; visibility and "
         "duration remain unverified." if vid else
         "Missing public YouTube video URL; mandatory under-three-minute demo is a submission blocker.")
    )

    # These cannot be proven by looking at source files. Never mark them pass
    # automatically, and never ask an operator to paste a password into CLI.
    checks = (
        ("Repository visibility", "Confirm the GitHub repository is public and LICENSE visible."),
        ("Hosted browser functionality", "Open public demo and judge guide in an incognito browser; test interactions."),
        ("Protected Gemini and PayPal test", "Manually demonstrate one real Gemini response and an existing PayPal Sandbox capture; use fictional data."),
        ("Video publishing", "Watch the YouTube video signed out, ensure playback, no secrets, and duration strictly below 3:00."),
        ("Submission form", "Complete all required Devpost questions and eligibility attestations truthfully."),
        ("Judging credentials", "Supply optional judge login details only in Devpost's private testing-instructions field."),
        ("Submission confirmation", "Verify a non-null submitted_at or explicit Submitted status on Devpost; project publication alone is insufficient."),
        ("Storage limitation", "Tell judges Render Free SQLite is ephemeral; do not call this production-ready."),
    )
    for name, detail in checks:
        check(name, False, detail, blocking=False)

    blockers = [item["name"] for item in tests if item["status"] == "blocker"]
    return {
        "project": "CircleSplit AI",
        "mode": "OFFLINE_SUBMISSION_PRECHECK_ONLY",
        "project_url": PROJECT_URL,
        "deadline_utc": DEADLINE_UTC,
        "status": "BLOCKED" if blockers else "NEEDS_MANUAL_REVIEW",
        "blockers": blockers,
        "checks": tests,
        "notice": (
            "No submission was made or verified. This check does not browse "
            "Devpost, YouTube, GitHub, Render, Gemini or PayPal. "
            "Never put real credentials into a public document."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="Local source checkout")
    parser.add_argument("--video-url", default="", help="Public YouTube URL only; not a password")
    parser.add_argument("--json", action="store_true", help="Machine-readable summary")
    args = parser.parse_args(argv)
    outcome = inspect(args.root, args.video_url)
    if args.json:
        print(json.dumps(outcome, indent=2, sort_keys=True))
    else:
        print("CircleSplit AI — offline Devpost preflight")
        print("Deadline (UTC):", DEADLINE_UTC)
        for item in outcome["checks"]:
            print(f"  [{item['status'].upper()}] {item['name']}: {item['detail']}")
        print(f"\nSTATUS: {outcome['status']}")
        if outcome["blockers"]:
            print("Blocking:", "; ".join(outcome["blockers"]))
        print(outcome["notice"])
    return 2 if outcome["blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
