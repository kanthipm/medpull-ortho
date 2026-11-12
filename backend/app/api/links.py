"""Opening a texted link: what it points at, and (on the demo stack) the
app session it may start. No console credential and no app session: the
token in the path is the credential, as with ``/api/tasks/{token}``.
Minting and the kinds a link can name are in ``app/links.py``.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/links", tags=["links"])
