from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import ConsoleScope, console_scope
from app.api.scope import scoped_clinic_patients
from app.database import get_db

router = APIRouter(tags=["ask"])


class AskBody(BaseModel):
    question: str


@router.post("/ask")
def ask_roster(
    body: AskBody,
    db: Session = Depends(get_db),
    scope: ConsoleScope = Depends(console_scope),
) -> dict:
    question = body.question.strip()
    if not (3 <= len(question) <= 300):
        raise HTTPException(status_code=422, detail="Question must be 3-300 characters")

    from app.llm.ask import ask

    # Staff ask over the whole clinic roster; an org credential over its own,
    # so neither the answer nor the filtered list can name another clinic's
    # patient.
    patients = None if scope.kind == "all" else scoped_clinic_patients(db, scope)
    return ask(db, question, patients=patients)
