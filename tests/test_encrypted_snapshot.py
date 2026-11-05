"""AES-256-GCM encrypted backup regression tests; all data is fictional."""
import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid

import pytest
from tools import encrypted_snapshot as encrypted


@pytest.fixture
def sandbox(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    source = tmp_path / "source.sqlite3"
    conn = sqlite3.connect(source)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE events(id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE expenses(id INTEGER PRIMARY KEY,title TEXT);
        CREATE TABLE people(id INTEGER PRIMARY KEY,event_id INTEGER,
                            name TEXT,share_cents INTEGER,status TEXT);
        CREATE TABLE payments(id INTEGER PRIMARY KEY,event_id INTEGER,
                              person_id INTEGER,status TEXT,amount_cents INTEGER,
                              capture_id TEXT,order_id TEXT,request_id TEXT);
        CREATE TABLE webhook_events(id TEXT PRIMARY KEY);
        CREATE TABLE storage_identity(id INTEGER PRIMARY KEY,incarnation_id TEXT);
    """)
    epoch=str(uuid.uuid4())
    conn.execute("INSERT INTO storage_identity VALUES(1,?)",(epoch,))
    conn.execute("INSERT INTO events VALUES(1,'VERY PRIVATE EVENT')")
    conn.execute("INSERT INTO expenses VALUES(1,'SECRET COURT')")
    conn.execute("INSERT INTO people VALUES(1,1,'PRIVATE NAME A',1500,'sandbox_paid')")
    conn.execute("INSERT INTO people VALUES(2,1,'PRIVATE NAME B',500,'unpaid')")
    conn.execute(
        "INSERT INTO payments VALUES(1,1,1,'completed',1500,'CAPTURE-SECRET-999',"
        "'ORDER-SECRET-999','IDEMPOTENCY-SECRET-999')"
    )
    conn.execute(
        "INSERT INTO payments VALUES(2,1,2,'created',500,NULL,"
        "'ORDER-PENDING-321','IDEMPOTENCY-PENDING-123')"
    )
    conn.execute("INSERT INTO webhook_events VALUES('WEBHOOK-SECRET-42')")
    conn.commit()
    archive=private / "demo.csb"
    key=private / "operator.passphrase"
    encrypted.keygen(key)
    try:
        yield source,archive,key,conn,epoch
    finally:
        conn.close()


def test_secure_archive_roundtrip_includes_wal_data_without_leaking_plaintext(sandbox):
    source,archive,key,conn,epoch=sandbox
    assert Path(str(source)+"-wal").exists()
    original=source.read_bytes()
    out=encrypted.seal(source,archive,key)
    assert out["database_epoch"]==epoch
    assert out["counts"]["payments"]==2
    assert out["counts"]["verified_captures"]==1
    assert archive.is_file()
    assert source.read_bytes()==original
    data=archive.read_bytes()
    assert data[:8]==encrypted.MAGIC
    for private_text in (
        b"PRIVATE NAME A", b"VERY PRIVATE EVENT", b"CAPTURE-SECRET-999",
        b"ORDER-SECRET-999", b"IDEMPOTENCY-SECRET-999", b"WEBHOOK-SECRET-42",
        b"SQLite format 3\x00",
    ):
        assert private_text not in data
    assert encrypted.verify(archive,key)==out
    drill=encrypted.drill(archive,key)
    assert drill["database_epoch"]==epoch
    assert drill["ledger_review"]["status"]=="locally_consistent"
    assert drill["ledger_review"]["unresolved_orders"]==1
    assert drill["ledger_review"]["issue_count"]==0
    assert sorted(p.name for p in archive.parent.iterdir())==[
        "demo.csb","operator.passphrase"]
    if os.name=="posix":
        assert stat.S_IMODE(archive.stat().st_mode)==0o600


def test_passphrase_is_random_private_not_logged_and_never_overwritten(sandbox,capsys):
    source,archive,key,conn,epoch=sandbox
    content=key.read_bytes()
    assert len(content.rstrip(b"\n"))>=48
    if os.name=="posix":
        assert stat.S_IMODE(key.stat().st_mode)==0o600
    with pytest.raises(encrypted.ArchiveError,match="overwrite"):
        encrypted.keygen(key)
    assert key.read_bytes()==content
    assert encrypted.main(["seal","--source",str(source),
                           "--output",str(archive),"--key-file",str(key)])==0
    printed=json.loads(capsys.readouterr().out)
    assert printed["status"]=="PASS"
    assert printed["counts"]["payments"]==2
    for secret in ("PRIVATE NAME A","IDEMPOTENCY-SECRET",
                   "CAPTURE-SECRET","ORDER-SECRET"):
        assert secret not in json.dumps(printed)
    assert key.read_bytes()==content
    assert encrypted.main(["verify","--bundle",str(archive),
                           "--key-file",str(key)])==0
    assert encrypted.main(["drill","--bundle",str(archive),
                           "--key-file",str(key)])==0


def test_wrong_key_fails_authentication_and_does_not_modify_encrypted_archive(sandbox):
    source,archive,key,conn,epoch=sandbox
    encrypted.seal(source,archive,key)
    previous=archive.read_bytes()
    wrong=archive.parent/"wrong.passphrase"
    encrypted.keygen(wrong)
    with pytest.raises(encrypted.ArchiveError,match="authentication failed"):
        encrypted.verify(archive,wrong)
    with pytest.raises(encrypted.ArchiveError,match="authentication failed"):
        encrypted.drill(archive,wrong)
    assert archive.read_bytes()==previous
    assert sorted(p.name for p in archive.parent.iterdir())==[
        "demo.csb","operator.passphrase","wrong.passphrase"]


@pytest.mark.parametrize("offset",[
    0, 9, 32, 49, 67,
])
def test_modified_header_or_ciphertext_is_rejected(sandbox,offset):
    source,archive,key,conn,epoch=sandbox
    encrypted.seal(source,archive,key)
    raw=bytearray(archive.read_bytes())
    raw[offset]^=0x5A
    archive.write_bytes(raw)
    with pytest.raises(encrypted.ArchiveError):
        encrypted.verify(archive,key)
    assert sorted(p.name for p in archive.parent.iterdir())==[
        "demo.csb","operator.passphrase"]


def test_truncated_and_appended_ciphertext_are_rejected(sandbox):
    source,archive,key,conn,epoch=sandbox
    encrypted.seal(source,archive,key)
    raw=archive.read_bytes()
    archive.write_bytes(raw[:-2])
    with pytest.raises(encrypted.ArchiveError,match="length"):
        encrypted.verify(archive,key)
    archive.write_bytes(raw+b"extra")
    with pytest.raises(encrypted.ArchiveError,match="length"):
        encrypted.verify(archive,key)


def test_existing_archive_must_not_be_overwritten(sandbox):
    source,archive,key,conn,epoch=sandbox
    encrypted.seal(source,archive,key)
    original=archive.read_bytes()
    with pytest.raises(encrypted.ArchiveError,match="overwrite"):
        encrypted.seal(source,archive,key)
    assert archive.read_bytes()==original


@pytest.mark.skipif(os.name!="posix",reason="POSIX permission checks")
def test_public_destination_or_world_readable_key_is_refused(sandbox,tmp_path):
    source,archive,key,conn,epoch=sandbox
    public=tmp_path/"public"
    public.mkdir(mode=0o755)
    with pytest.raises(encrypted.ArchiveError,match="0700"):
        encrypted.seal(source,public/"unsafe.csb",key)
    key.chmod(0o644)
    with pytest.raises(encrypted.ArchiveError,match="0600"):
        encrypted.seal(source,archive,key)
    assert not archive.exists()


def test_symlinked_key_or_archive_is_refused(sandbox):
    source,archive,key,conn,epoch=sandbox
    alias=archive.parent/"alias.passphrase"
    alias.symlink_to(key)
    with pytest.raises(encrypted.ArchiveError,match="symlink"):
        encrypted.seal(source,archive,alias)
    encrypted.seal(source,archive,key)
    link=archive.parent/"copy.csb"
    link.symlink_to(archive)
    with pytest.raises(encrypted.ArchiveError,match="regular"):
        encrypted.verify(link,key)


def test_internally_inconsistent_but_intact_archive_exits_review_required(sandbox,capsys):
    source,archive,key,conn,epoch=sandbox
    conn.execute("UPDATE people SET status='unpaid' WHERE id=1")
    conn.commit()
    encrypted.seal(source,archive,key)
    assert encrypted.verify(archive,key)["counts"]["payments"]==2
    report=encrypted.drill(archive,key)
    assert report["ledger_review"]["status"]=="needs_review"
    assert report["ledger_review"]["issue_counts"]["completed_person_not_paid"]>=1
    assert encrypted.main(["drill","--bundle",str(archive),
                           "--key-file",str(key)])==3
    displayed=json.loads(capsys.readouterr().out)
    assert displayed["status"]=="NEEDS_REVIEW"
    assert displayed["local_ledger_review"]["issue_counts"]["completed_person_not_paid"]>=1
    assert "PRIVATE NAME A" not in json.dumps(displayed)


def test_failed_creation_never_publishes_archive_or_leaves_raw_plaintext(sandbox,monkeypatch):
    source,archive,key,conn,epoch=sandbox
    real_link=encrypted.os.link
    def fail_link(src,dst):
        # The snapshot tool must still be able to publish its *staged*
        # SQLite file and manifest. Inject only at final .csb publication.
        if str(dst).endswith(".csb"):
            raise PermissionError("pretend filesystem denied encrypted publication")
        return real_link(src,dst)
    monkeypatch.setattr(encrypted.os,"link",fail_link)
    with pytest.raises(encrypted.ArchiveError,match="publish"):
        encrypted.seal(source,archive,key)
    assert not archive.exists()
    assert sorted(p.name for p in archive.parent.iterdir())==["operator.passphrase"]
    monkeypatch.setattr(encrypted.os,"link",real_link)


def test_cli_does_not_offer_restore_or_print_private_key(sandbox,capsys):
    source,archive,key,conn,epoch=sandbox
    assert encrypted.main(["verify","--bundle",str(archive),
                           "--key-file",str(key)])==2
    captured=capsys.readouterr()
    assert "private" not in captured.err.lower() or "archive" in captured.err.lower()
    assert key.read_text().strip() not in captured.err
    with pytest.raises(SystemExit) as exc:
        encrypted.main(["restore","--bundle",str(archive),
                        "--key-file",str(key)])
    assert exc.value.code==2


def test_operator_tool_not_exposed_as_web_route_and_secrets_ignored():
    root=Path(__file__).resolve().parents[1]
    app=(root/"app.py").read_text()
    assert "encrypted_snapshot" not in app
    ignored=(root/".gitignore").read_text()
    assert "*.csb" in ignored and "*.passphrase" in ignored
    assert "cryptography" not in (root/"requirements.txt").read_text()
    assert "cryptography" in (root/"requirements-ops.txt").read_text()
