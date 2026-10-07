"""The glossary behind every "i" icon: one static payload, cached by the
console for the session and read by the patient app per metric."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.engine.explain import METRICS, SECTIONS, SIGNALS, glossary

router = APIRouter(tags=["explain"])


@router.get("/explain")
def explain_all() -> JSONResponse:
    # Static for the life of a deploy; a day of browser caching costs nothing
    # and saves a fetch per page view.
    return JSONResponse(glossary(), headers={"Cache-Control": "public, max-age=86400"})


@router.get("/explain/{kind}/{key}")
def explain_one(kind: str, key: str) -> dict:
    table = {"metrics": METRICS, "signals": SIGNALS, "sections": SECTIONS}.get(kind)
    if table is None or key not in table:
        raise HTTPException(status_code=404, detail=f"No explanation for {kind}/{key}")
    return {"kind": kind, "key": key, **table[key]}
