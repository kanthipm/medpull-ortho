"""Every device and platform an athlete or a program uses, and how each one
reaches MedPull.

Honesty is the design rule for the integrations screen. Four kinds of
connection exist and the app says which one it is drawing on:

* ``healthkit``  — the device writes to Apple Health and the app reads it
                   there. Live the moment Health is connected; carries
                   sleep, heart rate, HRV (SDNN), workouts, not the vendor's
                   own scores.
* ``junction``   — the vendor's cloud account, linked once through the
                   Junction hosted page. Live, with the vendor's summaries
                   (readiness, sleep stages, recovery).
* ``partner``    — a team system (Catapult, Kinexon, VALD, Hawkin…) whose
                   API needs a credential the program holds. Shown as a team
                   connection; until the credential exists its tiles carry
                   sample data and say so.
* ``import``     — a CSV or PDF export the staff drops in.
* ``ble``        — a sensor the phone talks to directly (a chest strap).

The 2023 NBA CBA bans wearables in games, allows them in practice with the
player's written consent and gives the player full access to the data;
NCAA rules let health data reach medical staff on the bench, not coaches.
Both are repeated on screen where a team device is connected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeviceSpec:
    key: str
    name: str
    maker: str
    category: str      # wearable | ring | sleep | scale | glucose | team_tracking | force | strength | timing | shooting | video | game_data | recovery | hydration | lab | strap
    path: str          # healthkit | junction | partner | import | ble | none
    provides: tuple[str, ...]
    symbol: str = "applewatch"
    sports: tuple[str, ...] = ()
    # What the integrations screen says under the name.
    blurb: str = ""
    # Whether a program (not an athlete) connects it.
    team: bool = False
    # The vendor's own score, when the path carries it (Junction) or not (HealthKit).
    scores: tuple[str, ...] = ()
    note: str = ""
    # Which Junction provider slug links it, when path == junction.
    junction_slug: str | None = None
    popular: bool = False


DEVICES: dict[str, DeviceSpec] = {}


def _d(spec: DeviceSpec) -> None:
    DEVICES[spec.key] = spec


# --- the athlete's own wearables -------------------------------------------------------------------

_d(DeviceSpec("apple_watch", "Apple Watch", "Apple", "wearable", "healthkit",
              ("Sleep stages", "Heart rate and resting HR", "HRV (SDNN)", "VO₂ max", "Heart-rate recovery",
               "Workouts and effort", "Wrist temperature", "Respiratory rate", "SpO₂", "Steps and energy"),
              symbol="applewatch", blurb="Read straight from Apple Health. Nothing else to sign into.",
              scores=(), popular=True))
_d(DeviceSpec("whoop", "WHOOP 5.0 / MG", "WHOOP", "wearable", "junction",
              ("Recovery score", "Strain", "Sleep performance and need", "HRV (RMSSD)", "Resting HR",
               "Respiratory rate", "Skin temperature", "SpO₂", "Workouts"),
              symbol="waveform.path.ecg", blurb="Sign in once; recovery, strain and sleep arrive every morning.",
              scores=("Recovery", "Strain", "Sleep performance"), junction_slug="whoop_v2", popular=True,
              note="Also writes sleep and workouts to Apple Health."))
_d(DeviceSpec("oura", "Oura Ring", "Oura", "ring", "junction",
              ("Readiness score", "Sleep score and stages", "HRV (RMSSD)", "Resting HR", "Temperature deviation",
               "Resilience", "Daily stress", "SpO₂", "Cardiovascular age", "Workouts"),
              symbol="circle.circle", blurb="Readiness, sleep and temperature from the ring's own cloud.",
              scores=("Readiness", "Sleep", "Resilience"), junction_slug="oura", popular=True))
_d(DeviceSpec("garmin", "Garmin", "Garmin", "wearable", "junction",
              ("Sleep and sleep score", "Overnight HRV", "Body Battery", "Stress", "VO₂ max", "Training load",
               "Workouts", "Pulse ox", "Respiration"),
              symbol="applewatch.radiowaves.left.and.right", blurb="Connect Garmin and the watch's health data flows in.",
              scores=("Body Battery", "Sleep score"), junction_slug="garmin", popular=True))
_d(DeviceSpec("polar", "Polar", "Polar", "wearable", "junction",
              ("Nightly Recharge", "Sleep stages", "Nightly HRV", "Cardio load", "Training sessions",
               "Continuous HR", "Orthostatic test", "SleepWise"),
              symbol="applewatch", blurb="Nightly Recharge and cardio load from Polar Flow.",
              scores=("Nightly Recharge", "Cardio load"), junction_slug="polar"))
_d(DeviceSpec("fitbit", "Fitbit / Pixel Watch", "Google", "wearable", "junction",
              ("Sleep stages", "HRV", "Resting HR", "SpO₂", "Skin temperature", "Steps", "Workouts"),
              symbol="applewatch", blurb="Through Google Health. The old Fitbit API closes on October 30, 2026.",
              junction_slug="google_health"))
_d(DeviceSpec("withings", "Withings", "Withings", "scale", "junction",
              ("Weight and body composition", "Blood pressure", "Sleep mat (sleep, HR, breathing)", "ScanWatch ECG and SpO₂"),
              symbol="scalemass.fill", blurb="The morning weigh-in, automatically.", junction_slug="withings"))
_d(DeviceSpec("ultrahuman", "Ultrahuman Ring", "Ultrahuman", "ring", "junction",
              ("Sleep", "HRV", "Resting HR", "Skin temperature", "Recovery and movement indexes"),
              symbol="circle.circle", blurb="Ring data from Ultrahuman's cloud.", junction_slug="ultrahuman"))
_d(DeviceSpec("coros", "Coros", "Coros", "wearable", "healthkit",
              ("Workouts", "Sleep", "Heart rate"), symbol="applewatch",
              blurb="Coros writes to Apple Health; the watch's own daily metrics stay in its app."))
_d(DeviceSpec("amazfit", "Amazfit / Zepp", "Zepp Health", "wearable", "healthkit",
              ("Sleep", "Heart rate", "Workouts"), symbol="applewatch",
              blurb="Through Apple Health."))
_d(DeviceSpec("ringconn", "RingConn", "RingConn", "ring", "healthkit",
              ("Sleep", "Heart rate", "HRV", "SpO₂"), symbol="circle.circle", blurb="Through Apple Health."))
_d(DeviceSpec("samsung", "Galaxy Watch / Ring", "Samsung", "wearable", "none",
              ("Sleep", "Heart rate", "Energy score"), symbol="applewatch",
              blurb="Samsung Health has no cloud API and no iPhone path; an Android build would read it on-device.",
              note="Not available on iPhone."))
_d(DeviceSpec("eight_sleep", "Eight Sleep Pod", "Eight Sleep", "sleep", "junction",
              ("Sleep stages and fitness score", "Overnight HR and HRV", "Breathing rate", "Bed temperature"),
              symbol="bed.double.fill", blurb="The bed's own sleep data, through Junction.", junction_slug="eight_sleep"))
_d(DeviceSpec("dexcom", "Dexcom G7 / Stelo", "Dexcom", "glucose", "junction",
              ("Glucose every five minutes", "Trends"), symbol="drop.fill",
              blurb="Continuous glucose, for fuelling around games. Descriptive only.", junction_slug="dexcom_v3"))
_d(DeviceSpec("libre", "FreeStyle Libre / Lingo", "Abbott", "glucose", "junction",
              ("Glucose every minute",), symbol="drop.fill", blurb="Through LibreView.", junction_slug="abbott_libreview"))
_d(DeviceSpec("polar_h10", "Polar H10 / Verity Sense", "Polar", "strap", "ble",
              ("Live heart rate", "RR intervals for HRV", "Orthostatic test"), symbol="heart.fill",
              blurb="The chest strap the phone talks to directly, for a two-minute HRV or orthostatic test."))
_d(DeviceSpec("hyperice", "Hyperice / Normatec", "Hyperice", "recovery", "healthkit",
              ("Compression and percussion sessions",), symbol="wind",
              blurb="Sessions log to Apple Health, so recovery work shows beside the load it followed."))

# --- team systems (a program connects these) ---------------------------------------------------------

_d(DeviceSpec("catapult", "Catapult Vector / ClearSky", "Catapult", "team_tracking", "partner",
              ("PlayerLoad and PlayerLoad per minute", "Accelerations, decelerations, changes of direction by band",
               "Jump count and jump-height bands", "Distance, high-speed distance and max velocity (indoor LPS)",
               "Basketball Movement Profile"),
              symbol="sensor.tag.radiowaves.forward.fill", team=True, popular=True,
              blurb="The practice and game load most college programs run on. Connected by the program through the Connect API.",
              note="NBA-approved for practice; no wearables in NBA games under the 2023 CBA."))
_d(DeviceSpec("kinexon", "Kinexon PERFORM", "Kinexon", "team_tracking", "partner",
              ("Mechanical load and intensity", "Jumps with heights", "Accelerations and decelerations",
               "Speed and distance (UWB)", "ACWR"),
              symbol="sensor.tag.radiowaves.forward.fill", team=True, popular=True,
              blurb="In use across most of the NBA. Connected by the program."))
_d(DeviceSpec("statsports", "STATSports Apex", "STATSports", "team_tracking", "partner",
              ("Total and high-speed distance", "Sprints and max speed", "Dynamic stress load", "Accelerations by zone"),
              symbol="sensor.tag.radiowaves.forward.fill", sports=("soccer",), team=True,
              blurb="GPS load for soccer. Connected by the program, or imported per session."))
_d(DeviceSpec("polar_team_pro", "Polar Team Pro", "Polar", "team_tracking", "partner",
              ("Heart rate and zones per player", "Training and cardio load", "Distance, speed, sprints"),
              symbol="heart.text.square.fill", team=True,
              blurb="A documented team API: the quickest real team connection to stand up."))
_d(DeviceSpec("firstbeat", "Firstbeat Sports", "Firstbeat", "team_tracking", "partner",
              ("TRIMP and training effect", "Quick Recovery Test (3 min HRV)", "Movement load"),
              symbol="waveform.path.ecg", team=True, blurb="Connected by the program or imported from Excel."))
_d(DeviceSpec("vert", "VERT", "VERT", "team_tracking", "import",
              ("Jump count", "Jump heights and % of max", "Jumps over 15 in"),
              symbol="figure.jumprope", sports=("basketball",), team=True, popular=True,
              blurb="Jump counts from the belt sensor, imported from the VERT export."))
_d(DeviceSpec("plantiga", "Plantiga insoles", "Plantiga", "team_tracking", "partner",
              ("Load and impact asymmetry", "Accelerations and decelerations by intensity"),
              symbol="shoe.fill", team=True, blurb="Insole sensors; connected by the program."))
_d(DeviceSpec("hawkin", "Hawkin Dynamics force plates", "Hawkin Dynamics", "force", "partner",
              ("Countermovement jump: height, RSI-modified, power, braking RFD, asymmetry",
               "Drop jump and rebound RSI", "Isometric mid-thigh pull", "Landing metrics"),
              symbol="rectangle.split.2x1.fill", team=True, popular=True,
              blurb="A cloud API the program's admin can key in an afternoon; every test lands on the Stats tab."))
_d(DeviceSpec("vald", "VALD ForceDecks / NordBord / ForceFrame / DynaMo", "VALD", "force", "partner",
              ("ForceDecks jump and isometric tests", "NordBord hamstring force and imbalance",
               "ForceFrame hip adduction and abduction", "DynaMo quad and hamstring strength", "SmartSpeed sprint splits"),
              symbol="rectangle.split.2x1.fill", team=True, popular=True,
              blurb="Credentials come from VALD support; until then, results import from VALD Hub."))
_d(DeviceSpec("kinvent", "Kinvent K-Push / K-Pull / K-Grip", "Kinvent", "strength", "import",
              ("Isometric knee extension and flexion", "Grip", "Balance"),
              symbol="dumbbell.fill", team=True, blurb="Imported from the Kinvent report."))
_d(DeviceSpec("gymaware", "GymAware / Perch / Vitruve (bar velocity)", "GymAware", "strength", "partner",
              ("Bar velocity and power per rep", "Estimated 1RM", "Load-velocity profile"),
              symbol="dumbbell.fill", team=True, blurb="Velocity-based training from the rack."))
_d(DeviceSpec("timing_gates", "Timing gates (SmartSpeed, Dashr, Brower)", "Various", "timing", "import",
              ("Sprint splits", "Lane agility", "505 and pro agility"),
              symbol="timer", team=True, blurb="Entered by the staff or imported from the gate software."))
_d(DeviceSpec("noah", "Noah shooting system", "Noah Basketball", "shooting", "partner",
              ("Shots made and attempted by spot", "Arc, depth, left-right"),
              symbol="basketball.fill", sports=("basketball",), team=True,
              blurb="Shooting sessions beside sleep and readiness, so the link between the two is visible."))
_d(DeviceSpec("shottracker", "ShotTracker", "ShotTracker", "shooting", "partner",
              ("Shot location and percentages", "Possessions"),
              symbol="basketball.fill", sports=("basketball",), team=True, blurb="Connected by the program."))
_d(DeviceSpec("homecourt", "HomeCourt", "Nex", "shooting", "import",
              ("Shot counts and makes", "Drill scores"), symbol="basketball.fill", sports=("basketball",),
              blurb="Log a session's numbers by hand from the app."))
_d(DeviceSpec("sportradar", "Sportradar game data", "Sportradar", "game_data", "partner",
              ("Box scores and minutes", "Play-by-play", "Advanced metrics"),
              symbol="chart.bar.doc.horizontal", team=True,
              blurb="Game minutes and box scores beside practice load."))
_d(DeviceSpec("uplift", "Uplift Capture (phone 3D)", "Uplift", "video", "partner",
              ("Jump and landing mechanics from two iPhones", "Knee valgus and landing errors"),
              symbol="video.fill", team=True, blurb="Markerless mechanics from phone video, through a public API."))
_d(DeviceSpec("inbody", "InBody / DXA", "InBody", "lab", "import",
              ("Body fat and lean mass", "Segmental lean mass"), symbol="figure.stand", team=True,
              blurb="Imported from the scan report."))
_d(DeviceSpec("nix", "Nix / Gatorade Gx sweat patch", "Nix", "hydration", "import",
              ("Sweat rate", "Sodium loss"), symbol="drop.fill", blurb="Entered after a session."))
_d(DeviceSpec("swingvision", "SwingVision", "SwingVision", "video", "healthkit",
              ("Match workouts on Apple Watch", "Shot and rally stats in the app"),
              symbol="figure.tennis", sports=("tennis",), blurb="The watch workout reaches Health; stats are logged by hand."))
_d(DeviceSpec("playsight", "PlaySight SmartCourt", "PlaySight", "video", "partner",
              ("Match video and AI stats",), symbol="video.fill", sports=("tennis",), team=True,
              blurb="Connected by the program."))
_d(DeviceSpec("playermaker", "Playermaker / CITYPLAY", "Playermaker", "team_tracking", "import",
              ("Ball touches and kicks", "Kick velocity", "Left-right foot balance", "Distance and sprints"),
              symbol="figure.soccer", sports=("soccer",), blurb="Logged from the app."))

PATH_LABELS = {
    "healthkit": "Via Apple Health", "junction": "Cloud account", "partner": "Team connection",
    "import": "Import", "ble": "Bluetooth", "none": "Not available on iPhone",
}

CATEGORY_LABELS = {
    "wearable": "Watches and bands", "ring": "Rings", "sleep": "Sleep", "scale": "Scales and vitals",
    "glucose": "Glucose", "strap": "Chest straps", "recovery": "Recovery tools",
    "team_tracking": "Practice and game load", "force": "Force plates and dynamometry",
    "strength": "Strength and bar velocity", "timing": "Timing gates", "shooting": "Shooting",
    "video": "Video and mechanics", "game_data": "Game data", "lab": "Body composition", "hydration": "Hydration",
}


def devices_for(sport: str) -> list[DeviceSpec]:
    return [d for d in DEVICES.values() if not d.sports or sport in d.sports]


def device_view(spec: DeviceSpec) -> dict[str, Any]:
    return {
        "key": spec.key, "name": spec.name, "maker": spec.maker, "category": spec.category,
        "category_label": CATEGORY_LABELS.get(spec.category, spec.category), "path": spec.path,
        "path_label": PATH_LABELS.get(spec.path, spec.path), "provides": list(spec.provides),
        "symbol": spec.symbol, "sports": list(spec.sports), "blurb": spec.blurb, "team": spec.team,
        "scores": list(spec.scores), "note": spec.note, "junction_slug": spec.junction_slug,
        "popular": spec.popular,
    }
