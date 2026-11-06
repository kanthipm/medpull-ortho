"""The sports vocabulary, in one place.

Every number the app shows is named here: what a test measures, its unit,
which way is better, how it is measured, and where a given level sits. The
engines (``performance``, ``recovery``, ``rehab``) read these tables; the
app reads them too (``GET /mobile/sports/catalog``) so that labels, units
and protocols are never duplicated in Swift.
"""

from app.sports.catalog.devices import DEVICES, device_view, devices_for
from app.sports.catalog.injuries import (
    INJURIES,
    MEASURES,
    CriterionSpec,
    InjurySpec,
    MeasureSpec,
    PhaseSpec,
    injuries_for,
    injury_view,
    measure_view,
)
from app.sports.catalog.tests import (
    CATEGORIES,
    TESTS,
    TestSpec,
    band_for,
    benchmark_for,
    test_view,
    tests_for,
)
from app.sports.catalog.wellness import WELLNESS, WellnessSpec, wellness_view

__all__ = [
    "CATEGORIES", "DEVICES", "INJURIES", "MEASURES", "TESTS", "WELLNESS",
    "CriterionSpec", "InjurySpec", "MeasureSpec", "PhaseSpec", "TestSpec", "WellnessSpec",
    "band_for", "benchmark_for", "device_view", "devices_for", "injuries_for", "injury_view",
    "measure_view", "test_view", "tests_for", "wellness_view",
]
