"""Operator-only, offline SQLite snapshots for the PayPal SANDBOX demo.

Never import this module from the FastAPI app or expose snapshots over HTTP.
The file contains private participant data, bearer invite hashes and Sandbox
idempotency/order/capture IDs. It is not an authenticated PayPal receipt.

Create: python tools/sqlite_snapshot.py create --source /path/db.sqlite3 --output /private/backup.sqlite3
Verify: python tools/sqlite_snapshot.py verify --snapshot /private/backup.sqlite3
Drill:  python tools/sqlite_snapshot.py drill  --snapshot /private/backup.sqlite3

There is deliberately NO operation that overwrites or imports into a live DB.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import uuid

KIND = "circlesplit-sandbox-sqlite-snapshot"
SCHEMA_VERSION = 1
MAX_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 8192
REQUIRED_TABLES = ("events", "expenses", "people", "payments",
                   "webhook_events", "storage_identity")
COUNT_KEYS = REQUIRED_TABLES + ("verified_captures", "unresolved_payments")


class SnapshotError(Exception):
    """Safe operator-facing failure; never includes raw record contents."""


def _path(value: str | Path) -> Path:
    return Path(value).expanduser().absolute()


def _regular_file(value: str | Path) -> Path:
    path = _path(value)
    if path.is_symlink() or not path.is_file():
        raise SnapshotError("SQLite snapshot/source must be a regular file, not a symlink.")
    if path.stat().st_size > MAX_BYTES or path.stat().st_size < 100:
        raise SnapshotError("SQLite file is empty or exceeds the operator snapshot size limit.")
    with path.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\x00":
            raise SnapshotError("File is not a SQLite database.")
    return path


def _private_destination(output: str | Path) -> Path:
    dest = _path(output)
    if dest.suffix != ".sqlite3":
        raise SnapshotError("Snapshot filename must end in .sqlite3 (excluded by .gitignore).")
    folder = dest.parent
    if not folder.is_dir() or folder.is_symlink():
        raise SnapshotError("Create a dedicated private backup directory before exporting.")
    directory_info = folder.stat()
    if os.name == "posix" and (directory_info.st_uid != os.getuid()
                               or stat.S_IMODE(directory_info.st_mode) & 0o077):
        raise SnapshotError("Backup directory must be owned by you and mode 0700.")
    manifest = Path(str(dest) + ".manifest.json")
    if dest.exists() or dest.is_symlink() or manifest.exists() or manifest.is_symlink():
        raise SnapshotError("Refusing to overwrite an existing snapshot or manifest.")
    return dest


def _open_readonly(path: Path) -> sqlite3.Connection:
    # mode=ro observes WAL-committed transactions without creating an empty DB.
    # Do not set immutable=1: that could omit committed WAL content.
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=20)


def _inventory(path: str | Path) -> dict:
    source = _regular_file(path)
    try:
        with closing(_open_readonly(source)) as connection:
            check = connection.execute("PRAGMA integrity_check").fetchone()
            if check != ("ok",):
                raise SnapshotError("SQLite integrity_check failed.")
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not set(REQUIRED_TABLES) <= tables:
                raise SnapshotError("Snapshot is missing CircleSplit financial ledger tables.")
            rows = connection.execute(
                "SELECT incarnation_id FROM storage_identity WHERE id=1"
            ).fetchall()
            if len(rows) != 1 or not isinstance(rows[0][0], str):
                raise SnapshotError("Snapshot is missing the database incarnation marker.")
            try:
                epoch = str(uuid.UUID(rows[0][0]))
            except (ValueError, AttributeError) as exc:
                raise SnapshotError("Invalid database incarnation marker.") from exc
            counts = {
                table: connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                for table in REQUIRED_TABLES
            }
            counts["verified_captures"] = connection.execute(
                """SELECT COUNT(*) FROM payments WHERE status='completed'
                   AND capture_id IS NOT NULL AND capture_id!=''"""
            ).fetchone()[0]
            counts["unresolved_payments"] = connection.execute(
                """SELECT COUNT(*) FROM payments WHERE status!='completed'
                   OR capture_id IS NULL OR capture_id=''"""
            ).fetchone()[0]
            return {"database_epoch": epoch, "counts": counts}
    except sqlite3.DatabaseError as exc:
        raise SnapshotError("SQLite inspection failed: damaged or unsupported database.") from exc


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path(snapshot: str | Path) -> Path:
    return Path(str(_path(snapshot)) + ".manifest.json")


def _read_manifest(snapshot: Path) -> dict:
    path = _manifest_path(snapshot)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise SnapshotError("Missing or oversized private snapshot manifest.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise SnapshotError("Invalid private snapshot manifest.") from exc
    if not isinstance(data, dict) or set(data) != {
        "kind", "schema_version", "generated_at", "database_epoch",
        "snapshot_sha256", "size_bytes", "counts"
    } or data["kind"] != KIND or type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise SnapshotError("Unsupported snapshot manifest format.")
    try:
        if str(uuid.UUID(data["database_epoch"])) != data["database_epoch"]:
            raise ValueError("Noncanonical database marker")
        stamp = datetime.fromisoformat(data["generated_at"])
        if stamp.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware")
    except (TypeError, ValueError, AttributeError) as exc:
        raise SnapshotError("Invalid snapshot provenance metadata.") from exc
    if (not isinstance(data["snapshot_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", data["snapshot_sha256"])
            or type(data["size_bytes"]) is not int or not 100 <= data["size_bytes"] <= MAX_BYTES):
        raise SnapshotError("Invalid snapshot checksum or size metadata.")
    if (not isinstance(data["counts"], dict) or set(data["counts"]) != set(COUNT_KEYS)
            or any(type(x) is not int or x < 0 for x in data["counts"].values())):
        raise SnapshotError("Invalid snapshot count metadata.")
    return data


def verify(snapshot: str | Path) -> dict:
    """Read-only: SHA-256, SQLite integrity, schema, epoch and inventory."""
    source = _regular_file(snapshot)
    manifest = _read_manifest(source)
    if source.stat().st_size != manifest["size_bytes"] or _hash(source) != manifest["snapshot_sha256"]:
        raise SnapshotError("Snapshot file differs from its recorded SHA-256/size.")
    actual = _inventory(source)
    if (actual["database_epoch"] != manifest["database_epoch"]
            or actual["counts"] != manifest["counts"]):
        raise SnapshotError("Snapshot inventory differs from the manifest.")
    return manifest


def _sync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def create(source: str | Path, output: str | Path) -> dict:
    """Consistent online SQLite backup; atomic no-overwrite private outputs."""
    src = _regular_file(source)
    dest = _private_destination(output)
    if src.resolve() == dest.resolve(strict=False):
        raise SnapshotError("Source and private snapshot destination cannot be identical.")
    tmp_db = None
    tmp_manifest = None
    db_published = False
    manifest_published = False
    succeeded = False
    try:
        fd, tmp_db_name = tempfile.mkstemp(prefix=".circlesplit-db-",suffix=".sqlite3",
                                          dir=str(dest.parent))
        os.close(fd)
        tmp_db = Path(tmp_db_name)
        tmp_db.chmod(0o600)
        # Live DB may be in WAL mode or receiving writes; copying its bytes
        # directly would be an inconsistent financial snapshot.
        with closing(_open_readonly(src)) as source_db:
            with closing(sqlite3.connect(str(tmp_db), timeout=20)) as target_db:
                source_db.backup(target_db, pages=256, sleep=0.05)
                target_db.commit()
        # SQLite backup can inherit WAL journal mode from its source.
        # A portable snapshot MUST be a standalone database file, not a
        # database that still needs temporary -wal/-shm siblings.
        with closing(sqlite3.connect(str(tmp_db),timeout=20)) as copied:
            copied.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            mode=copied.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            if mode.lower()!="delete":
                raise SnapshotError("SQLite snapshot could not enter standalone journal mode.")
            copied.commit()
        if any(Path(str(tmp_db)+suffix).exists() for suffix in ("-wal","-shm")):
            raise SnapshotError("SQLite snapshot still has uncheckpointed journal sidecars.")
        if tmp_db.stat().st_size > MAX_BYTES:
            raise SnapshotError("SQLite snapshot exceeds the operator size limit.")
        inspected = _inventory(tmp_db)
        manifest = {
            "kind": KIND, "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database_epoch": inspected["database_epoch"],
            "snapshot_sha256": _hash(tmp_db),
            "size_bytes": tmp_db.stat().st_size,
            "counts": inspected["counts"]
        }
        fd, temp_name = tempfile.mkstemp(prefix=".circlesplit-manifest-",
                                         suffix=".json",dir=str(dest.parent))
        tmp_manifest = Path(temp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(),0o600) if hasattr(os,"fchmod") else None
            json.dump(manifest, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        _sync_file(tmp_db)
        # Hard-link creation fails if either destination exists. In contrast,
        # os.replace() could silently destroy another financial backup.
        os.link(str(tmp_db), str(dest))
        db_published = True
        os.link(str(tmp_manifest), str(_manifest_path(dest)))
        manifest_published = True
        if verify(dest) != manifest:
            raise SnapshotError("Post-publication snapshot verification failed.")
        succeeded = True
        return manifest
    except (OSError, sqlite3.DatabaseError) as exc:
        raise SnapshotError("Offline snapshot failed; inspect permissions and available disk space.") from exc
    finally:
        # If sidecar creation or validation fails, never leave a seemingly
        # complete orphan DB or accidentally remove a prior user's file.
        if not succeeded:
            if manifest_published:
                _manifest_path(dest).unlink(missing_ok=True)
            if db_published:
                dest.unlink(missing_ok=True)
        for item in (tmp_db, tmp_manifest):
            if item is not None:
                item.unlink(missing_ok=True)
        # Remove ONLY sidecars created for our own random staging filename.
        # On any error, avoid leaving temporary private ledger bytes behind.
        if tmp_db is not None:
            for suffix in ("-wal","-shm","-journal"):
                Path(str(tmp_db)+suffix).unlink(missing_ok=True)


def drill(snapshot: str | Path) -> dict:
    """Isolated rehearsal of restoring data for inspection, never the live DB."""
    source = _regular_file(snapshot)
    original = verify(source)
    with tempfile.TemporaryDirectory(prefix="circlesplit-restore-drill-") as folder:
        candidate = Path(folder) / "isolated-rehearsal.sqlite3"
        shutil.copyfile(source, candidate)
        candidate.chmod(0o600)
        if _hash(candidate) != original["snapshot_sha256"]:
            raise SnapshotError("Isolated rehearsal file does not match the backup.")
        inventory = _inventory(candidate)
        if (inventory["database_epoch"] != original["database_epoch"]
                or inventory["counts"] != original["counts"]):
            raise SnapshotError("Isolated restore rehearsal did not preserve ledger counts.")
    return original


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    first = commands.add_parser("create", help="Consistent offline SQLite snapshot, no overwrite")
    first.add_argument("--source", required=True)
    first.add_argument("--output", required=True)
    for action in ("verify","drill"):
        cmd = commands.add_parser(action, help="Read-only snapshot validation")
        cmd.add_argument("--snapshot", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "create":
            manifest = create(args.source,args.output)
        elif args.action == "verify":
            manifest = verify(args.snapshot)
        else:
            manifest = drill(args.snapshot)
    except (SnapshotError, OSError) as exc:
        print("FAILED: " + str(exc), file=sys.stderr)
        return 2
    # No names, private tokens or provider order/capture identifiers in output.
    print(json.dumps({"status":"PASS","operation":args.action,
          "database_epoch_prefix":manifest["database_epoch"][:12],
          "snapshot_sha256":manifest["snapshot_sha256"],
          "counts":manifest["counts"]},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
