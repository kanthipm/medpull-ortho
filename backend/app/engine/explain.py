"""Plain-English explanations for every metric, signal and chart — the text
behind the "i" icons on the console and in the patient app.

One entry per thing a person can look at: the care metrics (M1–M18, C1–C6),
the wearable signal cards, and the page-level charts (trajectory, deviation
index, adherence, data confidence, the risk tier). Each entry says, for a
clinician, what the thing measures, which data it takes in, how the number
is produced, how to read it, and how much data it needs before it shows;
and, for the patient, the same thing in everyday words with no clinical
verdict in it.

The copy lives here, beside the code that computes the numbers, so the two
cannot drift apart: a threshold changed in a metric module is a line to
change here too. Served as one static payload (``GET /api/explain``) that
the console fetches once and caches for the session.
"""

from __future__ import annotations

from typing import Any, TypedDict


class Explanation(TypedDict, total=False):
    title: str
    what: str          # what the number is
    inputs: str        # the data it takes in
    how: str           # how it is computed, in words
    reading: str       # how to read the statuses and the chart
    shows_after: str   # the minimum history before it says anything
    patient_what: str  # for the patient: what it is
    patient_why: str   # for the patient: why it matters
    patient_help: str  # for the patient: what helps it show / improve


METRICS: dict[str, Explanation] = {
    "M1": {
        "title": "Acute:chronic load ratio",
        "what": "How much the patient has been moving this week compared with their own recent "
                "weeks — the classic overload-versus-progression check.",
        "inputs": "Daily steps from the wearable or phone (active energy or exercise minutes when "
                  "a device reports no steps).",
        "how": "The mean daily load over the last 7 days divided by the mean over the last 28 "
               "(all days since post-op day 2 while the history is shorter). On an orthopedic "
               "pathway the same ratio is also taken along the expected recovery curve for those "
               "days, and the patient's ratio is read relative to that, so a normal first-month "
               "climb is not mistaken for overreaching.",
        "reading": "About 1.0 means this week matched the recent weeks. Above 1.3 the patient is "
                   "loading faster than their recent tolerance (Watch), above 1.5 well past it "
                   "(Flag). Below 0.8 load is stalling, below 0.6 collapsing. The chart shows "
                   "daily load with the 0.8–1.3 band and the 7-day rolling mean.",
        "shows_after": "A first, provisional read after 5 days of load (counted from post-op day "
                       "2) using a 3-day window; the full 7-day window from 10 days. A "
                       "provisional read can raise a Watch but never a Flag.",
        "patient_what": "How much you moved this week compared with your own recent weeks.",
        "patient_why": "Building up too fast is the most common reason a recovery stalls or "
                       "hurts more; a steady climb is what the plan wants.",
        "patient_help": "Wear your watch or carry your phone every day. The first reading "
                        "appears after about five days of steps.",
    },
    "M2": {
        "title": "Symptom–load sensitivity",
        "what": "Whether extra activity on one day costs the patient more pain (or breathlessness "
                "or fatigue) the next morning, and by how much.",
        "inputs": "Daily steps (or energy / exercise minutes) and the next morning's symptom "
                  "score from the check-in or the pain log.",
        "how": "A regression of next-day symptom score on same-day load over the last 21 days, "
               "with the post-op day held fixed so the recovery itself — walking more and "
               "hurting less every day — is not read as a dose-response. The slope is the cost "
               "in points per 1,000 steps, with its 90% interval; the earlier and later halves "
               "are compared to see whether tolerance is improving.",
        "reading": "A slope near zero means activity is not costing symptoms. 0.25 or more with "
                   "a resolved interval is Watch (the cost is climbing), 0.5 or more with a "
                   "clear t-statistic is Flag (irritability rising). The scatter shows each "
                   "paired day with the fitted line.",
        "shows_after": "4 paired days (a step count and a next-day symptom log) for a first "
                       "read, 6 to settle. A provisional read can raise a Watch but never a Flag.",
        "patient_what": "Whether a bigger day leaves you sorer the next morning.",
        "patient_why": "It tells your team how much you can safely add each week.",
        "patient_help": "Log your pain each morning. Four mornings with a step count the day "
                        "before is enough for a first reading.",
    },
    "M3": {
        "title": "Loading asymmetry decay",
        "what": "How the limp is settling: walking asymmetry (or double support) day by day, "
                "and whether it has plateaued at an elevated level.",
        "inputs": "Walking asymmetry from the guided walk in the app or Apple's gait metrics; "
                  "double support when asymmetry is not available.",
        "how": "An exponential-decay curve is fitted to the daily values, a 10-day trend test "
               "decides whether the decline is real, and a change-point search over the last "
               "21 days finds where a plateau began.",
        "reading": "Under 8% asymmetry reads as near-symmetric. Above that: Watch while it is "
                   "still improving, Flag when it has plateaued above 10% after post-op day 10. "
                   "The chart shows the daily values, the fitted decay and the plateau marker.",
        "shows_after": "3 days of walking data for a first read, 7 to settle.",
        "patient_what": "How evenly you are walking on both legs.",
        "patient_why": "A limp that keeps settling is normal; one that stops settling is "
                       "something physio can fix early.",
        "patient_help": "Do the guided walk in the app a few times a week, or carry your phone "
                        "in a front pocket on your walks.",
    },
    "M4": {
        "title": "Walking economy",
        "what": "How much heart-rate effort each unit of walking costs — the physiological price "
                "of a walk, and whether it is falling as the patient reconditions.",
        "inputs": "Heart rate and cadence (or speed) during walks: the guided walk in the app, "
                  "or a wearable's workout detail.",
        "how": "For each walk, mean heart rate above resting divided by mean cadence; the last "
               "three walks are compared with the first three.",
        "reading": "A falling cost is reconditioning. 15% up is Watch, 30% up is Flag — an "
                   "early sign of deconditioning or guarding.",
        "shows_after": "2 walks with heart rate for a first read, 6 to settle.",
        "patient_what": "How hard your heart works for each step.",
        "patient_why": "As you get fitter the same walk should feel, and measure, easier.",
        "patient_help": "Do the guided walk in the app with your watch on.",
    },
    "M5": {
        "title": "Endurance-fade index",
        "what": "Whether the patient can sustain a walk, or slows down within it.",
        "inputs": "Minute-by-minute cadence from walks of six minutes or more.",
        "how": "The slope of cadence across the minutes of each walk, as a percentage of the "
               "opening cadence per minute, averaged over the last three walks; the minute the "
               "cadence first drops under 90% of its opening value is the time to fatigue.",
        "reading": "Under 1.5% per minute is sustained. Over 1.5% is Watch, over 3% is Flag.",
        "shows_after": "One walk of six minutes or more; three to settle.",
        "patient_what": "Whether you keep your pace through a whole walk or fade part-way.",
        "patient_why": "Fading early means shorter, more frequent walks will build you up "
                       "better than one long one.",
        "patient_help": "Record a six-minute walk in the app.",
    },
    "M6": {
        "title": "Sit-to-stand frequency",
        "what": "How many times a day the patient gets up from a chair — a daily measure of "
                "functional strength and willingness to move.",
        "inputs": "Chair-rise counts from the sit-to-stand task or the phone's motion capture.",
        "how": "The last 7 days' mean against the 7 before.",
        "reading": "20% more than last week is improving; 25% fewer is Watch.",
        "shows_after": "2 days of counts for a first read, 7 to settle.",
        "patient_what": "How often you stand up from a chair each day.",
        "patient_why": "Standing up is the everyday strength that gets you walking.",
        "patient_help": "Do the sit-to-stand task in the app when it is assigned.",
    },
    "M7": {
        "title": "Cadence recovery curve",
        "what": "Walking pace (steps per minute, or walking speed) against the expected recovery "
                "curve and the patient's own trend.",
        "inputs": "Cadence from the app's guided walk, or walking speed and step length from "
                  "Apple's gait metrics.",
        "how": "The latest reading and its 3-day mean are compared with the expected value for "
               "this post-op day (from the pre-op norm and the procedure curve) and with the "
               "patient's own prior week.",
        "reading": "Climbing with recovery is OK. Flag when the control chart says pace is "
                   "below the expected curve; Watch on a dip of 8% or more against the "
                   "patient's own trend.",
        "shows_after": "2 days of walking data for a first read, 7 to settle.",
        "patient_what": "How quickly you are walking, compared with what is typical at this "
                        "point in recovery.",
        "patient_why": "Pace is one of the best single signs that a recovery is on course.",
        "patient_help": "Carry your phone on walks or do the guided walk.",
    },
    "M8": {
        "title": "Stair reintroduction & flight tolerance",
        "what": "When stairs re-enter the routine, and whether the number of flights keeps "
                "growing afterwards.",
        "inputs": "Flights climbed from the phone or watch, plus stair ascent speed from walks "
                  "recorded in the app.",
        "how": "The first post-op day with a flight, then the last 7 days' mean flights against "
               "the 7 before.",
        "reading": "No stairs after week three on a lower-limb pathway is Watch; growth of 10% "
                   "or less once stairs have been back for a week is a plateau.",
        "shows_after": "The first flight climbed; a week of flights to judge a plateau.",
        "patient_what": "When you started doing stairs again and how many flights a day.",
        "patient_why": "Stairs are the milestone most people care about; your team watches "
                       "that the number keeps growing.",
        "patient_help": "Keep your phone with you; it counts flights on its own.",
    },
    "M9": {
        "title": "Nocturnal disruption",
        "what": "How fragmented the nights are, and whether the fragmentation tracks evening "
                "pain — the pain-not-controlled-overnight signal people under-report by day.",
        "inputs": "Sleep stages from an overnight-worn wearable (awake time per night) and the "
                  "evening pain log; total sleep only when stages are not reported.",
        "how": "The awake fraction of each night, averaged over the last 7 nights, against the "
               "patient's pre-op nights (or their first post-op nights); correlated with the "
               "evening symptom score over the last 14 nights.",
        "reading": "Fragmentation 50% above the patient's own baseline is Watch; the same with "
                   "a correlation of 0.4 or more to evening pain is Flag.",
        "shows_after": "2 nights with sleep stages for a first read, 7 to settle.",
        "patient_what": "How broken your sleep is, and whether pain is behind it.",
        "patient_why": "Pain that wakes you is often under-reported in the day; this lets your "
                       "team see it.",
        "patient_help": "Wear your watch overnight and log your pain in the evening.",
    },
    "M10": {
        "title": "Autonomic recovery trend",
        "what": "Whether the body is settling after surgery: heart-rate variability and resting "
                "heart rate against the patient's own baseline.",
        "inputs": "Overnight HRV (RMSSD, or SDNN on Apple) and resting heart rate.",
        "how": "The mean of the smoothed z-scores of HRV (sign flipped) and resting heart rate "
               "over the last 7 nights; 'sustained' is three nights in a row with both beyond "
               "one standard deviation in the adverse direction.",
        "reading": "An index above 0.8 is Watch (recovery lagging); above 1.5 and sustained is "
                   "Flag (a systemic stress pattern: overloading, poorly controlled pain, or a "
                   "brewing complication — context for review, never a diagnosis).",
        "shows_after": "2 scored nights for a first read, 7 to settle.",
        "patient_what": "How well your body is recovering night to night.",
        "patient_why": "Heart rate and heart-rate variability shift before you feel it.",
        "patient_help": "Wear your watch overnight; it needs two nights to start.",
    },
    "M11": {
        "title": "Circadian rest–activity amplitude",
        "what": "How strong the daily rhythm is: active days and quiet nights, or everything "
                "flattened into the same level.",
        "inputs": "Hourly steps (or hourly heart-rate samples) over the last 14 days.",
        "how": "A 24-hour cosine fit per day gives the rhythm's relative amplitude; interdaily "
               "stability measures how repeatable the day is.",
        "reading": "A flattening of 30% or more against the first days is Watch — it often "
                   "precedes reduced daytime activity and poor nights.",
        "shows_after": "3 days with hourly data for a first read, 10 to settle.",
        "patient_what": "How clear the difference is between your active day and your quiet night.",
        "patient_why": "A strong day-night rhythm goes with better sleep and steadier recovery.",
        "patient_help": "Carry your phone or wear your watch through the day and night.",
    },
    "M12": {
        "title": "Multi-signal deterioration index",
        "what": "How far today's overnight vitals sit, together, from the patient's own stable "
                "baseline — the safety net for signals that move in concert.",
        "inputs": "Resting heart rate, respiratory rate, skin temperature, HRV and SpO₂ from an "
                  "overnight-worn device (at least three of the five).",
        "how": "A Mahalanobis distance of today's standardized readings from the patient's own "
               "14-day multivariate baseline (shrinkage covariance), read as a chi-square tail "
               "with one degree of freedom per signal, alongside the weighted composite the "
               "risk tier uses.",
        "reading": "Under 2σ is within the patient's usual range. A tail probability under 0.10 "
                   "is Watch; under 0.01, or a high composite, is Flag. Always phrased as "
                   "'signals deviating from baseline — recommend review', never as a named "
                   "complication.",
        "shows_after": "Three signals reporting today; the baseline behind the distance deepens "
                       "each day and settles after a week.",
        "patient_what": "Whether several of your overnight readings moved away from your "
                        "normal at the same time.",
        "patient_why": "One reading can wobble; several moving together is what your team wants "
                       "to know about early.",
        "patient_help": "Wear your watch overnight. Your team is told whenever this needs a look.",
    },
    "M13": {
        "title": "Thermal–cardiac coupling",
        "what": "Whether skin temperature and resting heart rate are rising together night "
                "after night, with HRV suppressed.",
        "inputs": "Skin temperature, resting heart rate and HRV from an overnight-worn device.",
        "how": "Correlation and lag between the temperature and heart-rate z-scores over the "
               "last 7 nights, counting the nights where temperature is elevated and the "
               "cardiac signals are adverse too.",
        "reading": "Two or more coupled nights with a correlation of 0.5 or more is Flag; one "
                   "coupled night, or two without the correlation, is Watch.",
        "shows_after": "3 scored nights for a first read, 5 to settle.",
        "patient_what": "Whether your temperature and heart rate are climbing together overnight.",
        "patient_why": "That pattern is one your care team would rather hear about a day early.",
        "patient_help": "Wear your watch overnight.",
    },
    "M14": {
        "title": "Verified adherence",
        "what": "How much of the care plan is actually being done, with wearable verification "
                "where it exists.",
        "inputs": "Assigned tasks and their completion records over the last 14 days (verified "
                  "by data, self-reported, or missed).",
        "how": "Verified completions count in full, self-reports at half weight, over every "
               "assigned task-day; this week's verified rate is compared with last week's.",
        "reading": "Under 50% is Flag, under 75% (or a 20-point drop) is Watch. The grid shows "
                   "each task by day: a filled dot is verified, a ring is self-reported, a dash "
                   "is missed.",
        "shows_after": "The first completion record.",
        "patient_what": "How much of your plan you are completing.",
        "patient_why": "The plan is built on a dose; your team adjusts it to what you can do.",
        "patient_help": "Tick off tasks in the app, by text or by voice.",
    },
    "M15": {
        "title": "Disengagement risk",
        "what": "Whether the patient is drifting away from the program before anyone has said so.",
        "inputs": "Check-in timing, reply length, the week-on-week movement trend and missed tasks.",
        "how": "A weighted score: check-in latency 40%, shrinking replies 20%, falling "
               "movement 20%, missed tasks 20%.",
        "reading": "Under 35 is engaged; 35–60 is Watch; 60 or more is Flag — reach out today.",
        "shows_after": "The first check-in or assigned task.",
        "patient_what": "How connected you are with the program this week.",
        "patient_why": "Recoveries go better with a quick daily check-in than with silence.",
        "patient_help": "Answer the check-ins when they come; a sentence is enough.",
    },
    "M16": {
        "title": "Data confidence",
        "what": "How clearly the engine can see this patient — the gate in front of every "
                "other reading.",
        "inputs": "Which key signals (steps, resting HR, HRV, sleep, skin temperature, SpO₂) "
                  "the patient's own sources report, on how many of the last 7 days, and when "
                  "the device last synced.",
        "how": "The lower of two fractions: the share of recent days carrying the patient's key "
               "signals, and the share of their panel still reporting. The panel is the signals "
               "their sources have ever reported (floored at three), so a watch without a "
               "temperature sensor is judged on what it has.",
        "reading": "75% and above is high confidence; 40–75% moderate; under 40% the patient "
                   "cannot be seen and the risk tier reads Missing data rather than guessing.",
        "shows_after": "Immediately; it is what the other metrics wait on.",
        "patient_what": "How much of your data is reaching your care team.",
        "patient_why": "Everything else on this screen rests on it.",
        "patient_help": "Keep your watch charged and worn, and open the app now and then so it "
                        "syncs.",
    },
    "M17": {
        "title": "Recovery-trajectory fit",
        "what": "How the functional index (activity relative to the patient's own norm) is "
                "tracking against the expected curve for the procedure, and how fast it is "
                "climbing.",
        "inputs": "Daily steps (70%) and walking speed (30%) against the pre-op norm, or a "
                  "post-op anchor when there is no pre-op history.",
        "how": "A saturating-exponential fit to the index gives the recovery rate, compared "
               "with the curve's own rate over the same days; the verdict itself (behind, on, "
               "ahead) is the engine's trajectory comparison.",
        "reading": "Behind is 12% or more under the curve over the last five days; ahead is "
                   "10% over — never claimed without a pre-op norm. The chart is the index over "
                   "the expected band with the fitted curve.",
        "shows_after": "4 days of functional index for a first read (the index needs two "
                       "scored days from post-op day 2 to exist), 8 to settle.",
        "patient_what": "How your activity compares with a typical recovery from your operation.",
        "patient_why": "It is the simplest answer to 'am I where I should be?'.",
        "patient_help": "Wear your watch or carry your phone daily. The curve appears after "
                        "about four days of steps.",
    },
    "M18": {
        "title": "Plateau / regression change-point",
        "what": "The most recent sustained shift in a daily series: a plateau that should still "
                "be rising, or a fall.",
        "inputs": "Daily steps, walking speed, sleep and resting heart rate over the last 28 days.",
        "how": "CUSUM binary segmentation on each series; a split counts when the two segments "
               "differ by at least one pooled standard deviation and a t-test agrees. A plateau "
               "is growth confidently below half of what the curve still expects.",
        "reading": "A regression (a fall) in the last 14 days is Flag; a plateau is Watch. The "
                   "marker on the chart is the day it started.",
        "shows_after": "6 days of steps or walking speed for a first read, 8 to settle.",
        "patient_what": "Whether something changed direction recently.",
        "patient_why": "A stall or a dip is easier to fix the week it starts.",
        "patient_help": "Keep the daily data flowing; it needs about a week of history.",
    },
    "C1": {
        "title": "Weight trend & fluid-gain signal",
        "what": "Daily weight against its recent median, and sudden gains.",
        "inputs": "A connected scale or a daily weight log.",
        "how": "Today's weight against the 14-day median, plus the 24-hour change.",
        "reading": "1 kg in 24 h or 2 kg in a week is Flag (a signal consistent with fluid "
                   "retention — for review); half that is Watch.",
        "shows_after": "2 prior days weighed for a first read, 7 to settle.",
        "patient_what": "Your weight against your recent normal.",
        "patient_why": "A fast gain is usually fluid, and your team wants to hear about it early.",
        "patient_help": "Weigh yourself every morning.",
    },
    "C2": {
        "title": "Oxygen saturation & desaturation burden",
        "what": "Overnight SpO₂ and how many days ran low.",
        "inputs": "SpO₂ from an overnight-worn wearable or a pulse-oximeter log.",
        "how": "Days in the last 7 with a mean under 90% and under 92%, with the control chart "
               "against the patient's own baseline.",
        "reading": "Two days under 90%, or a control-chart flag, is Flag; one day under 92% is "
                   "Watch.",
        "shows_after": "2 days of SpO₂ for a first read, 7 to settle.",
        "patient_what": "How much oxygen your blood is carrying overnight.",
        "patient_why": "It is one of the first things to shift with a chest problem.",
        "patient_help": "Wear your watch overnight.",
    },
    "C3": {
        "title": "Glucose time-in-range",
        "what": "The share of glucose readings between 70 and 180 mg/dL.",
        "inputs": "A continuous glucose monitor or a glucose log.",
        "how": "Time-in-range over the last 14 days, readings under 70 counted.",
        "reading": "70% or more on target; under 70% Watch; under 50% Flag.",
        "shows_after": "10 readings.",
        "patient_what": "How often your sugar is in the target band.",
        "patient_why": "Steady sugars heal better and feel better.",
        "patient_help": "Keep your sensor on, or log your readings.",
    },
    "C4": {
        "title": "Blood-pressure control",
        "what": "Mean blood pressure and the share of readings above target.",
        "inputs": "A connected cuff or an AM/PM blood-pressure log.",
        "how": "The 7-day mean and the share of readings at or above 140/90.",
        "reading": "A quarter of readings above target is Watch; half, or a mean systolic of 150, "
                   "is Flag.",
        "shows_after": "2 readings for a first read, 4 to settle.",
        "patient_what": "Your blood pressure against its target.",
        "patient_why": "It is the one number that most needs to stay in range.",
        "patient_help": "Take a reading morning and evening.",
    },
    "C5": {
        "title": "Symptom burden trend",
        "what": "A daily symptom score from logs and check-ins, its level and its slope.",
        "inputs": "Pain, breathlessness and fatigue logs, plus symptom answers in check-ins.",
        "how": "The components are averaged per day and trended over 14 days.",
        "reading": "Rising 2 points a week, or a level of 7 or more, is Flag; rising half a "
                   "point a week is Watch.",
        "shows_after": "2 days with a symptom log for a first read, 7 to settle.",
        "patient_what": "How your symptoms are trending week to week.",
        "patient_why": "The trend matters more than any single bad day.",
        "patient_help": "Answer the daily check-in.",
    },
    "C6": {
        "title": "Sedentary burden",
        "what": "How much of the waking day is spent still.",
        "inputs": "Hourly steps from the phone (daily steps when hourly buckets are not available).",
        "how": "Waking hours (07–22) with under 50 steps, averaged over the last 7 days; else "
               "days under 1,500 steps, scaled to the recovery curve on an orthopedic pathway.",
        "reading": "10 or more sedentary hours a day is Watch; 12 or more is Flag.",
        "shows_after": "2 days of steps for a first read, 7 to settle.",
        "patient_what": "How much of your day you spend sitting.",
        "patient_why": "Short, frequent movement breaks do more for recovery than one long walk.",
        "patient_help": "Carry your phone; a two-minute walk each hour breaks up the long stretches.",
    },
}

_WEARABLE = "The patient's wearable, synced through the app or the aggregator."
_GUIDED = "The guided walk in the MedPull app (phone in a front pocket), or Apple's gait metrics."
_VITAL_HOW = ("Each day is scored against the patient's own baseline — their pre-op days when "
              "there are any, otherwise their first post-op days from day 2 — on a smoothed "
              "control chart. A flag needs two consecutive days outside the limits in the "
              "adverse direction; a slow drift is caught by a cumulative-sum test over the "
              "last two weeks.")
_VITAL_SHOWS = ("2 days of readings (from post-op day 2 on) for a first read, 3 to settle the "
                "baseline. A provisional baseline can raise a Watch but never a Flag.")
_FUNC_HOW = ("Compared with the expected recovery curve for the procedure rather than the "
             "pre-op norm — every patient walks less after surgery, and that is not a "
             "finding. With a pre-op norm the comparison is absolute; without one the curve's "
             "shape is projected from the patient's own early post-op level, which tracks pace "
             "rather than capacity.")

SIGNALS: dict[str, Explanation] = {
    "steps": {
        "title": "Daily steps",
        "what": "Total steps per day — the broadest measure of how much the patient is moving.",
        "inputs": _WEARABLE + " A phone counts steps on its own when no watch is worn.",
        "how": _FUNC_HOW,
        "reading": "The dashed line is the expected count for today. Falling well under it "
                   "for two days is a flag; the finding says the percentage below expected.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How many steps you take each day.",
        "patient_why": "Steps are the backbone of recovery: your team watches that the count "
                       "climbs week by week at a pace that suits your operation.",
        "patient_help": "Carry your phone or wear your watch every day.",
    },
    "resting_hr": {
        "title": "Resting heart rate",
        "what": "Heart rate at rest, measured overnight.",
        "inputs": _WEARABLE,
        "how": _VITAL_HOW,
        "reading": "The dashed line is the patient's own baseline. A sustained rise is the "
                   "finding; a fall is not.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "Your heart rate while you sleep.",
        "patient_why": "A resting heart rate that climbs for a few days is an early hint the "
                       "body is working harder than it should.",
        "patient_help": "Wear your watch overnight.",
    },
    "hrv_rmssd": {
        "title": "Heart rate variability (RMSSD)",
        "what": "The beat-to-beat variation of the heart at rest — higher is more recovered.",
        "inputs": _WEARABLE,
        "how": _VITAL_HOW,
        "reading": "A sustained fall below the patient's own baseline is the finding.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How much your heart rhythm varies at rest; higher means better rested.",
        "patient_why": "It drops when the body is under strain, often before anything else does.",
        "patient_help": "Wear your watch overnight.",
    },
    "hrv_sdnn": {
        "title": "Heart rate variability (SDNN)",
        "what": "Apple's HRV statistic, used in place of RMSSD on an Apple Watch.",
        "inputs": "Apple Watch, through Apple Health.",
        "how": _VITAL_HOW,
        "reading": "A sustained fall below the patient's own baseline is the finding.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How much your heart rhythm varies at rest; higher means better rested.",
        "patient_why": "It drops when the body is under strain, often before anything else does.",
        "patient_help": "Wear your watch overnight.",
    },
    "sleep_duration": {
        "title": "Sleep duration",
        "what": "Hours asleep per night.",
        "inputs": _WEARABLE,
        "how": _VITAL_HOW,
        "reading": "A sustained fall well below the patient's own baseline is the finding.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How long you slept.",
        "patient_why": "Pain that cuts sleep short shows here first.",
        "patient_help": "Wear your watch overnight.",
    },
    "skin_temp": {
        "title": "Skin temperature",
        "what": "Overnight skin temperature.",
        "inputs": "A wearable with a temperature sensor, worn overnight.",
        "how": _VITAL_HOW,
        "reading": "A sustained rise above the patient's own baseline is the finding. "
                   "Guarded: it is phrased as a signal to review, never as a diagnosis.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "Your skin temperature while you sleep.",
        "patient_why": "A rise over a couple of nights is something your team wants to ask about.",
        "patient_help": "Wear your watch overnight.",
    },
    "skin_temp_delta": {
        "title": "Skin temperature change",
        "what": "Apple's overnight wrist-temperature deviation, used in place of absolute skin "
                "temperature on an Apple Watch.",
        "inputs": "Apple Watch, through Apple Health.",
        "how": _VITAL_HOW,
        "reading": "A sustained rise above the patient's own baseline is the finding.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How your overnight wrist temperature compares with your usual.",
        "patient_why": "A rise over a couple of nights is something your team wants to ask about.",
        "patient_help": "Wear your watch overnight.",
    },
    "spo2": {
        "title": "Blood oxygen",
        "what": "Overnight blood-oxygen saturation.",
        "inputs": "A wearable with a blood-oxygen sensor, worn overnight.",
        "how": _VITAL_HOW,
        "reading": "A sustained fall below the patient's own baseline is the finding; device fit "
                   "is the first thing to check.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "The oxygen level in your blood overnight.",
        "patient_why": "It is one of the first things to shift with a chest problem.",
        "patient_help": "Wear your watch snugly overnight.",
    },
    "respiratory_rate": {
        "title": "Respiratory rate",
        "what": "Breaths per minute during sleep.",
        "inputs": _WEARABLE,
        "how": _VITAL_HOW,
        "reading": "A sustained rise is the finding. Guarded phrasing.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How fast you breathe while asleep.",
        "patient_why": "Faster breathing over a few nights goes with a body under strain.",
        "patient_help": "Wear your watch overnight.",
    },
    "walking_speed": {
        "title": "Walking speed",
        "what": "Typical walking speed in metres per second.",
        "inputs": _GUIDED,
        "how": _FUNC_HOW,
        "reading": "The dashed line is the expected speed for today; falling well under it for "
                   "two days is a flag.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How fast you walk.",
        "patient_why": "Pace climbs steadily in a good recovery.",
        "patient_help": "Carry your phone in a front pocket on walks, or do the guided walk.",
    },
    "walking_asymmetry_pct": {
        "title": "Walking asymmetry",
        "what": "The share of walking time spent favouring one leg.",
        "inputs": _GUIDED,
        "how": "Read on absolute bands rather than a baseline, because every patient limps after "
               "a lower-limb operation and improves from there.",
        "reading": "8% or under is improving; above 10% after post-op day 10 is a flag.",
        "shows_after": "The first walk with the phone in a pocket.",
        "patient_what": "How evenly you walk on both legs.",
        "patient_why": "A limp that is still settling is normal; one that stops settling is "
                       "something physio can fix early.",
        "patient_help": "Carry your phone in a front pocket on walks.",
    },
    "step_length": {
        "title": "Step length",
        "what": "The length of each step.",
        "inputs": "The guided walk in the MedPull app; height from the Health app or entered once.",
        "how": _FUNC_HOW,
        "reading": "The dashed line is the expected length for today.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How long your steps are.",
        "patient_why": "Steps lengthen as confidence and strength return.",
        "patient_help": "Do the guided walk with your height entered in the app.",
    },
    "cadence": {
        "title": "Cadence",
        "what": "Steps per minute while walking.",
        "inputs": "The guided walk in the MedPull app.",
        "how": _FUNC_HOW,
        "reading": "The dashed line is the expected cadence for today.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How many steps a minute you take while walking.",
        "patient_why": "Cadence is the part of pace that returns first.",
        "patient_help": "Do the guided walk.",
    },
    "double_support_pct": {
        "title": "Double support",
        "what": "The share of each stride with both feet on the ground.",
        "inputs": _GUIDED,
        "how": "Read on absolute bands: healthy walking sits near 20%, and it rises for everyone "
               "after a lower-limb operation.",
        "reading": "Under 28% is improving; over 40% after post-op day 10 is a flag. Guarded: "
                   "the weakest gait metric from a single pocket sensor.",
        "shows_after": "The first walk with the phone in a pocket.",
        "patient_what": "How much of each stride both feet are on the ground.",
        "patient_why": "It falls as you trust the operated leg more.",
        "patient_help": "Carry your phone in a front pocket on walks.",
    },
    "walking_steadiness": {
        "title": "Walking steadiness",
        "what": "A 0–100 gait-variability index.",
        "inputs": _GUIDED,
        "how": "Read on absolute bands mirroring Apple's three levels.",
        "reading": "60 and above is OK; under 60 low; under 40 very low. Guarded phrasing.",
        "shows_after": "The first walk with the phone in a pocket.",
        "patient_what": "How steady your walking is.",
        "patient_why": "Steadiness is what keeps you safe on your feet.",
        "patient_help": "Carry your phone in a front pocket on walks.",
    },
    "stair_speed_up": {
        "title": "Stair speed up",
        "what": "Vertical speed climbing a flight of stairs.",
        "inputs": "A walk recorded in the app that includes a flight (barometer plus steps); an "
                  "Apple Watch also reports its own estimate.",
        "how": _FUNC_HOW,
        "reading": "The dashed line is the expected speed for today.",
        "shows_after": "The first recorded flight; a 7-day recency window.",
        "patient_what": "How quickly you climb stairs.",
        "patient_why": "Stairs are the milestone most people care about.",
        "patient_help": "Record a walk in the app that includes a flight of stairs.",
    },
    "stair_speed_down": {
        "title": "Stair speed down",
        "what": "Vertical speed descending a flight of stairs.",
        "inputs": "A walk recorded in the app that includes a flight; an Apple Watch also reports "
                  "its own estimate.",
        "how": _FUNC_HOW,
        "reading": "The dashed line is the expected speed for today.",
        "shows_after": "The first recorded flight; a 7-day recency window.",
        "patient_what": "How quickly you come down stairs.",
        "patient_why": "Coming down is the harder half; it is where control returns last.",
        "patient_help": "Record a walk in the app that includes a flight of stairs.",
    },
    "six_min_walk": {
        "title": "Six-minute walk",
        "what": "Distance covered in the six-minute walk test.",
        "inputs": "The six-minute walk test in the MedPull app.",
        "how": _FUNC_HOW,
        "reading": "The dashed line is the expected distance for today; a 14-day recency window.",
        "shows_after": "The first test; two tests to compare.",
        "patient_what": "How far you can walk in six minutes.",
        "patient_why": "It is the standard endurance test used in clinics.",
        "patient_help": "Do the six-minute walk in the app every week or so.",
    },
    "rom_flexion": {
        "title": "Flexion (range of motion)",
        "what": "How far the joint bends, in degrees.",
        "inputs": "The range-of-motion test in the MedPull app (phone inclinometer).",
        "how": _VITAL_HOW.replace("post-op day 2", "the first tests"),
        "reading": "A sustained fall is the finding; a 10-day recency window.",
        "shows_after": "2 tests for a first read, 3 to settle.",
        "patient_what": "How far your joint bends.",
        "patient_why": "Bend is the milestone your surgeon tracks most closely in the first weeks.",
        "patient_help": "Do the range-of-motion test in the app every few days.",
    },
    "rom_extension": {
        "title": "Extension deficit (range of motion)",
        "what": "How far short of straight the joint is, in degrees.",
        "inputs": "The range-of-motion test in the MedPull app.",
        "how": _VITAL_HOW.replace("post-op day 2", "the first tests"),
        "reading": "A sustained rise (more residual bend) is the finding.",
        "shows_after": "2 tests for a first read, 3 to settle.",
        "patient_what": "How close to straight your joint gets.",
        "patient_why": "Getting fully straight matters as much as bending.",
        "patient_help": "Do the range-of-motion test in the app every few days.",
    },
    "rom_abduction": {
        "title": "Abduction (range of motion)",
        "what": "How far the arm lifts sideways, in degrees.",
        "inputs": "The range-of-motion test in the MedPull app.",
        "how": _VITAL_HOW.replace("post-op day 2", "the first tests"),
        "reading": "A sustained fall is the finding.",
        "shows_after": "2 tests for a first read, 3 to settle.",
        "patient_what": "How far you can lift your arm out to the side.",
        "patient_why": "It is the shoulder milestone your team follows.",
        "patient_help": "Do the range-of-motion test in the app every few days.",
    },
    "exercise_session": {
        "title": "Exercise minutes",
        "what": "Minutes of recorded exercise per day.",
        "inputs": "Workouts on the wearable or guided walks in the app.",
        "how": _FUNC_HOW,
        "reading": "The dashed line is the expected minutes for today.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "How many minutes of exercise you logged.",
        "patient_why": "It is the dose your plan is built around.",
        "patient_help": "Record workouts on your watch or walks in the app.",
    },
    "active_energy": {
        "title": "Active energy",
        "what": "Calories burned through movement.",
        "inputs": _WEARABLE,
        "how": _FUNC_HOW,
        "reading": "The dashed line is the expected energy for today.",
        "shows_after": _VITAL_SHOWS,
        "patient_what": "The energy you burn moving.",
        "patient_why": "A second view of activity when steps undercount it (cycling, swimming).",
        "patient_help": "Wear your watch.",
    },
    "calories": {
        "title": "Total calories",
        "what": "Total daily energy, for context.",
        "inputs": _WEARABLE,
        "how": "Charted only; not judged.",
        "reading": "Context only.",
        "shows_after": "The first day of data.",
        "patient_what": "Your total energy for the day.",
        "patient_why": "Context for the activity numbers.",
        "patient_help": "Wear your watch.",
    },
    "stress_index": {
        "title": "Stress index",
        "what": "A 0–100 daily strain index computed by MedPull from the patient's own "
                "overnight autonomic signals, the same way for every device.",
        "inputs": "Overnight HRV, resting heart rate and respiratory rate from the wearable.",
        "how": "Each signal is standardized against the patient's own trailing six weeks (two "
               "prior days at minimum) and the three are combined in the direction that means "
               "strain: 50 is at baseline, 75 one standard deviation of strain, 100 two.",
        "reading": "Above 62.5 is Watch, above 75 Flag — but never a Flag until a week of "
                   "baseline exists, when the card says 'early estimate'. Guarded phrasing.",
        "shows_after": "2 prior days of autonomic data for an early estimate; the band firms up "
                       "after 7.",
        "patient_what": "A single number for how much strain your body was under overnight.",
        "patient_why": "It pulls three signals into one you can watch day to day.",
        "patient_help": "Wear your watch overnight; it starts after two nights.",
    },
}

SECTIONS: dict[str, Explanation] = {
    "trajectory": {
        "title": "Recovery trajectory",
        "what": "The functional index — the patient's activity relative to their own norm — "
                "drawn over the expected recovery band for the procedure.",
        "inputs": "Daily steps (70%) and walking speed (30%), each divided by the patient's "
                  "pre-op norm; without pre-op history, their first post-op days anchor it.",
        "how": "The expected curve is a logistic calibrated per procedure (a knee replacement "
               "recovers slowest early, a meniscus repair fastest). The verdict compares the "
               "last five days' mean to the curve: 12% under is behind, 10% over is ahead. "
               "Without a pre-op norm the index tracks pace, not capacity, and 'ahead' is "
               "withheld.",
        "reading": "Blue line is the patient; the grey band is the expected range; the dashed "
                   "line its middle; an orange marker is a detected change point.",
        "shows_after": "3 days of functional index for a first verdict, 5 to settle.",
        "patient_what": "Your activity against a typical recovery from your operation.",
        "patient_why": "It is the simplest answer to 'am I where I should be?'.",
        "patient_help": "Wear your watch or carry your phone daily.",
    },
    "composite": {
        "title": "Multi-signal deviation",
        "what": "The weighted sum of today's adverse movement across resting heart rate, skin "
                "temperature, HRV, respiratory rate and activity — the pattern that matters is "
                "several moving together.",
        "inputs": "Today's raw z-scores for those five signals against the patient's own baseline; "
                  "a signal that stopped reporting is dropped rather than carried forward.",
        "how": "Only movement in the clinically adverse direction counts (heart rate and "
               "temperature up, HRV and activity down), weighted 25/25/20/15/15 and clipped "
               "at 4σ each.",
        "reading": "Over 1.2 is elevated, over 2.0 high — high is one of the two ways a patient "
                   "reaches the High-risk tier. The bars are each signal's share of the index.",
        "shows_after": "Any two of the signals with a baseline (2 days each).",
        "patient_what": "Whether several of your overnight readings moved the wrong way together.",
        "patient_why": "One reading can wobble; several together is what your team wants to "
                       "know about early.",
        "patient_help": "Wear your watch overnight.",
    },
    "adherence": {
        "title": "Adherence and monitoring",
        "what": "Task completion over the last 14 days.",
        "inputs": "Assigned tasks and their completion records.",
        "how": "Verified completions count in full, self-reports at half weight.",
        "reading": "A filled dot is a verified day, a half dot self-reported, an empty ring missed.",
        "shows_after": "The first assigned task.",
        "patient_what": "How much of your plan you completed each day.",
        "patient_why": "The plan is a dose; your team adjusts it to what you can do.",
        "patient_help": "Tick off tasks in the app, by text or by voice.",
    },
    "confidence": {
        "title": "Data confidence",
        "what": "How clearly the engine can see this patient this week.",
        "inputs": "Which key signals the patient's sources report, on how many of the last 7 "
                  "days.",
        "how": "The lower of the share of days with the patient's key signals and the share of "
               "their panel still reporting; the panel is what their sources have ever "
               "reported, floored at three signals.",
        "reading": "High at 75% and above; moderate from 40%; below 40% the risk tier reads "
                   "Missing data rather than guessing.",
        "shows_after": "Immediately.",
        "patient_what": "How much of your data is reaching your care team.",
        "patient_why": "Everything else rests on it.",
        "patient_help": "Keep your watch charged and worn; open the app so it syncs.",
    },
    "risk_tier": {
        "title": "Risk tier",
        "what": "Who needs attention today: High risk, Needs review, On track, or Missing data.",
        "inputs": "Every flag, drift, the trajectory verdict, the deviation index, adherence and "
                  "data coverage.",
        "how": "Ordered rules. Missing data when confidence is low. High when the deviation "
               "index is high or two signals including heart rate or temperature are flagged. "
               "Needs review for any flag, drift, limp, a vital gone dark, a behind trajectory "
               "or low adherence. On track otherwise. A reading more than five days old never "
               "moves the tier.",
        "reading": "Each reason under the tier is the rule that fired, in words.",
        "shows_after": "Immediately; Missing data until the patient can be seen.",
        "patient_what": "Whether your care team is keeping a closer eye this week.",
        "patient_why": "It decides who they call first.",
        "patient_help": "Keep the data flowing and answer the check-ins.",
    },
}


def glossary() -> dict[str, Any]:
    """The whole payload the console caches once per session."""
    return {"metrics": METRICS, "signals": SIGNALS, "sections": SECTIONS}


def explain_metric(metric_id: str) -> Explanation | None:
    return METRICS.get(metric_id)


def explain_signal(metric_key: str) -> Explanation | None:
    return SIGNALS.get(metric_key)


def patient_explanation(entry: Explanation | None) -> dict[str, str] | None:
    """The three patient-facing lines of an entry, under short keys."""
    if entry is None:
        return None
    return {
        "title": entry.get("title", ""),
        "what": entry.get("patient_what", ""),
        "why": entry.get("patient_why", ""),
        "help": entry.get("patient_help", ""),
    }
