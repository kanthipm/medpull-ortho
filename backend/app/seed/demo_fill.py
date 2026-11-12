"""The clinic half of the showcase: fill a LIVE database with the clinic
personas, anchored to today.

    uv run python -m app.seed.demo_fill --db /path/to/recovery.db [--warm]
                                        [--no-persona-phones]

``fill(db, today)`` is the callable; the command line above is a thin
wrapper round it, and ``app.seed.showcase.fill_showcase`` calls it beside
the sports and Personal fills. Unlike ``app.seed.seed`` it never drops the
schema, and it writes only the charts it authors (``build_roster``): a row
with any other id — a real person who enrolled, an onboarding attempt
somebody abandoned, an athlete, a subscriber — is never read, changed or
deleted, whatever it does or does not carry.

What it does, anchored to today:

* the ortho roster (linda, robert, ... elena) keeps its ids, hospitals and
  scenarios and has every derived row regenerated, so surgery dates,
  observations, check-ins and adherence run up to today instead of stopping
  on the day the database was last filled;
* the demo hospital's roster — the two charts the shipped seed starts it
  with (reyes, medha) and the named patients written here — is rewritten
  with a device, a scenario, tasks, check-ins and a message thread;
* the H.I.R.T. Physical Therapy roster (app/seed/hirt.py): five lifters
  followed by text check-in alone, no wearable, with fourteen days of
  check-ins and their exercise calendar re-anchored to today;
* every hospital and care-team row those charts point at is added to a
  database that predates it;
* the risk engine is re-run for every chart it touched, and with ``--warm``
  the Groq insight caches are filled so the first console load is instant.

What a refill keeps on a persona: its app sessions (a phone signed in as
Cole yesterday is still signed in this morning), a phone number that is not
a 555 placeholder (a presenter bound their own through ``/api/demo/phone``),
its consent, and the clips a lifter sent back.

Deterministic: the same numpy streams as the seed, so re-running produces
the same numbers for the same day.

Demo orgs: see the module docstring of app/seed/patients.py.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def _bind_database(db_path: str) -> None:
    path = Path(db_path).expanduser().resolve()
    if not path.exists():
        sys.exit(f"database not found: {path}")
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    os.environ.setdefault("WARM_CACHES_ON_STARTUP", "false")


# --------------------------------------------------------------------------
# Roster
# --------------------------------------------------------------------------

# Ids that belong to real people on a database this has been run against. No
# persona may ever be given one: ``fill`` refuses a roster that names any.
PROTECTED = frozenset({"steve", "steve-test-8de9", "guest"})
DEMO_HOSPITAL = "hosp_demo"
TZ = "America/Chicago"

# Every persona is written with a number on the 555 exchange, which no phone
# can have. Anything else on a persona's chart was put there by a presenter
# (``/api/demo/phone``) so the demo's texts reach a real phone, and a refill
# leaves it alone.
_PLACEHOLDER_PHONE = re.compile(r"^\+1\d{3}555\d{4}$")


def is_placeholder_phone(phone: str | None) -> bool:
    return bool(phone) and _PLACEHOLDER_PHONE.match(phone) is not None


@dataclass(frozen=True)
class MessageSpec:
    days_ago: int
    hour: int
    sender: str  # patient | care_team | copilot
    text: str
    sender_id: str | None = None
    channel: str = "app"


@dataclass(frozen=True)
class Persona:
    """Everything one demo patient needs beyond the seed's PatientSpec."""

    spec: object  # app.seed.patients.PatientSpec
    scenario: object  # app.seed.scenarios.ScenarioSpec
    phone: str
    mrn: str
    care_pathway: str | None = None
    tasks: list = field(default_factory=list)  # app.seed.adherence.TaskSpec
    adherence_rate: float = 0.85
    conversations: list = field(default_factory=list)  # seed.conversations shape
    messages: list[MessageSpec] = field(default_factory=list)
    # Set by --no-persona-phones: leave this chart without a number so a
    # message sent to it on camera stores cleanly instead of failing to send.
    suppress_phone: bool = False
    # A chart followed by text check-in alone (no device, no generated
    # observations): the fourteen days of answers app.seed.hirt writes.
    reported_history: bool = False
    # What today's read on this chart is, in a few words: the line the
    # persona list shows under the name (app/seed/showcase.py).
    story: str = ""


def build_roster() -> tuple[list[Persona], list[Persona], list[Persona]]:
    """Every chart the clinic fill authors, in three lists: the ortho roster
    across its four hospitals, the demo hospital's roster, the HIRT lifters.
    Nothing in it depends on the day: dates are offsets ``write_persona``
    resolves against today."""
    from app.models.enums import ProcedureType as PT
    from app.models.enums import SourceProvider as SP
    from app.seed import adherence as adh
    from app.seed.adherence import TaskSpec
    from app.seed.conversations import CONVERSATIONS
    from app.seed.patients import ORTHO_DEMO_PATIENTS, PATIENTS, _spec
    from app.seed.scenarios import SCENARIOS, Ramp, ScenarioSpec
    from app.models.enums import MetricType as M

    C, P = "copilot", "patient"
    RN = "ct_torres"
    PTH = "ct_wooley"

    # --- the ortho roster the production database already carries ----------
    legacy_specs = ORTHO_DEMO_PATIENTS
    legacy_phones = {
        "linda": "+17135550111", "robert": "+17135550112", "sofia": "+17135550113",
        "aisha": "+17135550114", "priya": "+12145550115", "grace": "+17135550116",
        "david": "+17135550117", "james": "+12145550118", "elena": "+17135550119",
    }
    legacy_stories = {
        "linda": "Shoulder keeping her up: short nights for a week",
        "robert": "Steps sliding a little every day since surgery",
        "sofia": "Behind the expected curve at three weeks",
        "aisha": "Walking has levelled off since day 8",
        "priya": "Watch off most days: too little data to read",
        "grace": "Early days, and as expected",
        "david": "On plan at five weeks, asking to jog",
        "james": "Ahead of the expected curve at six weeks",
        "elena": "Ahead of the expected curve",
    }
    legacy_messages = {
        "linda": [
            MessageSpec(3, 14, "care_team", "Hi Linda, Maya from Dr. Chen's office. Your watch shows a few short nights in a row. Is the shoulder keeping you up?", RN),
            MessageSpec(3, 15, "patient", "Yes, I can't get comfortable on either side. Daytime is fine."),
            MessageSpec(3, 15, "care_team", "Thanks for telling us. Try a wedge pillow with the arm supported in front of you. I'll check back after the weekend.", RN),
            MessageSpec(1, 9, "patient", "Tried the wedge. A little better, still waking up twice."),
        ],
        "robert": [
            MessageSpec(2, 11, "care_team", "Robert, your step count has been sliding this week. Anything getting in the way of the short walks?", RN),
            MessageSpec(2, 13, "patient", "Just tired. I sit back down after a few minutes."),
            MessageSpec(2, 13, "care_team", "Understood. Let's aim for five minutes every two hours rather than one long walk. Dr. Chen will review your plan tomorrow.", RN),
        ],
        "aisha": [
            MessageSpec(4, 10, "care_team", "Hi Aisha, Sam from physical therapy. Your walks have leveled off. Are you still using the cane on the longer ones?", PTH),
            MessageSpec(4, 12, "patient", "Only when I go outside. In the house I hold the furniture."),
            MessageSpec(4, 12, "care_team", "Let's keep the cane for every walk this week so the hip loads evenly. I'll add two abduction sets to your plan.", PTH),
        ],
        "priya": [
            MessageSpec(2, 9, "care_team", "Hi Priya, we haven't had watch data for a few days. Could you pop it back on when you can?", RN),
            MessageSpec(2, 18, "patient", "Sorry, it was on the charger. Wearing it now."),
        ],
        "grace": [
            MessageSpec(0, 8, "care_team", "Good morning Grace. Day three is a big one. Keep the ankle pumps going and call us if you notice calf pain.", RN),
        ],
        "david": [
            MessageSpec(1, 17, "patient", "PT says my range is ahead of schedule. Can I start jogging?"),
            MessageSpec(1, 17, "care_team", "Great news, but no running before your six-week visit with Dr. Chen. Straight-line cycling is fine.", PTH),
        ],
    }
    legacy: list[Persona] = []
    for spec in legacy_specs:
        legacy.append(Persona(
            spec=spec,
            scenario=SCENARIOS.get(spec.id, ScenarioSpec()),
            phone=legacy_phones[spec.id],
            mrn=f"MH{int(hashlib.sha256(spec.id.encode()).hexdigest()[:6], 16) % 900000 + 100000:06d}",
            tasks=adh.TASKS.get(spec.id, []),
            adherence_rate=adh.RATES.get(spec.id, 0.85),
            conversations=CONVERSATIONS.get(spec.id, []),
            messages=legacy_messages.get(spec.id, []),
            story=legacy_stories[spec.id],
        ))

    # --- the demo hospital roster --------------------------------------------
    #
    # It opens with the two charts the shipped seed starts the hospital with
    # (app/seed/patients.py), written from the seed's own specs so a
    # database built by the seed and then filled reads the same as one that
    # was only ever filled: Marcus Reyes with his scenario, tasks and
    # check-ins re-anchored, and Medha Rao as the blank chart she is — no
    # device, nothing reported yet, which is what a new patient looks like.
    shipped = {spec.id: spec for spec in PATIENTS}
    general = "General care"
    new: list[Persona] = [
        Persona(
            spec=shipped["reyes"], scenario=SCENARIOS["reyes"],
            phone="+17135550120", mrn="DM100873",
            tasks=adh.TASKS["reyes"], adherence_rate=adh.RATES.get("reyes", 0.85),
            conversations=CONVERSATIONS.get("reyes", []),
            story="Resting heart rate and skin temperature up, walking down",
        ),
        Persona(
            spec=shipped["medha"], scenario=ScenarioSpec(),
            phone="+17135550110", mrn="DM100911",
            story="New chart: no device connected yet",
        ),
        Persona(
            spec=_spec("ana", "Ana Lee", 52, "F", PT.TKA, "Total Knee Replacement (TKA)",
                       5, SP.APPLE, "Apple Watch Series 9", 1, DEMO_HOSPITAL),
            scenario=ScenarioSpec(),
            phone="+17135550121", mrn="DM204117", story="Home and on plan",
            tasks=[
                TaskSpec("Ankle pumps every hour while awake", "Prevents blood clots", "self-report"),
                TaskSpec("Three short walks spread across the day", "Gentle, frequent movement helps the knee heal", "step data"),
                TaskSpec("Heel slides, 10 reps, 3x daily", "Restores knee bend", "self-report"),
            ],
            adherence_rate=0.9,
            conversations=[
                (3, 9, [
                    (C, "Good morning, Ana. Day two at home. How is the knee?"),
                    (P, "Swollen and stiff, but the pain is manageable with the schedule."),
                    (C, "That's expected this week. Are you getting the heel slides in?"),
                    (P, "Three times a day. The last set is the hardest."),
                ]),
                (0, 9, [
                    (C, "Hi Ana, quick check-in. How did you sleep?"),
                    (P, "Better than the first nights. Woke up once."),
                    (C, "Good. Any calf pain, fever, or new redness at the incision?"),
                    (P, "No, none of that."),
                ]),
            ],
            messages=[
                MessageSpec(4, 10, "care_team", "Hi Ana, Maya from Dr. Alvarez's team. Welcome home. Your tasks for this week are in the app; message me here with anything at all.", RN),
                MessageSpec(4, 11, "patient", "Thank you! Is it normal for the knee to feel warm?"),
                MessageSpec(4, 11, "care_team", "Yes, warmth and swelling are normal for the first two weeks. Spreading redness or a fever is what we want to hear about right away.", RN),
            ],
        ),
        Persona(
            spec=_spec("marcus", "Marcus Bennett", 61, "M", PT.NONE, general,
                       24, SP.FITBIT, "Fitbit Charge 6", 0, DEMO_HOSPITAL),
            scenario=ScenarioSpec(ramps=(
                Ramp(M.SLEEP_DURATION, 14, 20, mult_to=0.72),
                Ramp(M.RESTING_HR, 14, 22, add=6.0),
                Ramp(M.HRV_RMSSD, 14, 22, mult_to=0.82),
            )),
            phone="+17135550122", mrn="DM318452", care_pathway="general_recovery",
            story="Short nights for a week, resting heart rate up",
            tasks=[
                TaskSpec("Walk 20 minutes daily", "Keeps the heart and lungs conditioned", "step data"),
                TaskSpec("Log blood pressure each morning", "Lets the team see how the new dose is working", "self-report"),
            ],
            adherence_rate=0.62,
            conversations=[
                (6, 8, [
                    (C, "Morning, Marcus. How are you feeling this week?"),
                    (P, "Run down. I haven't been sleeping much since I went back to work."),
                    (C, "Thanks for saying so. How many hours would you guess?"),
                    (P, "Five, maybe. I'm up at four and can't get back off."),
                ]),
                (1, 8, [
                    (C, "Hi Marcus, checking in. Any better on the sleep?"),
                    (P, "No. And my chest feels like it's racing when I lie down."),
                    (C, "I'll pass that straight to your care team. Any chest pain, or shortness of breath walking?"),
                    (P, "No pain. I get winded on the stairs more than I used to."),
                ]),
            ],
            messages=[
                MessageSpec(1, 9, "care_team", "Marcus, Maya here. Your Fitbit shows your resting heart rate up and sleep down for about a week. Can you take a call from Dr. Chen this afternoon?", RN),
                MessageSpec(1, 9, "patient", "Yes, after 3 works."),
                MessageSpec(1, 15, "care_team", "Booked for 3:30. Please have your blood pressure log handy.", RN),
            ],
        ),
        Persona(
            spec=_spec("rosa", "Rosa Delgado", 44, "F", PT.NONE, general,
                       30, SP.OURA, "Oura Ring Gen4", 0, DEMO_HOSPITAL),
            scenario=ScenarioSpec(),
            phone="+17135550123", mrn="DM427790", care_pathway="general_recovery",
            story="Steady: back to her full walks",
            tasks=[
                TaskSpec("Walk 30 minutes, 5 days a week", "Builds back endurance after the pneumonia", "step data"),
                TaskSpec("Breathing exercises, 2x daily", "Keeps the lungs clear", "self-report"),
            ],
            adherence_rate=0.93,
            conversations=[
                (7, 18, [
                    (C, "Hi Rosa, how has the week been?"),
                    (P, "Really good. Back to my full walks and sleeping through."),
                    (C, "Any cough or breathlessness left?"),
                    (P, "A little cough in the morning, nothing else."),
                ]),
                (0, 18, [
                    (C, "Evening check-in, Rosa. Anything new?"),
                    (P, "Nothing new. I feel like myself again."),
                ]),
            ],
            messages=[
                MessageSpec(7, 19, "patient", "Do I still need the breathing exercises now that the cough is gone?"),
                MessageSpec(6, 8, "care_team", "Keep them up through the end of the month, Rosa. They're what's keeping the cough gone.", RN),
            ],
        ),
        Persona(
            spec=_spec("tom", "Thomas Nguyen", 67, "M", PT.THA, "Total Hip Replacement (THA)",
                       12, SP.APPLE, "Apple Watch SE 3", 2, DEMO_HOSPITAL),
            scenario=ScenarioSpec(track=0.84),
            phone="+17135550124", mrn="DM511263",
            story="Walking less than planned, staying indoors",
            tasks=[
                TaskSpec("Walk to the mailbox and back, twice daily", "Builds hip endurance", "step data"),
                TaskSpec("Hip abduction exercises, 2x daily", "Strengthens the muscles that steady the hip", "self-report"),
                TaskSpec("Use the walker for all walks this week", "Protects the new joint while strength returns", "self-report"),
            ],
            adherence_rate=0.68,
            conversations=[
                (5, 10, [
                    (C, "Good morning, Thomas. How is the hip this week?"),
                    (P, "Slow. I'm not walking as far as the sheet says I should."),
                    (C, "What's holding you back, pain or energy?"),
                    (P, "Mostly nerves. I don't trust it yet."),
                ]),
                (1, 10, [
                    (C, "Hi Thomas, checking in. How are the walks going?"),
                    (P, "Same as before. I stick to the house."),
                    (C, "Understood. I'll let your PT know so they can adjust the plan with you."),
                ]),
            ],
            messages=[
                MessageSpec(2, 14, "care_team", "Thomas, Sam from PT. Your walks are shorter than we'd expect at day ten. Would a home visit on Thursday help build some confidence outside?", PTH),
                MessageSpec(2, 16, "patient", "Yes please. Thursday morning is best."),
                MessageSpec(2, 16, "care_team", "Done, 10am Thursday. Keep the walker for now.", PTH),
            ],
        ),
        Persona(
            spec=_spec("helen", "Helen Okafor", 73, "F", PT.NONE, general,
                       18, SP.WITHINGS, "Withings ScanWatch 2", 0, DEMO_HOSPITAL),
            scenario=ScenarioSpec(
                dropout_frac=0.15,
                ramps=(Ramp(M.STEPS, 8, 16, mult_to=0.62),),
            ),
            phone="+17135550125", mrn="DM633908", care_pathway="general_recovery",
            story="Steps down a third, ankles puffy by evening",
            tasks=[
                TaskSpec("Weigh in every morning", "Catches fluid build-up early", "self-report"),
                TaskSpec("Walk 10 minutes, 3x daily", "Keeps the legs strong and the heart conditioned", "step data"),
                TaskSpec("Take the water pill with breakfast", "Keeps fluid off the lungs", "self-report"),
            ],
            adherence_rate=0.55,
            conversations=[
                (5, 9, [
                    (C, "Good morning, Helen. How are you getting on?"),
                    (P, "Tired. My ankles are puffy by the evening."),
                    (C, "Thank you for telling me. Are you managing the morning weigh-ins?"),
                    (P, "I forget most days, to be honest."),
                ]),
                (1, 9, [
                    (C, "Hi Helen, checking in. How are the walks?"),
                    (P, "Shorter. I get out of breath by the end of the street."),
                    (C, "I'll flag that for your nurse today. Any chest pain?"),
                    (P, "No chest pain."),
                ]),
            ],
            messages=[
                MessageSpec(1, 10, "care_team", "Helen, Maya here. Your steps have dropped by about a third over the last week and you mentioned puffy ankles. Can you weigh yourself this morning and send me the number?", RN),
                MessageSpec(1, 11, "patient", "It says 168. It was 164 last week."),
                MessageSpec(1, 11, "care_team", "Thank you. Dr. Chen is going to call you before lunch about the water pill.", RN),
            ],
        ),
        Persona(
            spec=_spec("kevin", "Kevin Walsh", 38, "M", PT.ACL, "ACL Reconstruction",
                       20, SP.GARMIN, "Garmin Forerunner 265", 0, DEMO_HOSPITAL),
            scenario=ScenarioSpec(track=1.06),
            phone="+17135550126", mrn="DM745120",
            story="On plan at three weeks, asking to run",
            tasks=[
                TaskSpec("PT program, 3 sessions weekly", "Graft-safe strength progression", "PT attendance"),
                TaskSpec("Stationary bike, 15 minutes daily", "Restores range without loading the graft", "self-report"),
                TaskSpec("No running or pivoting", "Protects the graft while it heals", "self-report"),
            ],
            adherence_rate=0.94,
            conversations=[
                (6, 17, [
                    (C, "Hey Kevin, how's the knee holding up in PT?"),
                    (P, "Good. Full extension now and the bike is easy."),
                    (C, "Any swelling after sessions?"),
                    (P, "A bit, ice sorts it."),
                ]),
                (0, 17, [
                    (C, "Hi Kevin, weekly check-in. Anything new?"),
                    (P, "Nope. Walking normally, itching to run."),
                    (C, "Hold that thought until your surgeon says go."),
                ]),
            ],
            messages=[
                MessageSpec(3, 12, "patient", "Can I add light jogging on the treadmill? Feels ready."),
                MessageSpec(3, 13, "care_team", "Not yet, Kevin. Straight-line jogging starts at week twelve if the six-week strength test goes well. Bike and pool are fine.", PTH),
            ],
        ),
        Persona(
            spec=_spec("lucia", "Lucia Fernandez", 55, "F", PT.NONE, general,
                       4, SP.APPLE, "Apple Watch Series 10", 0, DEMO_HOSPITAL),
            scenario=ScenarioSpec(),
            phone="+17135550127", mrn="DM858341", care_pathway="general_recovery",
            story="First week home, signals coming in",
            tasks=[
                TaskSpec("Wear the watch day and night", "Lets your care team see your recovery", "device sync"),
                TaskSpec("Walk 15 minutes daily", "Rebuilds stamina after the hospital stay", "step data"),
            ],
            adherence_rate=0.8,
            conversations=[
                (1, 9, [
                    (C, "Hi Lucia, welcome to the program. How are you feeling since you got home?"),
                    (P, "Weak, but glad to be home. I walked around the block yesterday."),
                    (C, "That's a good start. Any dizziness when you stand?"),
                    (P, "A little the first morning, not since."),
                ]),
            ],
            messages=[
                MessageSpec(3, 10, "care_team", "Welcome, Lucia. Maya from the care team. Your watch is linked and I can see your steps coming through. I'll check in every couple of days this first week.", RN),
                MessageSpec(3, 12, "patient", "Thank you Maya."),
            ],
        ),
        # --- the two the room should be looking at -------------------------
        #
        # A demo roster with one high-risk patient shows the tier but not the
        # judgement: the interesting question on this screen is which of the
        # red rows to open first. These two are both HIGH and they get there
        # by different routes — one is a vitals story on a fresh knee, the
        # other a functional collapse three weeks out — so the worklist has a
        # call to make rather than a single alarm to read out.
        Persona(
            # Possible early prosthetic joint infection: the reyes signature
            # (coupled RHR/skin-temp rise with HRV and activity falling away)
            # landing on day 9, with the patient's own words matching it.
            spec=_spec("dana", "Dana Okonkwo", 64, "F", PT.TKA,
                       "Total Knee Replacement (TKA)",
                       9, SP.APPLE, "Apple Watch Series 10", 2, DEMO_HOSPITAL),
            scenario=ScenarioSpec(ramps=(
                Ramp(M.RESTING_HR, 5, 9, add=8.0),
                Ramp(M.SKIN_TEMP, 5, 9, add=0.7),
                Ramp(M.HRV_RMSSD, 5, 9, mult_to=0.78),
                Ramp(M.STEPS, 5, 9, mult_to=0.58),
                Ramp(M.WALKING_SPEED, 5, 9, mult_to=0.75),
            )),
            phone="+17135550128", mrn="DM962574",
            story="Warm, red knee and a temperature of 100.9",
            tasks=[
                TaskSpec("Walk 10 minutes, twice daily", "Restores knee motion and circulation", "step data"),
                TaskSpec("Quad sets, 3 sets of 10", "Rebuilds the thigh strength that guards the joint", "self-report"),
                TaskSpec("Check the incision each evening", "Catches redness or drainage early", "self-report"),
            ],
            adherence_rate=0.54,
            conversations=[
                (4, 9, [
                    (C, "Good morning, Dana. How is the knee today?"),
                    (P, "Warmer than last week, and it aches deeper than it did."),
                    (C, "Thank you for telling me. Any redness spreading, or drainage from the incision?"),
                    (P, "A little redness around the middle of it. Nothing leaking."),
                ]),
                (1, 8, [
                    (C, "Hi Dana, checking in. How was the night?"),
                    (P, "Chills around two in the morning. I took my temperature, 100.9."),
                    (C, "I'm flagging this for your care team now. Please don't wait for your next visit."),
                ]),
            ],
            messages=[
                MessageSpec(1, 9, "care_team", "Dana, Maya from Dr. Alvarez's team. A temperature of 100.9 with a warm, red knee on day nine needs to be seen today, not at your Thursday visit. Can you come to the clinic this morning?", RN),
                MessageSpec(1, 10, "patient", "I can be there by eleven."),
                MessageSpec(1, 10, "care_team", "Perfect, we'll have a room ready. Please bring the thermometer readings you've taken.", RN),
            ],
        ),
        Persona(
            # Three weeks out and going backwards: a near-fall stopped her
            # walking, and the sleep and heart-rate drift followed. No fever,
            # nothing to admit for — the deterioration is in the pattern,
            # which is the case a worklist is supposed to catch.
            spec=_spec("omar", "Omar Haddad", 58, "M", PT.THA,
                       "Total Hip Replacement (THA)",
                       22, SP.FITBIT, "Fitbit Charge 6", 2, DEMO_HOSPITAL),
            scenario=ScenarioSpec(
                track=0.80,
                plateau_after=12,
                ramps=(
                    Ramp(M.STEPS, 13, 20, mult_to=0.45),
                    Ramp(M.WALKING_SPEED, 13, 20, mult_to=0.70),
                    Ramp(M.SLEEP_DURATION, 13, 20, mult_to=0.74),
                    Ramp(M.RESTING_HR, 13, 20, add=7.0),
                    Ramp(M.HRV_RMSSD, 13, 20, mult_to=0.80),
                ),
            ),
            phone="+17135550129", mrn="DM071685",
            story="Stopped walking after a near-fall",
            tasks=[
                TaskSpec("Walk 15 minutes, twice daily", "Keeps the hip loading evenly as strength returns", "step data"),
                TaskSpec("Hip abduction exercises, 2x daily", "Strengthens the muscles that steady the hip", "self-report"),
                TaskSpec("Log pain before and after walks", "Shows the team what the hip does under load", "self-report"),
            ],
            adherence_rate=0.41,
            conversations=[
                (6, 19, [
                    (C, "Evening, Omar. How did the walks go this week?"),
                    (P, "I stopped them. I nearly went down on the front step on Monday."),
                    (C, "That sounds frightening. Were you hurt?"),
                    (P, "No, I caught the rail. But I'm not going out there again."),
                ]),
                (2, 20, [
                    (C, "Hi Omar, checking in. Have you managed any walking since we spoke?"),
                    (P, "Only room to room. The hip feels weaker than it did a fortnight ago."),
                    (C, "Thank you for being straight with me. I'll make sure your team sees this today."),
                ]),
            ],
            messages=[
                MessageSpec(3, 15, "care_team", "Omar, Sam from physical therapy. Your steps have dropped by more than half since the near-fall and your sleep is going the same way. That combination at three weeks is worth a proper look — can I come to you on Wednesday and walk the front step with you?", PTH),
                MessageSpec(3, 18, "patient", "Wednesday is fine. The step is what worries me."),
                MessageSpec(3, 18, "care_team", "Then that's where we'll start. Keep the walks inside until I'm there.", PTH),
            ],
        ),
    ]

    # --- H.I.R.T. Physical Therapy ------------------------------------------
    #
    # The second demo org. Five lifters, no devices: their history is the
    # lifter check-in, fourteen evenings of it (app/seed/hirt.py), and their
    # tiers come from what they reported. The thread carries the enrolment
    # text and a line or two, because the clinic texts rather than charts.
    from app.seed import hirt

    GREGG, HARRIS = "ct_gregg", "ct_harris"
    enrol = (
        "Welcome to the two-week check-in. Each evening you'll get one text — pain, the "
        "night, today's program, how hard you trained. Tap through or reply here; it takes "
        "under a minute."
    )
    hirt_messages = {
        "hirt-cole": [
            MessageSpec(14, 11, "care_team", enrol, GREGG, channel="sms"),
            MessageSpec(14, 12, "patient", "Got it. Do I count my own lifting as training or just the program?", channel="sms"),
            MessageSpec(14, 12, "care_team", "Everything you do in the gym counts — that's the point of asking.", GREGG, channel="sms"),
        ],
        "hirt-tessa": [
            MessageSpec(14, 11, "care_team", enrol, GREGG, channel="sms"),
            MessageSpec(13, 21, "patient", "Thanks, done. Quick to fill in.", channel="sms"),
        ],
        "hirt-devon": [
            MessageSpec(14, 11, "care_team", enrol, HARRIS, channel="sms"),
        ],
        "hirt-june": [
            MessageSpec(14, 11, "care_team", enrol, HARRIS, channel="sms"),
        ],
        "hirt-rafael": [
            MessageSpec(14, 11, "care_team", enrol, GREGG, channel="sms"),
            MessageSpec(14, 13, "patient", "Cool, thanks for the screen today.", channel="sms"),
        ],
    }
    lifters: list[Persona] = [
        Persona(
            spec=spec, scenario=ScenarioSpec(), phone=hirt.PHONES[spec.id], mrn=hirt.MRNS[spec.id],
            care_pathway=spec.care_pathway, messages=hirt_messages.get(spec.id, []),
            reported_history=True, story=hirt.STORIES[spec.id],
        )
        for spec in hirt.HIRT_PATIENTS
    ]
    return legacy, new, lifters


# --------------------------------------------------------------------------
# Database work
# --------------------------------------------------------------------------

PER_PATIENT_TABLES = [
    "observations", "risk_assessments", "insights", "established_baselines",
    "monitoring_windows", "adherence_records", "task_verifications",
    "adherence_tasks", "messages", "notifications", "care_actions",
    "checkin_invites", "phone_verifications", "checkins",
    "rtm_documents", "rtm_interactions", "rtm_time_logs", "rtm_enrollment",
    # The exercise calendar (app/hep): one row per patient, exercise and day,
    # so a refill has to clear the old one before writing today's.
    "exercise_assignments",
]
# The device and the aggregator link, dropped only for the charts written
# from nothing each time. App sessions are in neither list: a refill never
# signs a phone out of a persona.
DEVICE_TABLES = ["wearable_connections", "devices"]


def _existing_tables(db) -> set[str]:
    from sqlalchemy import text

    return set(db.execute(text("select name from sqlite_master where type='table'")).scalars())


def purge_patient(db, patient_id: str, *, devices: bool, tables: set[str]) -> None:
    """Delete everything derived for one persona, ahead of writing it again.
    ``devices`` also drops the device and the aggregator link. The chart
    itself, its app sessions and its consent stay."""
    from sqlalchemy import text

    if "checkin_messages" in tables:
        db.execute(text(
            "delete from checkin_messages where checkin_id in "
            "(select id from checkins where patient_id = :pid)"
        ), {"pid": patient_id})
    if "attachments" in tables:
        # The thread is about to be rewritten, and SQLite hands a deleted
        # row's id to the next insert: a file left pointing at a line that is
        # gone would turn up under whichever new line took its number. Files
        # come off their lines here; the lifters' return clips go back on the
        # calendar afterwards (hirt.relink_return_clips).
        db.execute(text("update attachments set message_id = null where patient_id = :pid"),
                   {"pid": patient_id})
    for table in PER_PATIENT_TABLES + (DEVICE_TABLES if devices else []):
        if table in tables:
            db.execute(text(f"delete from {table} where patient_id = :pid"), {"pid": patient_id})


def ensure_orgs(db, personas: list[Persona]) -> int:
    """Every hospital and care-team row the roster points at, for a database
    that predates one of them. Without its hospital a chart is moved to the
    demo hospital at the next start (``app/main.py`` gives a chart whose
    hospital is unknown the first seeded one), and the next fill would move
    it back. Idempotent; returns rows added."""
    from app.models import CareTeamMember, Hospital, NotificationPreference
    from app.models.enums import NotificationChannel
    from app.seed import hirt
    from app.seed.patients import CARE_TEAM, HOSPITALS, ORTHO_DEMO_HOSPITALS

    added = hirt.ensure_org(db)
    wanted = {p.spec.hospital_id for p in personas}
    for h in (*HOSPITALS, *ORTHO_DEMO_HOSPITALS):
        if h.id in wanted and db.get(Hospital, h.id) is None:
            db.add(Hospital(id=h.id, name=h.name, system=h.system, city=h.city, state=h.state,
                            timezone=h.timezone, load_unit=h.load_unit))
            added += 1
    for ct in CARE_TEAM:
        if db.get(CareTeamMember, ct.id) is None:
            db.add(CareTeamMember(id=ct.id, name=ct.name, role=ct.role))
            for channel, enabled in ((NotificationChannel.IN_APP, True),
                                     (NotificationChannel.SMS, False),
                                     (NotificationChannel.EMAIL, False)):
                db.add(NotificationPreference(recipient_id=ct.id, channel=channel, enabled=enabled))
            added += 1
    db.commit()
    return added


def _dob(today: date, age: int, patient_id: str) -> date:
    offset = sum(ord(c) for c in patient_id) % 300
    try:
        return date(today.year - age, today.month, today.day) - timedelta(days=offset + 1)
    except ValueError:  # 29 Feb
        return date(today.year - age, today.month, 28) - timedelta(days=offset + 1)


def write_persona(db, persona: Persona, today: date) -> dict[str, int]:
    """Write one persona's chart and everything on it, anchored to
    ``today``; the chart row is created when the database has none. Call
    after ``purge_patient``. Returns row counts."""
    from app.connectors.ingest import ingest_observations
    from app.models import (
        AdherenceRecord, AdherenceTask, Checkin, CheckinMessage, Device, Patient,
    )
    from app.models.mobile import Message
    from app.seed import adherence as adh
    from app.seed.generators import generate_patient_observations

    spec = persona.spec
    surgery = today - timedelta(days=spec.postop_day)
    discharge = surgery + timedelta(days=spec.discharge_offset)

    patient = db.get(Patient, spec.id)
    if patient is None:
        patient = Patient(id=spec.id, created_at=datetime.combine(surgery, dtime(9, 0)))
        db.add(patient)
    patient.name = spec.name
    patient.initials = spec.initials
    patient.age = spec.age
    patient.sex = spec.sex
    patient.procedure_type = spec.procedure
    patient.procedure_display = spec.procedure_display
    patient.surgery_date = surgery
    patient.discharge_date = discharge
    patient.timezone = TZ
    patient.surgeon_id = spec.surgeon_id
    patient.assigned_provider_id = spec.assigned_id or spec.surgeon_id
    patient.hospital_id = spec.hospital_id
    # Personas carry their placeholder number so the charts read as complete;
    # Steve asked for that explicitly and drives every real SMS through his
    # own verified number instead. Know the trade-off: Sendblue delivers only
    # to a contact verified in its dashboard, which an invented number can
    # never be, so a console message or task dispatch to a persona is recorded
    # as a failed delivery and shows a badge in the thread. Pass
    # --no-persona-phones to clear them for a take that needs a clean thread.
    #
    # A number that is not a placeholder is a presenter's own, bound through
    # /api/demo/phone so the demo's texts reach a real phone. It stays.
    if patient.phone is None or is_placeholder_phone(patient.phone):
        patient.phone = None if persona.suppress_phone else persona.phone
    patient.date_of_birth = _dob(today, spec.age, spec.id)
    patient.mrn = persona.mrn
    patient.care_pathway = persona.care_pathway
    db.flush()

    counts: dict[str, int] = {}
    if spec.provider is not None:
        device = db.get(Device, f"dev_{spec.id}")
        if device is None:
            device = Device(id=f"dev_{spec.id}", patient_id=spec.id)
            db.add(device)
        device.source_provider = spec.provider
        device.device_model = spec.device_model
        device.connected_at = datetime.combine(surgery - timedelta(days=14), dtime(10, 0))
        device.last_sync_at = datetime.combine(today, dtime(7, 30))
        device.status = "connected"
        db.commit()
        obs = generate_patient_observations(spec, persona.scenario, today)
        ingested, _, _ = ingest_observations(db, obs)
        counts["observations"] = ingested
    else:
        # No wearable: a chart followed by what the patient reports. Any
        # device row left from an earlier life is gone with purge_patient.
        db.commit()
        counts["observations"] = 0

    n = 0
    if persona.reported_history:
        from app.seed import hirt

        written = hirt.write_history(db, spec.id, today)
        n += written["checkins"]
        counts["observations"] += written["observations"]
        counts["exercise_assignments"] = hirt.write_schedule(db, spec.id, today)["assignments"]
        counts["return_clips"] = hirt.relink_return_clips(db, spec.id)
    for days_ago, hour, lines in persona.conversations:
        checkin = Checkin(
            patient_id=spec.id,
            occurred_at=datetime.combine(today - timedelta(days=days_ago), dtime(hour, 12)),
            channel="app",
        )
        db.add(checkin)
        db.flush()
        for seq, (who, text) in enumerate(lines):
            db.add(CheckinMessage(checkin_id=checkin.id, seq=seq, who=who, text=text))
        n += 1
    counts["checkins"] = n

    task_rows = []
    for t in persona.tasks:
        row = AdherenceTask(
            patient_id=spec.id, title=t.title, why=t.why, verified_by=t.verified_by,
            kind="custom", status="pending",
            created_at=datetime.combine(max(surgery, today - timedelta(days=13)), dtime(6, 0)),
        )
        db.add(row)
        task_rows.append(row)
    db.flush()
    # adh.daily_statuses draws from the patient's own stream; the rate table
    # only knows the legacy ids, so patch it for the personas' rate.
    adh.RATES[spec.id] = persona.adherence_rate
    statuses = adh.daily_statuses(spec.id, len(task_rows))
    n = 0
    for day_offset, day_statuses in enumerate(statuses):
        record_date = today - timedelta(days=len(statuses) - 1 - day_offset)
        if record_date < surgery:
            continue
        for task_row, status in zip(task_rows, day_statuses):
            db.add(AdherenceRecord(
                patient_id=spec.id, task_id=task_row.id, date=record_date, status=status,
            ))
            n += 1
    counts["adherence_records"] = n

    for m in persona.messages:
        at = datetime.combine(today - timedelta(days=m.days_ago), dtime(m.hour, 5))
        db.add(Message(
            patient_id=spec.id, sender=m.sender, sender_id=m.sender_id, text=m.text,
            channel=m.channel, created_at=at,
            read_by_patient_at=at + timedelta(minutes=20) if m.sender != "patient" else at,
            read_by_care_team_at=at if m.sender != "patient" else (
                at + timedelta(hours=1) if m.days_ago > 0 else None
            ),
            delivery_status="delivered" if m.sender != "patient" else None,
        ))
    counts["messages"] = len(persona.messages)
    db.commit()
    return counts


def refresh_briefing_and_engine(
    db, patient_ids: list[str], say: Callable[[str], None] = logger.info
) -> dict[str, str]:
    """Drop the roster briefing (it was written about the old roster) and
    re-run the engine for each chart. Returns the tier each one reads."""
    from sqlalchemy import text

    from app.engine.pipeline import run_patient

    db.execute(text("delete from insights where patient_id is null"))
    db.commit()
    tiers: dict[str, str] = {}
    for pid in patient_ids:
        assessment = run_patient(db, pid)
        tiers[pid] = str(assessment.risk_level)
        say(f"  engine: {pid:12s} {assessment.risk_level:12s} score={assessment.risk_score:.2f}")
    return tiers


def warm_insights(
    db, patient_ids: list[str], pause: float, say: Callable[[str], None] = logger.info
) -> None:
    from app.llm.insights import get_daily_briefing, get_patient_insight
    from app.models.enums import InsightKind

    kinds = (InsightKind.WORKLIST_REASON, InsightKind.PATIENT_SUMMARY,
             InsightKind.SUGGESTED_ACTIONS)
    for pid in patient_ids:
        for kind in kinds:
            row = get_patient_insight(db, kind, pid)
            say(f"  insight: {pid:12s} {kind:18s} via {row.llm_provider}")
            if row.llm_provider != "fallback":
                time.sleep(pause)
    briefing = get_daily_briefing(db)
    say(f"  briefing via {briefing.llm_provider}")


def roster_ids() -> list[str]:
    """The id of every chart the clinic fill authors, in the order it writes them."""
    legacy, new, lifters = build_roster()
    return [p.spec.id for p in (*legacy, *new, *lifters)]


def fill(
    db,
    today: date,
    *,
    suppress_phones: bool = False,
    warm: bool = False,
    pause: float = 2.0,
    say: Callable[[str], None] = logger.info,
) -> dict:
    """Write every clinic persona, anchored to ``today``, and re-run the
    engine for each. Idempotent: a second run on the same day leaves the same
    rows. Only the roster's own ids are touched (see the module docstring
    for what is kept on them); an id that is on the roster but belongs to a
    row that is not a clinic chart is skipped and reported.

    ``suppress_phones`` leaves the personas without a placeholder number,
    ``warm`` fills the model's insight caches afterwards (``pause`` seconds
    apart), and ``say`` receives one progress line per step.

    Returns ``{"personas": [...ids written], "skipped": {id: why}, "tiers":
    {id: tier}, "orgs_added": n, "counts": {table: rows written}}``.
    """
    from app.models import Patient
    from app.personal.scope import is_clinic

    legacy, new, lifters = build_roster()
    if suppress_phones:
        legacy, new, lifters = (
            [replace(p, suppress_phone=True) for p in group] for group in (legacy, new, lifters)
        )
        say("demo patients will be left without a phone number")
    # The ortho roster keeps its device and aggregator link across a refill;
    # the demo hospital's personas and the lifters are written from nothing.
    plan = [(p, False) for p in legacy] + [(p, True) for p in (*new, *lifters)]
    claimed = PROTECTED & {p.spec.id for p, _ in plan}
    if claimed:
        raise RuntimeError(f"the roster names a protected id: {', '.join(sorted(claimed))}")

    tables = _existing_tables(db)
    added = ensure_orgs(db, [p for p, _ in plan])
    if added:
        say(f"added {added} hospital, care-team or program row(s) this database lacked")

    written: list[str] = []
    skipped: dict[str, str] = {}
    totals: dict[str, int] = {}
    for persona, devices in plan:
        pid = persona.spec.id
        existing = db.get(Patient, pid)
        if existing is not None and not is_clinic(existing):
            skipped[pid] = f"the row with this id is a {existing.account_kind} account"
            say(f"  skipped   {pid:12s} {skipped[pid]}")
            continue
        purge_patient(db, pid, devices=devices, tables=tables)
        db.commit()
        counts = write_persona(db, persona, today)
        written.append(pid)
        for table, n in counts.items():
            totals[table] = totals.get(table, 0) + n
        say(f"  {'wrote' if existing is None else 'refreshed':9s} {pid:12s} {counts}")

    tiers = refresh_briefing_and_engine(db, written, say)
    if warm:
        warm_insights(db, written, pause, say)
    return {"personas": written, "skipped": skipped, "tiers": tiers, "orgs_added": added,
            "counts": totals}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", required=True, help="SQLite file to fill in place")
    parser.add_argument("--warm", action="store_true", help="fill the Groq insight caches")
    parser.add_argument("--warm-only", action="store_true",
                        help="skip regeneration; only fill the insight caches for the demo roster")
    parser.add_argument("--pause", type=float, default=2.0,
                        help="seconds between Groq calls while warming")
    parser.add_argument("--no-persona-phones", action="store_true",
                        help="leave the demo patients without a phone number, so a message "
                             "sent to one stores cleanly instead of recording a failed SMS")
    args = parser.parse_args()
    _bind_database(args.db)

    import app.models  # noqa: F401 — register every table

    from app.database import SessionLocal, ensure_schema

    ensure_schema()
    db = SessionLocal()
    try:
        if args.warm_only:
            ids = roster_ids()
            refresh_briefing_and_engine(db, ids, print)
            warm_insights(db, ids, args.pause, print)
        else:
            fill(db, date.today(), suppress_phones=args.no_persona_phones, warm=args.warm,
                 pause=args.pause, say=print)
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
