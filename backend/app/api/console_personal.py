"""The console's Personal version: the demo members' spaces, read-only.

Every route answers 404 unless ``DEMO_MODE`` is on, the console is staff
scope, and the row is a generated member (``app/personal/showcase.py``). A
real subscriber's space is never listed or opened here.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/console/personal", tags=["console-personal"])
