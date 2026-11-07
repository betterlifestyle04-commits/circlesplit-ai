"""No-network contract for CircleSplit's required Devpost submission deliverables."""
from pathlib import Path

import pytest
from tools.submission_preflight import (
    ROOT, DEADLINE_UTC, inspect, main, youtube_video_id,
)

VALID = "https://youtu.be/AbC012_-xYz"


@pytest.mark.parametrize("url", [
    "https://youtu.be/AbC012_-xYz",
    "https://www.youtu.be/AbC012_-xYz",
    "https://www.youtube.com/watch?v=AbC012_-xYz",
    "https://youtube.com/watch?v=AbC012_-xYz",
    "https://m.youtube.com/watch?v=AbC012_-xYz",
])
def test_youtube_format_allowed_without_falsely_claiming_playback(url):
    assert youtube_video_id(url) == "AbC012_-xYz"


@pytest.mark.parametrize("url", [
    "", None, "https://youtu.be/",
    "http://youtu.be/AbC012_-xYz",
    "https://youtu.be/AbC012_-xYz#fragment",
    "https://youtu.be/AbC012_-xYz?utm_campaign=sponsored",
    "https://youtu.be/abc",
    "https://youtube.com/watch?v=AbC012_-xYz&v=OtherVideo!",
    "https://youtube.com/watch?v=AbC012_-xYz&feature=sharing",
    "https://youtube.com/watch?v=",
    "https://youtube.com.evil.example/watch?v=AbC012_-xYz",
    "https://user:pass@youtu.be/AbC012_-xYz",
    "https://youtu.be:8080/AbC012_-xYz",
    "https://youtube.com/watch?video=AbC012_-xYz",
    "file:///private/passwords",
    "https://youtu.be/AbC012_-xYz\nAuthorization: Bearer private",
    " https://youtu.be/AbC012_-xYz",
    ["not a URL"], 123
])
def test_invalid_video_urls_are_rejected(url):
    assert youtube_video_id(url) is None


def fixture_project(tmp_path):
    files = {
        "LICENSE": "MIT License\nPermission is hereby granted\nTHE SOFTWARE IS PROVIDED",
        "README.md": ("# CircleSplit AI\n"
            "https://github.com/betterlifestyle04-commits/circlesplit-ai\n"
            "pip install -r requirements.txt\nuvicorn app:app\n"
            "This project uses Google Gemini AI and PayPal Sandbox.\n"),
        "docs/JUDGE_HANDOFF.md": (
            "https://circlesplit-ai-demo.onrender.com/\n"
            "https://circlesplit-ai-demo.onrender.com/workspace\n"
            "PayPal sandbox only. Never reveal credentials.\n"),
        "docs/VIDEO_DEMO_SCRIPT.md": (
            "00:00 Demonstrate Gemini AI, PayPal Sandbox and human approvals.\n"
            "Publish to YouTube under 3 minutes.\n"),
        "static/public.html": "<title>CircleSplit AI</title>",
        "static/judge.html": "<h1>Judge walkthrough</h1>",
        "static/judge_walkthrough.js": "function guide() {}",
        "app.py": "# FastAPI app",
        "paypal.py": "# Sandbox-only adapter",
    }
    for path, text in files.items():
        target = tmp_path / path
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_text(text)
    return tmp_path


def test_real_repo_preflight_identifies_video_as_only_automated_blocker():
    result = inspect(ROOT)
    assert result["mode"] == "OFFLINE_SUBMISSION_PRECHECK_ONLY"
    assert result["deadline_utc"] == "2026-11-12T20:00:00Z"
    assert result["status"] == "BLOCKED"
    assert result["blockers"] == ["Public YouTube demo URL supplied"]
    assert all(item["status"] != "blocker" for item in result["checks"][:-9])
    assert "No submission was made" in result["notice"]
    assert "project publication alone is insufficient" in str(result).lower()


def test_even_valid_video_syntax_still_requires_manual_confirmations(tmp_path):
    project = fixture_project(tmp_path)
    report = inspect(project, VALID)
    assert report["status"] == "NEEDS_MANUAL_REVIEW"
    assert report["blockers"] == []
    assert sum(x["status"] == "manual_review" for x in report["checks"]) == 8
    assert not any(x["name"] == "Submission confirmation" and
                   x["status"] == "pass" for x in report["checks"])
    assert "unverified" in next(x for x in report["checks"]
        if x["name"] == "Public YouTube demo URL supplied")["detail"]


def test_missing_license_and_setup_block_even_with_supplied_video(tmp_path):
    project = fixture_project(tmp_path)
    (project / "LICENSE").unlink()
    (project / "README.md").write_text("README\n")
    outcome = inspect(project, VALID)
    assert outcome["status"] == "BLOCKED"
    assert "Public open-source license" in outcome["blockers"]
    assert "README and reproducible setup" in outcome["blockers"]
    assert "AI and PayPal technology explanation" in outcome["blockers"]


def test_preflight_never_includes_real_secrets_or_submission_confirmation(tmp_path):
    project = fixture_project(tmp_path)
    text = (project / "README.md").read_text()
    (project / "README.md").write_text(text + "\nDEMO_PASSWORD=SECRET_PRIVATE_PASSWORD\n")
    report = inspect(project)
    assert "SECRET_PRIVATE_PASSWORD" not in str(report)
    assert not any("submitted" in x["name"].lower() and x["status"] == "pass"
                   for x in report["checks"])
    assert report["status"] == "BLOCKED"


def test_local_cli_requires_video_and_never_bypasses_manual_review(
    tmp_path, capsys
):
    project = fixture_project(tmp_path)
    assert main(["--root", str(project), "--json"]) == 2
    assert '"status": "BLOCKED"' in capsys.readouterr().out
    assert main(["--root", str(project), "--video-url", VALID]) == 0
    out = capsys.readouterr().out
    assert "STATUS: NEEDS_MANUAL_REVIEW" in out
    assert "No submission was made or verified" in out


def test_missing_or_symlinked_repository_file_does_not_pass(tmp_path):
    project = fixture_project(tmp_path)
    (project / "static/judge.html").unlink()
    (project / "static/judge.html").symlink_to(project / "static/public.html")
    result = inspect(project, VALID)
    assert "Working entrypoint and public judge walkthrough" in result["blockers"]
