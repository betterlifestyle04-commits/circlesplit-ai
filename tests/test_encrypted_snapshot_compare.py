"""Offline comparison of two encrypted PayPal Sandbox SQLite backups.

These tests use fictional data only. No PayPal calls, uploads or live restore.
"""
from datetime import datetime, timezone
import json
import sqlite3
import uuid

import pytest

from tools import encrypted_snapshot as backup
from tools import sqlite_snapshot


@pytest.fixture
def archives(tmp_path):
    private=tmp_path/"private"
    private.mkdir(mode=0o700)
    dbfile=tmp_path/"demo.sqlite3"
    conn=sqlite3.connect(dbfile)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE events(id INTEGER PRIMARY KEY,name TEXT);
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
    conn.execute("INSERT INTO events VALUES(1,'PRIVATE SPORTS GROUP')")
    conn.execute("INSERT INTO expenses VALUES(1,'PRIVATE VENUE')")
    conn.execute("INSERT INTO people VALUES(1,1,'PRIVATE ALICE',1000,'sandbox_paid')")
    conn.execute("INSERT INTO people VALUES(2,1,'PRIVATE BOB',750,'unpaid')")
    conn.execute(
        "INSERT INTO payments VALUES(1,1,1,'completed',1000,"
        "'PRIVATE-CAPTURE-A','PRIVATE-ORDER-A','PRIVATE-REQUEST-A')"
    )
    conn.execute(
        "INSERT INTO payments VALUES(2,1,2,'created',750,NULL,"
        "'PRIVATE-ORDER-B','PRIVATE-REQUEST-B')"
    )
    conn.execute("INSERT INTO webhook_events VALUES('PRIVATE-WEBHOOK-A')")
    conn.commit()
    older=private/"older.csb"
    newer=private/"newer.csb"
    key1=private/"old.passphrase"
    key2=private/"new.passphrase"
    backup.keygen(key1)
    backup.keygen(key2)
    backup.seal(dbfile,older,key1)

    def make_new():
        conn.commit()
        backup.seal(dbfile,newer,key2)
        return backup.compare(older,newer,key1,key2)

    try:
        yield conn,older,newer,key1,key2,make_new
    finally:
        conn.close()


def test_identical_records_in_two_authenticated_archives_are_consistent(archives,capsys):
    conn,older,newer,key1,key2,make_new=archives
    report=make_new()
    assert report["status"]=="PASS"
    assert report["mode"]=="PAYPAL_SANDBOX"
    assert report["same_database_incarnation"] is True
    assert report["chronological_order_valid"] is True
    assert report["provider_orders_shared"]==2
    assert report["new_provider_orders"]==0
    assert report["prior_provider_orders_missing"]==0
    assert report["prior_capture_ids_missing"]==0
    assert report["prior_local_attempts_missing_same_epoch"]==0
    assert report["previous"]["unresolved_payment_records"]==1
    assert report["current"]["unresolved_payment_records"]==1
    assert backup.main(["compare","--previous",str(older),"--current",str(newer),
                        "--previous-key-file",str(key1),"--current-key-file",str(key2)])==0
    parsed=json.loads(capsys.readouterr().out)
    assert parsed["status"]=="PASS"
    assert "PRIVATE-" not in json.dumps(parsed)


def test_additional_sandbox_order_and_webhook_are_expected_forward_progress(archives):
    conn,older,newer,key1,key2,make_new=archives
    conn.execute("INSERT INTO people VALUES(3,1,'PRIVATE CATHY',500,'unpaid')")
    conn.execute(
        "INSERT INTO payments VALUES(3,1,3,'created',500,NULL,"
        "'PRIVATE-ORDER-C','PRIVATE-REQUEST-C')"
    )
    conn.execute("INSERT INTO webhook_events VALUES('PRIVATE-WEBHOOK-B')")
    result=make_new()
    assert result["status"]=="PASS"
    assert result["new_provider_orders"]==1
    assert result["current"]["payment_records"]==3
    assert result["current"]["webhook_events"]==2


def test_missing_previously_known_paypal_order_requires_external_reconciliation(archives):
    conn,older,newer,key1,key2,make_new=archives
    conn.execute("DELETE FROM payments WHERE id=2")
    report=make_new()
    assert report["status"]=="NEEDS_REVIEW"
    assert report["prior_provider_orders_missing"]==1
    assert report["prior_local_attempts_missing_same_epoch"]==1
    assert report["aggregate_count_decreases"]["payments"]==1
    assert "PRIVATE-ORDER-B" not in json.dumps(report)


def test_database_replacement_is_always_review_required_even_when_orders_survive(archives):
    conn,older,newer,key1,key2,make_new=archives
    conn.execute("UPDATE storage_identity SET incarnation_id=? WHERE id=1",(str(uuid.uuid4()),))
    result=make_new()
    assert result["status"]=="NEEDS_REVIEW"
    assert result["same_database_incarnation"] is False
    assert result["provider_orders_shared"]==2
    assert result["prior_provider_orders_missing"]==0
    assert result["prior_local_attempts_missing_same_epoch"] is None
    assert "PRIVATE-CAPTURE-A" not in json.dumps(result)


def test_existing_capture_disappearance_is_review_even_if_new_ledger_is_internally_valid(archives):
    conn,older,newer,key1,key2,make_new=archives
    conn.execute("UPDATE payments SET status='created',capture_id=NULL WHERE id=1")
    conn.execute("UPDATE people SET status='unpaid' WHERE id=1")
    result=make_new()
    assert result["status"]=="NEEDS_REVIEW"
    assert result["prior_capture_ids_missing"]==1
    assert result["shared_order_capture_conflicts"]==1
    assert result["shared_order_completion_regressions"]==1
    assert result["current"]["local_issue_count"]==0


def test_change_to_existing_provider_order_amount_is_detected(archives):
    conn,older,newer,key1,key2,make_new=archives
    conn.execute("UPDATE payments SET amount_cents=1050 WHERE id=1")
    conn.execute("UPDATE people SET share_cents=1050 WHERE id=1")
    report=make_new()
    assert report["shared_order_amount_changes"]==1
    assert report["status"]=="NEEDS_REVIEW"
    assert report["current"]["local_issue_count"]==0


def test_capture_id_replaced_with_another_capture_is_detected(archives):
    conn,older,newer,key1,key2,make_new=archives
    conn.execute("UPDATE payments SET capture_id='PRIVATE-CAPTURE-NEW' WHERE id=1")
    report=make_new()
    assert report["status"]=="NEEDS_REVIEW"
    assert report["shared_order_capture_conflicts"]==1
    assert report["prior_capture_ids_missing"]==1


def test_older_local_attempt_without_provider_id_can_only_be_matched_same_epoch(archives):
    conn,older,newer,key1,key2,make_new=archives
    # Recreate older file separately with a new pending create before sealing.
    conn.execute("INSERT INTO people VALUES(3,1,'PRIVATE D',100,'unpaid')")
    conn.execute(
        "INSERT INTO payments VALUES(3,1,3,'creating',100,NULL,NULL,'PRIVATE-REQUEST-D')"
    )
    conn.commit()
    second_old=older.parent/"pre-unknown.csb"
    backup.seal(older.parent.parent/"demo.sqlite3",second_old,key1)
    conn.execute("DELETE FROM payments WHERE id=3")
    conn.commit()
    backup.seal(older.parent.parent/"demo.sqlite3",newer,key2)
    result=backup.compare(second_old,newer,key1,key2)
    assert result["status"]=="NEEDS_REVIEW"
    assert result["previous_unknown_provider_order_attempts"]==1
    assert result["prior_local_attempts_missing_same_epoch"]==1
    assert result["provider_orders_shared"]==2


def test_semantic_inconsistency_requires_review_without_provider_request(archives):
    conn,older,newer,key1,key2,make_new=archives
    conn.execute("UPDATE people SET status='unpaid' WHERE id=1")
    result=make_new()
    assert result["status"]=="NEEDS_REVIEW"
    assert result["current"]["local_issue_count"]>=1
    assert "PRIVATE ALICE" not in json.dumps(result)


def test_reverse_generated_timestamps_are_review_required(archives,monkeypatch):
    conn,older,newer,key1,key2,make_new=archives
    class OldClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2020,1,1,tzinfo=timezone.utc)
    monkeypatch.setattr(sqlite_snapshot,"datetime",OldClock)
    conn.commit()
    backup.seal(older.parent.parent/"demo.sqlite3",newer,key2)
    # Restore date reader before checking both manifests and timestamps.
    monkeypatch.undo()
    result=backup.compare(older,newer,key1,key2)
    assert result["status"]=="NEEDS_REVIEW"
    assert result["chronological_order_valid"] is False


def test_modified_or_wrong_key_archives_rejected_without_plaintext_leak(archives):
    conn,older,newer,key1,key2,make_new=archives
    make_new()
    before=older.read_bytes()
    with pytest.raises(backup.ArchiveError,match="authentication failed"):
        backup.compare(older,newer,key2,key1)
    raw=bytearray(newer.read_bytes())
    raw[-22]^=4
    newer.write_bytes(raw)
    with pytest.raises(backup.ArchiveError,match="authentication failed"):
        backup.compare(older,newer,key1,key2)
    assert older.read_bytes()==before
    assert sorted(p.name for p in newer.parent.iterdir())==[
        "new.passphrase","newer.csb","old.passphrase","older.csb"
    ]


def test_same_encrypted_archive_must_not_be_compared_to_itself(archives):
    conn,older,newer,key1,key2,make_new=archives
    with pytest.raises(backup.ArchiveError,match="two different"):
        backup.compare(older,older,key1,key1)


def test_unbounded_financial_rows_fail_closed(archives,monkeypatch):
    conn,older,newer,key1,key2,make_new=archives
    make_new()
    monkeypatch.setattr(sqlite_snapshot,"MAX_LEDGER_AUDIT_ROWS",1)
    with pytest.raises(backup.ArchiveError):
        backup.compare(older,newer,key1,key2)


def test_compare_command_never_uploads_or_restores_and_has_distinct_exit_codes(archives,capsys):
    conn,older,newer,key1,key2,make_new=archives
    conn.execute("DELETE FROM payments WHERE id=2")
    make_new()
    rc=backup.main(["compare","--previous",str(older),"--current",str(newer),
                    "--previous-key-file",str(key1),"--current-key-file",str(key2)])
    assert rc==3
    answer=json.loads(capsys.readouterr().out)
    assert answer["status"]=="NEEDS_REVIEW"
    assert answer["prior_provider_orders_missing"]==1
    assert "PRIVATE-" not in json.dumps(answer)
    assert "PayPal" in answer["notice"]
    assert "import" in answer["notice"]
    assert not hasattr(backup,"restore")
