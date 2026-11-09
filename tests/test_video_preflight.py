"""Offline demo-video metadata guard; no actual recording or network required."""
import json
from pathlib import Path
import subprocess

import pytest
from tools import video_preflight as video


def metadata(duration="164.250000", *, width=1920, height=1080, audio=True):
    streams = [{
        "codec_type": "video", "width": width, "height": height,
        "disposition": {"attached_pic": 0},
    }]
    if audio:
        streams.append({"codec_type": "audio"})
    return {"format": {"duration": duration}, "streams": streams}


def test_valid_local_demo_metadata_has_manual_only_status_and_exact_duration():
    result = video.inspect_metadata(metadata())
    assert result["mode"] == "LOCAL_VIDEO_METADATA_ONLY"
    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert not result["blockers"] and not result["warnings"]
    assert result["duration_seconds"] == "164.250000"
    assert result["video_width"] == 1920 and result["video_height"] == 1080
    assert result["audio_present"] is True
    assert len(result["required_manual_checks"]) >= 4
    assert "YouTube" in str(result["required_manual_checks"])
    assert "submission" in result["notice"].lower()


@pytest.mark.parametrize(("duration", "blocked"), [
    ("179.999999999", False),
    ("175", False),
    ("175.000001", False),
    ("179.999", False),
    ("180", True),
    ("180.000", True),
    ("180.000000001", True),
    ("181", True),
    ("9999999.123456789", True),
])
def test_three_minute_hackathon_boundary_uses_exact_decimal(duration, blocked):
    result = video.inspect_metadata(metadata(duration))
    assert ("Recording duration must be strictly under 180 seconds."
            in result["blockers"]) is blocked
    assert (result["status"] == "BLOCKED") is blocked
    assert result["duration_seconds"] == duration
    if duration == "175.000001":
        assert any("margin" in w for w in result["warnings"])


@pytest.mark.parametrize("duration", [
    None, "", "-1", "0", "NaN", "Infinity", "1e1000000",
    "179,9", "180seconds", " 179.1", 123.4, True,
])
def test_bad_or_ambiguous_container_duration_blocks(duration):
    result = video.inspect_metadata(metadata(duration))
    assert result["status"] == "BLOCKED"
    assert result["duration_seconds"] is None


@pytest.mark.parametrize("payload", [
    None, [], "{}", {}, {"format": None, "streams": []},
    {"format": {"duration": "120"}, "streams": None},
])
def test_corrupt_ffprobe_shapes_fail_closed(payload):
    assert video.inspect_metadata(payload)["status"] == "BLOCKED"


def test_video_track_must_be_present_and_not_just_audio_cover_art():
    no_video = {"format": {"duration": "100"}, "streams": [{"codec_type": "audio"}]}
    cover_only = {"format": {"duration": "100"}, "streams": [
        {"codec_type": "audio"},
        {"codec_type": "video", "width": 1000, "height": 1000,
         "disposition": {"attached_pic": 1}},
    ]}
    for sample in (no_video, cover_only):
        result = video.inspect_metadata(sample)
        assert result["status"] == "BLOCKED"
        assert result["video_width"] is None
        assert any("video track" in issue for issue in result["blockers"])


@pytest.mark.parametrize(("width", "height"), [
    (None, 720), (1280, None), (True, 720), (-1, 720),
    (0, 720), (1280, 0), (16385, 720), ("1920", 1080),
])
def test_invalid_video_dimensions_do_not_count_as_video(width, height):
    result = video.inspect_metadata(metadata(width=width, height=height))
    assert result["status"] == "BLOCKED"
    assert result["video_width"] is None


def test_low_resolution_and_missing_narration_audio_are_advisory_not_false_legal_requirements():
    result = video.inspect_metadata(metadata(width=1024, height=576, audio=False))
    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert not result["blockers"]
    assert result["audio_present"] is False
    assert any("resolution" in issue for issue in result["warnings"])
    assert any("audio track" in issue for issue in result["warnings"])


def test_actual_file_probe_command_is_bounded_no_network_no_shell_and_redacted(tmp_path):
    local = tmp_path / "file_with_private_buyer_email_do_not_print.mp4"
    local.write_bytes(b"sample")
    recorded = []
    def runner(args, **options):
        recorded.append((args, options))
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=json.dumps(metadata()),
            stderr="private-password-would-not-be-shown"
        )
    report = video.inspect_video(local, run=runner)
    assert report["status"] == "NEEDS_MANUAL_REVIEW"
    assert len(recorded) == 1
    command, opts = recorded[0]
    assert command[0] == "ffprobe"
    assert command[command.index("-protocol_whitelist") + 1] == "file"
    assert command[-2:] == ["-i", str(local)]
    assert opts["timeout"] == 15
    assert opts["capture_output"] is True
    assert opts["check"] is False
    assert "shell" not in opts
    assert "private_buyer_email" not in str(report)
    assert "private-password" not in str(report)


@pytest.mark.parametrize("returncode,out", [
    (2, "{}"), (0, "bad json"), (0, "a" * (video.MAX_PROBE_BYTES + 1)),
])
def test_ffprobe_failures_never_return_private_metadata_or_pass(tmp_path, returncode, out):
    local = tmp_path / "do-not-echo-this-video-file.mp4"
    local.write_bytes(b"video")
    def runner(args, **opts):
        return subprocess.CompletedProcess(args, returncode, out, "private-data")
    result = video.inspect_video(local, run=runner)
    assert result["status"] == "BLOCKED"
    assert "do-not-echo" not in str(result)
    assert "private-data" not in str(result)


def test_missing_ffprobe_and_timeout_block_safely(tmp_path):
    local = tmp_path / "recording.mp4"
    local.write_bytes(b"video")
    def not_installed(*a, **kw):
        raise FileNotFoundError("ffprobe")
    assert video.inspect_video(local, run=not_installed)["status"] == "BLOCKED"
    def too_slow(*a, **kw):
        raise subprocess.TimeoutExpired("ffprobe", 15)
    assert video.inspect_video(local, run=too_slow)["status"] == "BLOCKED"


def test_symlink_empty_missing_and_large_video_block_before_external_program(tmp_path):
    external = tmp_path / "target.mp4"
    external.write_bytes(b"film")
    linked = tmp_path / "linked.mp4"
    linked.symlink_to(external)
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    huge = tmp_path / "huge.mp4"
    with huge.open("wb") as handle:
        handle.truncate(video.MAX_FILE_BYTES + 1)
    def should_not_run(*a, **kw):
        raise AssertionError("Rejected local input must not run ffprobe")
    for bad_path in [linked, empty, huge, tmp_path / "missing.mp4", tmp_path]:
        assert video.inspect_video(bad_path, run=should_not_run)["status"] == "BLOCKED"


def test_plain_and_json_cli_never_disclose_private_input_path(monkeypatch, capsys):
    seen = []
    def fake_inspect(p):
        seen.append(p)
        return video.inspect_metadata(metadata(duration="179.999"))
    monkeypatch.setattr(video, "inspect_video", fake_inspect)
    filename = "/private/customer_secret_buyer_email.mp4"
    assert video.main([filename]) == 0
    plain = capsys.readouterr().out
    assert "179.999" in plain
    assert filename not in plain and "customer_secret" not in plain
    assert "MANUAL" in plain
    assert video.main([filename, "--json"]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "NEEDS_MANUAL_REVIEW"
    assert filename not in output
    assert seen == [filename, filename]


def test_hackathon_duration_blocks_and_returns_cli_exit_two(monkeypatch, capsys):
    monkeypatch.setattr(video, "inspect_video",
                        lambda _path: video.inspect_metadata(metadata("180.000")))
    assert video.main(["video.mp4", "--json"]) == 2
    output = capsys.readouterr().out
    assert '"status": "BLOCKED"' in output
    assert "strictly under 180" in output
