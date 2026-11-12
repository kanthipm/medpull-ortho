"""Console actions that text a lifter about their exercises
(``app/hep/texts.py`` writes and sends them)."""

from fastapi import APIRouter

router = APIRouter(prefix="/hep", tags=["hep-texts"])
