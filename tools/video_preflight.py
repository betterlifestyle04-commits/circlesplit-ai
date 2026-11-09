#!/usr/bin/env python3
"""Offline metadata check of a *locally recorded* CircleSplit demo video.

Use: python tools/video_preflight.py /private/path/recording.mp4
Requires the user's local FFmpeg ffprobe binary; never installs anything.
This checks the actual file's video track and duration (<180s), but does
NOT watch its content, inspect credentials, authenticate to YouTube or
prove the hackathon submission. No network requests are made.
"""
import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import stat
import subprocess
import sys

MAX_FILE_BYTES = 1024 * 1024 * 1024  # Do not analyze huge/untrusted media.
MAX_PROBE_BYTES = 128 * 1024
MAX_SECONDS = Decimal("180")
RECOMMENDED_MAX_SECONDS = Decimal("175")


def _result(blockers=(), warnings=(), *, duration=None, width=None,
            height=None, audio=None):
    return {
        "mode": "LOCAL_VIDEO_METADATA_ONLY",
        "status": "BLOCKED" if blockers else "NEEDS_MANUAL_REVIEW",
        "blockers": list(blockers),
        "warnings": list(warnings),
        "duration_seconds": duration,
        "video_width": width,
        "video_height": height,
        "audio_present": audio,
        "required_manual_checks": [
            "Watch the entire recording and confirm the app is genuinely functioning.",
            "Redact and review any private credentials, buyer details and invitation links.",
            "Verify the uploaded YouTube version plays signed out and is under 3 minutes.",
            "Confirm actual Gemini and PayPal Sandbox evidence is not simulated or mislabeled.",
            "Finish the required Devpost form and verify actual submission confirmation.",
        ],
        "notice": (
            "Local file metadata only. No remote requests, video frame inspection, "
            "YouTube playback, provider tests, or Devpost submission. "
            "No filename or raw ffprobe metadata is included in the report."
        ),
    }


def inspect_metadata(metadata):
    """Fail closed on untrusted ffprobe JSON; never copy raw metadata."""
    invalid = _result(("Video metadata is missing or malformed.",))
    if not isinstance(metadata, dict):
        return invalid
    fmt = metadata.get("format")
    streams = metadata.get("streams")
    if not isinstance(fmt, dict) or not isinstance(streams, list):
        return invalid
    try:
        # Validate textual decimal explicitly. Float JSON would have lost
        # precision at the 180-second contest boundary.
        raw = fmt.get("duration")
        if not isinstance(raw, str) or not re.fullmatch(
                r"[0-9]{1,7}(?:\.[0-9]{1,9})?", raw, flags=re.ASCII):
            return _result(("Video duration is unavailable or ambiguous.",))
        seconds = Decimal(raw)
        if not seconds.is_finite() or seconds <= 0:
            return _result(("Video duration must be finite and positive.",))
    except (InvalidOperation, ValueError, TypeError):
        return _result(("Video duration is unavailable or ambiguous.",))
    seconds_string = format(seconds, "f")
    video = [
        stream for stream in streams
        if isinstance(stream, dict)
        and stream.get("codec_type") == "video"
        and not (
            isinstance(stream.get("disposition"), dict)
            and stream["disposition"].get("attached_pic") == 1
        )
    ]
    dimensions = [
        (stream.get("width"), stream.get("height"))
        for stream in video
        if isinstance(stream.get("width"), int)
        and not isinstance(stream.get("width"), bool)
        and isinstance(stream.get("height"), int)
        and not isinstance(stream.get("height"), bool)
        and 0 < stream["width"] <= 16384
        and 0 < stream["height"] <= 16384
    ]
    if dimensions:
        width, height = max(dimensions, key=lambda dims: dims[0] * dims[1])
    else:
        width = height = None
    audio = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in streams
    )
    blockers, warnings = [], []
    if seconds >= MAX_SECONDS:
        blockers.append("Recording duration must be strictly under 180 seconds.")
    elif seconds > RECOMMENDED_MAX_SECONDS:
        warnings.append(
            "Very close to three minutes; leave a margin for the final YouTube export."
        )
    if not dimensions:
        blockers.append("No usable moving-video track and dimensions were found.")
    elif width < 1280 or height < 720:
        warnings.append(
            "Below the recommended 1280×720 resolution; verify text is legible."
        )
    if not audio:
        warnings.append(
            "No audio track detected; manually confirm the explanation is clear."
        )
    return _result(
        blockers, warnings, duration=seconds_string,
        width=width, height=height, audio=audio
    )


def inspect_video(path, run=subprocess.run):
    """Analyze a local non-symlink regular file via bounded, no-network ffprobe."""
    if not isinstance(path, (str, Path)) or not str(path):
        return _result(("A local video file is required.",))
    try:
        candidate = Path(path)
        info = candidate.lstat()
        if not stat.S_ISREG(info.st_mode) or candidate.is_symlink():
            return _result(("The video must be a regular local file, not a link.",))
        if info.st_size < 1 or info.st_size > MAX_FILE_BYTES:
            return _result(("The local video is empty or exceeds the 1 GiB check limit.",))
    except (OSError, ValueError, TypeError):
        return _result(("The local video could not be opened.",))
    argv = [
        "ffprobe", "-v", "error", "-protocol_whitelist", "file",
        "-show_entries",
        "format=duration:stream=codec_type,width,height:stream_disposition=attached_pic",
        "-of", "json", "-i", str(candidate),
    ]
    try:
        finished = run(
            argv, capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return _result(("ffprobe is unavailable, timed out, or could not inspect the file.",))
    if finished.returncode != 0:
        return _result(("ffprobe could not read the local video metadata.",))
    if not isinstance(finished.stdout, str) or len(finished.stdout) > MAX_PROBE_BYTES:
        return _result(("Video metadata exceeds the safe inspection limit.",))
    try:
        metadata = json.loads(finished.stdout)
    except (ValueError, UnicodeError):
        return _result(("Video metadata is not valid JSON.",))
    return inspect_metadata(metadata)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_file", help="Path to one existing local recording")
    parser.add_argument("--json", action="store_true", help="Machine-readable metadata-only report")
    args = parser.parse_args(argv)
    result = inspect_video(args.video_file)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("CircleSplit AI — local demo-video metadata preflight")
        print("STATUS:", result["status"])
        if result["duration_seconds"] is not None:
            print("Duration:", result["duration_seconds"], "seconds")
        if result["video_width"] is not None:
            print("Video:", str(result["video_width"]) + "x" + str(result["video_height"]))
        if result["audio_present"] is not None:
            print("Audio track:", "yes" if result["audio_present"] else "no")
        for item in result["blockers"]:
            print("BLOCKER:", item)
        for item in result["warnings"]:
            print("ADVISORY:", item)
        for item in result["required_manual_checks"]:
            print("MANUAL:", item)
        print(result["notice"])
    return 2 if result["blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
