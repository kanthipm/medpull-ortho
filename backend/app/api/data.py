"""The console's Data tab: every stored reading, what was computed from it,
and where it came from, across a roster and for one chart.

Read-only. Roster reads go through ``scoped_clinic_patients``; a chart's
reads through ``require_patient`` and are clinic charts only. No route here
recomputes or commits: a GET that commits re-uploads the database on AWS.
"""

from fastapi import APIRouter

router = APIRouter(tags=["data"])
