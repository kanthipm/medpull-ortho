"""An empty sports program can be removed whole; one with athletes cannot."""

from datetime import date

import pytest
from sqlalchemy import select

from app.console_credentials import mint
from app.models import Patient
from app.models.credential import ConsoleCredential
from app.models.sports import SportsEvent, SportsOrg, SportsProfile, SportsStaff, SportsTeam
from app.sports.identity import delete_sports_org


def _program(db, org_id: str) -> None:
    db.add(SportsOrg(id=org_id, name="Test Program", short_name="TP", kind="club", city="Houston", state="TX"))
    db.add(SportsTeam(id=f"{org_id}-a", org_id=org_id, name="A", sport="basketball"))
    db.flush()
    db.add(SportsStaff(id=f"{org_id}-coach", org_id=org_id, team_id=f"{org_id}-a", name="Coach", role="head_coach"))
    db.add(SportsEvent(team_id=f"{org_id}-a", date=date.today(), kind="practice", title="Practice"))
    db.commit()


def test_an_empty_program_goes_with_its_teams_staff_events_and_tokens(db):
    _program(db, "tp-empty")
    mint(db, "sports_org", "tp-empty", "org token")
    mint(db, "team", "tp-empty-a", "team token")
    db.commit()

    result = delete_sports_org(db, "tp-empty")

    assert result["deleted"] == "tp-empty"
    assert result["rows"] == {
        "sports_events": 1, "sports_staff": 1, "console_credentials": 2, "sports_teams": 1,
    }
    assert db.get(SportsOrg, "tp-empty") is None
    assert db.scalars(select(SportsTeam.id).where(SportsTeam.org_id == "tp-empty")).all() == []
    assert db.scalars(select(ConsoleCredential.id).where(
        ConsoleCredential.org_id.in_(["tp-empty", "tp-empty-a"]))).all() == []


def test_a_program_with_an_athlete_on_it_is_refused(db):
    _program(db, "tp-busy")
    src = db.get(Patient, "reyes")
    cols = {c.name: getattr(src, c.name) for c in Patient.__table__.columns}
    cols.update(id="tp-athlete", name="Busy Athlete", account_kind="sports", hospital_id=None,
                phone=None, linked_patient_id=None)
    db.add(Patient(**cols))
    db.flush()
    db.add(SportsProfile(patient_id="tp-athlete", sport="basketball", org_id="tp-busy", team_id="tp-busy-a"))
    db.commit()

    with pytest.raises(ValueError, match="tp-athlete"):
        delete_sports_org(db, "tp-busy")
    assert db.get(SportsOrg, "tp-busy") is not None

    with pytest.raises(ValueError, match="unknown"):
        delete_sports_org(db, "no-such-org")

    # tidy: the athlete out first, then the program goes
    db.delete(db.get(SportsProfile, "tp-athlete"))
    db.delete(db.get(Patient, "tp-athlete"))
    db.commit()
    assert delete_sports_org(db, "tp-busy")["deleted"] == "tp-busy"
