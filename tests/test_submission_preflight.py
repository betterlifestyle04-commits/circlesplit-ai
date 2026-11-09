"""No-network contract for CircleSplit's required Devpost submission deliverables."""
from pathlib import Path

import pytest
from tools.submission_preflight import (
    ROOT, DEADLINE_UTC, inspect, main, youtube_video_id, public_credential_indicators,
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
    assert "Public materials do not contain detectable credentials" in report["blockers"]
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



@pytest.mark.parametrize(("content", "risk"), [
    ("DEMO_PASSWORD=HIDDEN_SUPER_SECRET_123456", "credential_assignment"),
    ("GEMINI_API_KEY: 'private-value-xyz'", "credential_assignment"),
    ("PAYPAL_CLIENT_SECRET=\"SANDBOX_ONLY_SECRET\"", "credential_assignment"),
    ("JUDGE_PASSWORD=NEVER_PUT_PASSWORD_IN_DOCS", "credential_assignment"),
    ("CIRCLESPLIT_BACKUP_KEY=SECRET_PRIVATE_KEY", "credential_assignment"),
    ("-----BEGIN RSA PRIVATE KEY-----\nXXXX\n-----END RSA PRIVATE KEY-----", "private_key"),
    ("-----BEGIN OPENSSH PRIVATE KEY-----", "private_key"),
    ("Authorization: Bearer FAKE_LONG_TEST_TOKEN_FOR_REVIEW_ONLY_1234", "bearer_value"),
    ("AIza" + "a" * 35, "google_api_key"),
    ("ghp_" + "z" * 30, "github_access_token"),
    ("github_pat_" + "Y" * 40, "github_access_token"),
    ("sk-proj-" + "T" * 35, "openai_api_key"),
    ("https://demo.example/participant?token=" + "R" * 35, "private_invite_link"),
])
def test_private_credential_patterns_are_detected_without_returning_values(content, risk):
    found = public_credential_indicators(content)
    assert risk in found
    assert content not in str(found)
    assert found == public_credential_indicators(content)


@pytest.mark.parametrize("public_file", [
    "README.md", "docs/JUDGE_HANDOFF.md", "docs/DEVPOST_FINAL_SUBMISSION.md",
    "docs/VIDEO_DEMO_SCRIPT.md", "static/judge.html", "static/public.html",
])
def test_public_materials_secret_scan_blocks_and_redacts_all_report_formats(
    tmp_path, capsys, public_file
):
    project = fixture_project(tmp_path)
    target = project / public_file
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text() if target.exists() else ""
    fake_secret = "JUDGE_PASSWORD=DO_NOT_COPY_MY_PASSWORD_76802"
    target.write_text(existing + "\n" + fake_secret)
    report = inspect(project, VALID)
    assert report["status"] == "BLOCKED"
    assert "Public materials do not contain detectable credentials" in report["blockers"]
    assert fake_secret not in str(report)
    assert "DO_NOT_COPY_MY_PASSWORD_76802" not in str(report)

    assert main(["--root", str(project), "--video-url", VALID]) == 2
    output = capsys.readouterr().out
    assert "Public materials do not contain detectable credentials" in output
    assert fake_secret not in output

    assert main(["--root", str(project), "--video-url", VALID, "--json"]) == 2
    output = capsys.readouterr().out
    assert '"status": "BLOCKED"' in output
    assert fake_secret not in output


def test_documentation_discussion_and_public_paypal_ids_are_not_secrets(tmp_path):
    project = fixture_project(tmp_path)
    target = project / "README.md"
    target.write_text(target.read_text() + "\n" +
        "PAYPAL_CLIENT_ID=NON_SECRET_PUBLIC_ID\n" +
        "PAYPAL_WEBHOOK_ID=NON_SECRET_WEBHOOK_ID\n" +
        "JUDGE_PASSWORD (18+ characters) must be provided privately.\n" +
        "No bearer tokens or private-key blocks should be included.\n")
    report = inspect(project, VALID)
    assert report["status"] == "NEEDS_MANUAL_REVIEW"
    assert "Public materials do not contain detectable credentials" not in report["blockers"]
    assert public_credential_indicators("Do not show a private key or bearer link.") == ()


def test_cannot_make_a_public_secret_scan_pass_by_linking_external_file(tmp_path):
    project = fixture_project(tmp_path)
    target = project / "docs/JUDGE_HANDOFF.md"
    target.unlink()
    target.symlink_to(project / "README.md")
    # Existing content checks still fail, and no external secret is read.
    report = inspect(project, VALID)
    assert "Judge testing and safety handoff" in report["blockers"]



def test_local_video_metadata_is_optional_and_never_claims_submitted(tmp_path, monkeypatch):
    from tools import submission_preflight as preflight
    project = fixture_project(tmp_path)
    valid_path = str(tmp_path / "SENSITIVE_OWNER_FILE_NAME.mp4")
    called = []
    def fake_video(path):
        called.append(path)
        return {
            "mode": "LOCAL_VIDEO_METADATA_ONLY",
            "status": "NEEDS_MANUAL_REVIEW",
            "blockers": [],
            "warnings": [],
            "duration_seconds": "164.25",
            "video_width": 1920,
            "video_height": 1080,
            "audio_present": True,
            "required_manual_checks": ["Verify YouTube is public."],
            "notice": "Local file metadata only.",
        }
    monkeypatch.setattr(preflight, "inspect_video", fake_video)
    output = preflight.inspect(project, VALID)
    assert output["local_video_metadata"] is None
    assert not called
    checked = preflight.inspect(project, VALID, valid_path)
    assert called == [valid_path]
    assert checked["status"] == "NEEDS_MANUAL_REVIEW"
    assert checked["blockers"] == []
    assert checked["local_video_metadata"]["duration_seconds"] == "164.25"
    assert "Local demo recording metadata under 3 minutes" in [
        c["name"] for c in checked["checks"] if c["status"] == "pass"
    ]
    assert valid_path not in str(checked)
    assert "No submission was made" in checked["notice"]
    assert not any(c["name"] == "Submission confirmation" and
                   c["status"] == "pass" for c in checked["checks"])


def test_invalid_local_video_fails_combined_preflight_even_with_youtube_url(tmp_path, monkeypatch):
    from tools import submission_preflight as preflight
    project = fixture_project(tmp_path)
    monkeypatch.setattr(preflight, "inspect_video", lambda _: {
        "mode": "LOCAL_VIDEO_METADATA_ONLY", "status": "BLOCKED",
        "blockers": ["Recording duration must be strictly under 180 seconds."],
        "warnings": [], "duration_seconds": "180.000",
        "video_width": 1920, "video_height": 1080, "audio_present": True,
        "required_manual_checks": [], "notice": "Metadata only."
    })
    report = preflight.inspect(project, VALID, "/private/demo.mp4")
    assert report["status"] == "BLOCKED"
    assert "Local demo recording metadata under 3 minutes" in report["blockers"]
    assert "Public YouTube demo URL supplied" not in report["blockers"]


def test_combined_cli_video_metadata_never_prints_private_recording_name(
        tmp_path, monkeypatch, capsys):
    from tools import submission_preflight as preflight
    project = fixture_project(tmp_path)
    private_path = "/private/NEVER_ECHO_BUYER_EMAIL.mp4"
    monkeypatch.setattr(preflight, "inspect_video", lambda _: {
        "mode": "LOCAL_VIDEO_METADATA_ONLY", "status": "BLOCKED",
        "blockers": ["No usable moving-video track and dimensions were found."],
        "warnings": [], "duration_seconds": "185",
        "video_width": None, "video_height": None, "audio_present": None,
        "required_manual_checks": [], "notice": "Metadata only."
    })
    assert preflight.main(["--root", str(project), "--video-url", VALID,
                           "--video-file", private_path]) == 2
    output = capsys.readouterr().out
    assert private_path not in output
    assert "NEVER_ECHO_BUYER_EMAIL" not in output
    assert "Local demo recording metadata" in output
    assert preflight.main(["--root", str(project), "--video-url", VALID,
                           "--video-file", private_path, "--json"]) == 2
    output = capsys.readouterr().out
    assert '"status": "BLOCKED"' in output
    assert private_path not in output
