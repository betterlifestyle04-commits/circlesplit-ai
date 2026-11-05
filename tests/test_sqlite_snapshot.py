"""Offline backup & recovery-drill contract. All databases are fictional.

Never contacts PayPal, restores a live DB, or accesses hosted app credentials.
"""
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import uuid
import pytest

from tools import sqlite_snapshot as snapshot


@pytest.fixture
def ledger(tmp_path):
    source = tmp_path / "sandbox.sqlite3"
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    conn = sqlite3.connect(source)
    assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    conn.executescript("""
        CREATE TABLE events(id INTEGER PRIMARY KEY,name TEXT);
        CREATE TABLE expenses(id INTEGER PRIMARY KEY,title TEXT);
        CREATE TABLE people(id INTEGER PRIMARY KEY,name TEXT);
        CREATE TABLE payments(id INTEGER PRIMARY KEY,status TEXT,
            capture_id TEXT,order_id TEXT,request_id TEXT);
        CREATE TABLE webhook_events(id TEXT PRIMARY KEY);
        CREATE TABLE storage_identity(id INTEGER PRIMARY KEY,incarnation_id TEXT);
    """)
    epoch = str(uuid.uuid4())
    conn.execute("INSERT INTO storage_identity VALUES(1,?)",(epoch,))
    conn.execute("INSERT INTO events VALUES(1,'Secret Event')")
    conn.execute("INSERT INTO expenses VALUES(1,'Private expense')")
    conn.execute("INSERT INTO people VALUES(1,'PRIVATE PERSON NAME')")
    conn.execute(
        "INSERT INTO payments VALUES(1,'completed','PRIVATE-CAPTURE-123',"
        "'PRIVATE-ORDER-123','PRIVATE-IDEMPOTENCY-KEY')"
    )
    conn.execute("INSERT INTO payments VALUES(2,'capturing',NULL,NULL,'UNRESOLVED-SECRET')")
    conn.execute("INSERT INTO webhook_events VALUES('PRIVATE-WEBHOOK')")
    conn.commit()
    output = directory / "offline-20261105.sqlite3"
    try:
        yield source,output,conn,epoch
    finally:
        conn.close()


def test_create_captures_committed_wal_and_protects_personal_contents(ledger):
    source,output,conn,epoch=ledger
    assert (Path(str(source)+"-wal")).exists(), "WAL must still be active"
    result=snapshot.create(source,output)
    assert result["database_epoch"]==epoch
    assert result["counts"]=={
        "events":1,"expenses":1,"people":1,"payments":2,
        "webhook_events":1,"storage_identity":1,
        "verified_captures":1,"unresolved_payments":1,
    }
    assert output.is_file()
    assert snapshot.verify(output)==result
    assert output.stat().st_size==result["size_bytes"]
    manifest_path=Path(str(output)+".manifest.json")
    saved=manifest_path.read_text()
    for private in ("PRIVATE PERSON NAME","Secret Event","PRIVATE-CAPTURE-123",
                    "PRIVATE-ORDER-123","PRIVATE-IDEMPOTENCY-KEY","PRIVATE-WEBHOOK"):
        assert private not in saved
    with sqlite3.connect(output) as restored:
        assert restored.execute("SELECT name FROM people").fetchone()[0]=="PRIVATE PERSON NAME"
        assert restored.execute("SELECT COUNT(*) FROM payments").fetchone()[0]==2
    if os.name=="posix":
        assert stat.S_IMODE(output.stat().st_mode)==0o600
        assert stat.S_IMODE(manifest_path.stat().st_mode)==0o600


def test_isolated_drill_does_not_modify_existing_source_or_output(ledger):
    source,output,conn,_=ledger
    snapshot.create(source,output)
    source_digest=snapshot._hash(source)
    output_digest=snapshot._hash(output)
    before=set(output.parent.iterdir())
    report=snapshot.drill(output)
    assert report["counts"]["verified_captures"]==1
    assert snapshot._hash(source)==source_digest
    assert snapshot._hash(output)==output_digest
    assert set(output.parent.iterdir())==before


def test_refuse_overwrite_preserves_existing_snapshot_and_sidecar(ledger):
    source,output,conn,_=ledger
    snapshot.create(source,output)
    original_db=output.read_bytes()
    original_meta=Path(str(output)+".manifest.json").read_bytes()
    with pytest.raises(snapshot.SnapshotError,match="Refusing to overwrite"):
        snapshot.create(source,output)
    assert output.read_bytes()==original_db
    assert Path(str(output)+".manifest.json").read_bytes()==original_meta


def test_snapshot_checksum_detects_tampered_file(ledger):
    source,output,conn,_=ledger
    snapshot.create(source,output)
    data=bytearray(output.read_bytes())
    data[200] ^= 1
    output.write_bytes(data)
    with pytest.raises(snapshot.SnapshotError,match="SHA-256"):
        snapshot.verify(output)
    with pytest.raises(snapshot.SnapshotError,match="SHA-256"):
        snapshot.drill(output)


def test_manifest_schema_changes_are_rejected(ledger):
    source,output,conn,_=ledger
    snapshot.create(source,output)
    manifest_path=Path(str(output)+".manifest.json")
    data=json.loads(manifest_path.read_text())
    data["person_name"]="PRIVATE SECRET"
    manifest_path.write_text(json.dumps(data))
    with pytest.raises(snapshot.SnapshotError,match="Unsupported"):
        snapshot.verify(output)


def test_manifest_inventory_mismatch_is_detected(ledger):
    source,output,conn,_=ledger
    snapshot.create(source,output)
    path=Path(str(output)+".manifest.json")
    data=json.loads(path.read_text())
    data["counts"]["payments"]=0
    path.write_text(json.dumps(data))
    with pytest.raises(snapshot.SnapshotError,match="inventory differs"):
        snapshot.verify(output)


def test_missing_manifest_refused_without_rebuilding_from_db(ledger):
    source,output,conn,_=ledger
    snapshot.create(source,output)
    Path(str(output)+".manifest.json").unlink()
    with pytest.raises(snapshot.SnapshotError,match="Missing"):
        snapshot.verify(output)


def test_symlink_source_and_backup_destination_are_refused(ledger,tmp_path):
    source,output,conn,_=ledger
    alias=tmp_path/"alias.sqlite3"
    alias.symlink_to(source)
    with pytest.raises(snapshot.SnapshotError,match="symlink"):
        snapshot.create(alias,output)
    fake=output
    fake.symlink_to(source)
    with pytest.raises(snapshot.SnapshotError,match="overwrite"):
        snapshot.create(source,fake)


@pytest.mark.skipif(os.name!="posix",reason="POSIX directory permissions")
def test_private_directory_required_even_when_file_permissions_are_private(ledger,tmp_path):
    source,output,conn,_=ledger
    public=tmp_path/"public"
    public.mkdir()
    public.chmod(0o755)
    with pytest.raises(snapshot.SnapshotError,match="mode 0700"):
        snapshot.create(source,public/"oops.sqlite3")
    assert not (public/"oops.sqlite3").exists()


def test_non_sqlite_file_or_uninitialized_schema_cannot_be_exported(ledger,tmp_path):
    source,output,conn,_=ledger
    bogus=tmp_path/"fake.sqlite3"
    bogus.write_bytes(b"not an sqlite file" * 20)
    with pytest.raises(snapshot.SnapshotError,match="not a SQLite"):
        snapshot.create(bogus,output)
    empty=tmp_path/"empty.sqlite3"
    with sqlite3.connect(empty) as c:
        c.execute("CREATE TABLE missing(id INTEGER PRIMARY KEY)")
    with pytest.raises(snapshot.SnapshotError,match="missing CircleSplit"):
        snapshot.create(empty,output)
    assert not output.exists()
    assert not Path(str(output)+".manifest.json").exists()


def test_failed_output_publishing_cleans_temporary_files(ledger,monkeypatch):
    source,output,conn,_=ledger
    original_link=snapshot.os.link
    count=[0]
    def refuse_manifest(temp,final):
        count[0]+=1
        if count[0]==2:
            raise PermissionError("simulated disk error")
        return original_link(temp,final)
    monkeypatch.setattr(snapshot.os,"link",refuse_manifest)
    with pytest.raises(snapshot.SnapshotError,match="snapshot failed"):
        snapshot.create(source,output)
    assert not output.exists()
    assert not Path(str(output)+".manifest.json").exists()
    assert list(output.parent.iterdir())==[]


def test_cli_create_verify_drill_and_no_unsafe_restore_command(ledger,capsys):
    source,output,conn,_=ledger
    assert snapshot.main(["create","--source",str(source),"--output",str(output)])==0
    printed=json.loads(capsys.readouterr().out)
    assert printed["status"]=="PASS"
    assert printed["counts"]["payments"]==2
    assert "PRIVATE-" not in json.dumps(printed)
    assert snapshot.main(["verify","--snapshot",str(output)])==0
    assert snapshot.main(["drill","--snapshot",str(output)])==0
    assert not hasattr(snapshot,"restore")
    with pytest.raises(SystemExit) as exc:
        snapshot.main(["restore","--snapshot",str(output)])
    assert exc.value.code==2


def test_tool_is_not_registered_as_web_route_and_manifest_is_gitignored():
    repo=Path(__file__).resolve().parents[1]
    source=(repo/"app.py").read_text()
    assert "sqlite_snapshot" not in source
    assert "tools/sqlite_snapshot.py" not in source
    ignored=(repo/".gitignore").read_text()
    assert "*.sqlite3.manifest.json" in ignored


def test_verified_copy_cannot_silently_change_underlying_manifest(ledger):
    source,output,conn,_=ledger
    snapshot.create(source,output)
    path=Path(str(output)+".manifest.json")
    obj=json.loads(path.read_text())
    obj["database_epoch"]=str(uuid.uuid4())
    path.write_text(json.dumps(obj))
    with pytest.raises(snapshot.SnapshotError,match="inventory differs"):
        snapshot.verify(output)
