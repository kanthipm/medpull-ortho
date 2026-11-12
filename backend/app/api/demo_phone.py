"""Binding a real phone number to a demo persona, so the texts the demo
sends reach the presenter's own phone. Demo stack only (404 elsewhere);
authorised by the persona's app session, not the console credential."""

from fastapi import APIRouter

router = APIRouter(prefix="/demo", tags=["demo"])
