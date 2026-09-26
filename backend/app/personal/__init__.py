"""The personal tier: a subscription product on the same app and the same
engine, for a person who is not a hospital's patient.

Everything a clinic patient has — the wearable stream, the engine, tasks,
check-ins, the copilot, texts — a subscriber has too, under their own
profile. What is different is the audience: the console never sees them,
nobody stands behind their messages but the app, and the readouts are the
athlete's, not the clinician's (``metrics.py``). The two are kept apart
structurally (``scope.py``), and a person who is both can hold both rows
and move between them (``identity.py``).
"""
