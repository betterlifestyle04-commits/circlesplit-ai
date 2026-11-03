"""Calendar serialization: RFC 5545 safety, deterministic IDs, floating times."""
from datetime import datetime, timezone

import pytest

from calendar_export import build_ics, escape_ics


STAMP=datetime(2026,11,3,20,0,tzinfo=timezone.utc)


def example():
    return [
        {"id":51,"start_time":"09:00","end_time":"10:00","title":"Warmup","note":"Meet at court"},
        {"id":52,"start_time":"10:00","end_time":"11:15","title":"Group match","note":""},
    ]


def unfolded(ics):
    return ics.replace("\r\n ","")


def test_ics_has_exact_calendar_properties_and_local_floating_times():
    ics=build_ics(7,"Volleyball night","2026-12-08",example(),3,stamp=STAMP)
    clean=unfolded(ics)
    assert ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
    assert ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT\r\n")==2
    assert clean.count("END:VEVENT\r\n")==2
    assert "DTSTAMP:20261103T200000Z" in clean
    assert "DTSTART:20261208T090000\r\n" in clean
    assert "DTEND:20261208T100000\r\n" in clean
    assert "DTSTART;TZID=" not in clean
    assert "DTSTART:20261208T090000Z" not in clean
    assert "SEQUENCE:3\r\n" in clean
    assert "STATUS:TENTATIVE\r\n" in clean
    assert "confirm location/timezone" in clean.lower()
    for secret in ("ATTENDEE:", "ORGANIZER:", "PAYPAL", "token=", "share_cents"):
        assert secret not in clean
    assert all(len(line.encode("utf-8"))<=75 for line in ics.split("\r\n") if line)


def test_calendar_update_uses_same_opaque_uids_and_higher_revision():
    original=unfolded(build_ics(7,"Volleyball","2026-12-08",example(),1,stamp=STAMP))
    updated=example()
    updated[0]["title"]="New warmup"
    next_version=unfolded(build_ics(7,"Volleyball","2026-12-08",updated,2,stamp=STAMP))
    uids=[row for row in original.split("\r\n") if row.startswith("UID:")]
    assert len(uids)==2
    for uid in uids:
        assert uid in next_version
        assert not uid.startswith("UID:51@") and not uid.startswith("UID:52@")
    assert "SEQUENCE:2" in next_version
    assert "New warmup" in next_version
    other=unfolded(build_ics(8,"Volleyball","2026-12-08",example(),1,stamp=STAMP))
    assert all(uid not in other for uid in uids)


def test_escape_text_prevents_calendar_property_injection():
    title="Team\\break, semi; newline\nATTENDEE:mailto:someone@example.com"
    note="Bring gloves\r\nBEGIN:VEVENT\r\nSUMMARY:Injected\0"
    ics=build_ics(7,title,"2026-12-08",
        [{"id":10,"start_time":"12:00","end_time":"12:30",
          "title":"Welcome\nEND:VEVENT","note":note}],1,stamp=STAMP)
    text=unfolded(ics)
    assert text.count("BEGIN:VEVENT\r\n")==1
    assert text.split("\r\n").count("END:VEVENT")==1
    assert "\r\nATTENDEE:" not in text
    assert "\r\nSUMMARY:Injected" not in text
    assert "BEGIN:VEVENT\\nSUMMARY:Injected" in text
    assert "Welcome\\nEND:VEVENT" in text
    assert "Team\\\\break\\, semi\\; newline\\nATTENDEE:" in text
    assert "\x00" not in text


def test_long_unicode_fields_are_folded_on_utf8_octet_boundaries():
    title="Møte 🎉 café " + "ø".join(["verylong"]*10)
    note="🍀"*39+" Additional instructions"
    value=build_ics(10,title,"2026-12-30",[{
        "id":1,"start_time":"18:00","end_time":"19:00",
        "title":"Volleyball warmup","note":note
    }],1,stamp=STAMP)
    assert all(len(line.encode("utf-8"))<=75 for line in value.split("\r\n") if line)
    assert title in unfolded(value)
    assert note in unfolded(value)
    assert "\r\n " in value
    assert value.endswith("\r\n")


@pytest.mark.parametrize("date_value,slots",[
    ("2026-02-30",example()),
    ("garbage",example()),
    ("2026-12-08",[]),
    ("2026-12-08",[{"id":1,"start_time":"10:00","end_time":"09:59","title":"Invalid"}]),
    ("2026-12-08",[{"id":1,"start_time":"10:00","end_time":"11:00","title":"One"},
                    {"id":2,"start_time":"10:30","end_time":"11:30","title":"Overlap"}]),
])
def test_calendar_validation_rejects_missing_or_invalid_agenda(date_value,slots):
    with pytest.raises(ValueError):
        build_ics(1,"Event",date_value,slots,1,stamp=STAMP)


def test_escape_ics_never_contains_raw_line_breaks():
    escaped=escape_ics("One\r\nTwo\\Three;Four,Five")
    assert escaped=="One\\nTwo\\\\Three\\;Four\\,Five"
    assert "\r" not in escaped and "\n" not in escaped
