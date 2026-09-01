from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(tags=["ask"])


class AskBody(BaseModel):
    question: str


@router.post("/ask")
def ask_roster(body: AskBody, db: Session = Depends(get_db)) -> dict:
    question = body.question.strip()
    if not (3 <= len(question) <= 300):
        raise HTTPException(status_code=422, detail="Question must be 3-300 characters")

    from app.llm.ask import ask

    return ask(db, question)
