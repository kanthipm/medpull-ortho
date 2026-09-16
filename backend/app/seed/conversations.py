"""Recovery check-in transcripts, matched to each patient's seeded scenario.

Shape: patient_id -> list of check-ins, oldest first. Each check-in is
(days_ago, hour, [(who, text), ...]). The engine never parses these — they are
LLM context and provider-facing history, in the patient's own words.
"""

C = "copilot"
P = "patient"

CONVERSATIONS: dict[str, list[tuple[int, int, list[tuple[str, str]]]]] = {
    "marcus": [
        (3, 8, [
            (C, "Good morning, Marcus. How are you feeling today?"),
            (P, "Not bad. The knee is sore but I got my exercises in yesterday."),
            (C, "Good to hear you kept up with the exercises. Is the soreness better, worse, or about the same as yesterday?"),
            (P, "About the same. Maybe a little more swollen in the evening."),
            (C, "That can happen after activity. Are you icing and elevating after your exercise sessions?"),
            (P, "Yes, twenty minutes like they showed me."),
        ]),
        (1, 8, [
            (C, "Morning, Marcus. How did you sleep, and how is the knee today?"),
            (P, "Rough night. The pain woke me up a couple of times."),
            (C, "I'm sorry to hear that. On a scale from mild to severe, how would you describe the pain right now?"),
            (P, "Worse than the weekend. The pills don't seem to be doing as much."),
            (C, "Has the pain been increasing gradually or did it change suddenly?"),
            (P, "It's been creeping up the last few days."),
            (C, "Thank you. Any new swelling, warmth, or redness around the incision?"),
            (P, "It does feel warm, and it looks puffier than before."),
        ]),
        (0, 8, [
            (C, "Good morning, Marcus. Checking in on the knee — how are you feeling?"),
            (P, "Honestly, worse. My pain has gotten worse and I felt feverish last night."),
            (C, "I'm sorry you're feeling worse. Did you take your temperature?"),
            (P, "I didn't have a thermometer handy, but I was sweating and had chills."),
            (C, "Understood. Is the knee still warm and swollen today?"),
            (P, "Yes, it's warm to the touch and pretty swollen."),
            (C, "Thank you for telling me. Your care team will see this today. If you develop severe pain, spreading redness, or a temperature over 101°F, call the clinic right away."),
            (P, "Okay, I will."),
        ]),
    ],
    "linda": [
        (4, 9, [
            (C, "Hi Linda, how is the shoulder feeling today?"),
            (P, "Stiff in the mornings, but the sling is manageable."),
            (C, "Are you doing the pendulum exercises from your sheet?"),
            (P, "Most days. They pull a little but nothing sharp."),
        ]),
        (1, 9, [
            (C, "Good morning, Linda. How did you sleep?"),
            (P, "Badly again. I can't find a position that doesn't bother the shoulder."),
            (C, "That's common after rotator cuff repair, but several rough nights in a row matter. How many hours are you getting, roughly?"),
            (P, "Maybe five, five and a half. I keep waking up when I roll over."),
            (C, "Thank you. Is the pain itself getting worse, or is it mostly the sleeping position?"),
            (P, "Mostly position. During the day it's okay."),
        ]),
        (0, 9, [
            (C, "Hi Linda, quick check-in. How was last night?"),
            (P, "Same story — kept waking up. I'm tired all day now."),
            (C, "I hear you. I'll flag the sleep disruption for your care team; a wedge pillow setup can sometimes help. Any new symptoms otherwise?"),
            (P, "No, nothing new."),
        ]),
    ],
    "robert": [
        (3, 10, [
            (C, "Good morning, Robert. How is your back today?"),
            (P, "A bit stiff. I did a short walk yesterday but it tired me out."),
            (C, "Short and frequent beats long and exhausting at this stage. Any numbness or tingling in your legs?"),
            (P, "No, none of that."),
        ]),
        (0, 10, [
            (C, "Hi Robert, checking in. How are the walks going?"),
            (P, "Honestly I've been doing a little less each day. I get tired quickly and sit back down."),
            (C, "Thanks for being straight about that. Is anything specific stopping you — pain, dizziness, motivation?"),
            (P, "Not pain exactly. Just worn out."),
            (C, "Understood. I'll note the activity dip for your care team so they can adjust your plan."),
        ]),
    ],
    "sofia": [
        (5, 18, [
            (C, "Hi Sofia, how is the ankle treating you?"),
            (P, "It's okay. I'm still careful on stairs but getting around the house fine."),
            (C, "Are you managing the boot and weight-bearing as instructed?"),
            (P, "Yes, following the plan."),
        ]),
        (1, 18, [
            (C, "Evening check-in, Sofia. How was your day on the ankle?"),
            (P, "Alright, though I feel like my progress has stalled. I'm not walking much farther than last week."),
            (C, "That's useful to know. Any new pain or swelling that's holding you back?"),
            (P, "A little ache by the end of the day, nothing dramatic."),
            (C, "Thanks — I'll pass along that your distance has plateaued so your PT can review your progression."),
        ]),
    ],
    "aisha": [
        (4, 9, [
            (C, "Good morning, Aisha. How is the hip feeling this week?"),
            (P, "The pain is much better than the first week, thank goodness."),
            (C, "That's good progress. How far are you walking these days?"),
            (P, "To the corner and back, once or twice a day. It hasn't really grown in a while."),
        ]),
        (1, 9, [
            (C, "Hi Aisha, checking in. How are the walks going?"),
            (P, "About the same as last week. I still favor the new hip — my daughter says I limp."),
            (C, "Thank you for sharing that. Does the limp get worse when you're tired?"),
            (P, "Yes, by evening I lean on the rail a lot more."),
            (C, "Noted. Your care team will review whether your exercise plan needs adjusting."),
        ]),
    ],
    "priya": [
        (6, 9, [
            (C, "Good morning, Priya. How is your recovery going?"),
            (P, "Fine, I think. I keep forgetting to wear the watch you gave me."),
            (C, "No problem — wearing it during the day helps your care team see how you're moving. How is the hip?"),
            (P, "Sore but improving."),
        ]),
        (2, 9, [
            (C, "Hi Priya, we haven't received much data from your watch lately. Are you wearing it?"),
            (P, "It was on the charger for a few days, sorry. I'll put it back on."),
            (C, "Thank you. And how are you feeling overall?"),
            (P, "Okay. Walking a little every day."),
        ]),
    ],
    "grace": [
        (1, 10, [
            (C, "Good morning, Grace. You're two days out from surgery — how are you feeling?"),
            (P, "Sore and slow, but I expected that. I stood up with the walker twice yesterday."),
            (C, "That's exactly right for day two. Is the pain manageable with your medication schedule?"),
            (P, "Yes, as long as I don't miss a dose."),
        ]),
        (0, 10, [
            (C, "Hi Grace, day three check-in. How was your night?"),
            (P, "Not bad. I walked to the bathroom without help this morning."),
            (C, "Great milestone. Any dizziness, calf pain, or shortness of breath?"),
            (P, "No, none of that."),
            (C, "Perfect. Keep the ankle pumps going through the day."),
        ]),
    ],
    "david": [
        (7, 17, [
            (C, "Hey David, how's the knee holding up in PT?"),
            (P, "Really good. Quad sets and heel slides are easy now, started balance work."),
            (C, "Nice progression. Any swelling after sessions?"),
            (P, "Barely any. Ice takes care of it."),
        ]),
        (1, 17, [
            (C, "Hi David, weekly check-in. How's training going?"),
            (P, "Feeling strong. Walking normally, and PT says my range is ahead of schedule."),
            (C, "Excellent. Remember not to test-run it on your own — clearance comes from the surgeon."),
            (P, "Yeah yeah, I know. Patience."),
        ]),
    ],
    "james": [
        (5, 8, [
            (C, "Good morning, James. Six weeks in — how is the knee?"),
            (P, "Honestly better than I hoped. I walk the dog a mile most mornings."),
            (C, "That's wonderful. Any stiffness after sitting?"),
            (P, "A little when I first stand, then it loosens right up."),
        ]),
        (0, 8, [
            (C, "Hi James, routine check-in. Anything new to report?"),
            (P, "Nothing new. Feeling steadier on stairs this week."),
            (C, "Great to hear. Keep up the daily walking."),
        ]),
    ],
    "elena": [
        (4, 12, [
            (C, "Hi Elena, how is the knee after the meniscus repair?"),
            (P, "Pretty good! Swelling is nearly gone and I'm off the crutches."),
            (C, "Nice. Any catching or locking sensations?"),
            (P, "No, it feels smooth."),
        ]),
        (0, 12, [
            (C, "Morning, Elena. Quick check-in — how are you feeling?"),
            (P, "Great, honestly. Did a full day at work without thinking about it."),
            (C, "That's the goal. Stick with the strengthening plan through week six."),
        ]),
    ],
}
