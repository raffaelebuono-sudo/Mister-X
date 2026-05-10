"""REST-Routen für Chat und Verlauf."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Body, HTTPException

if TYPE_CHECKING:
    from core import JarvisCore


def build_router(core: "JarvisCore") -> APIRouter:
    router = APIRouter(prefix="/api", tags=["chat"])

    @router.get("/history")
    def get_history(limit: int = 50):
        return {"messages": core.chat_history(limit)}

    @router.post("/chat")
    def post_chat(payload: dict = Body(...)):
        text = (payload.get("content") or "").strip()
        speak = bool(payload.get("speak", False))
        if not text:
            raise HTTPException(status_code=400, detail="Leere Nachricht.")
        try:
            reply = core.process_text(text, speak=speak)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"reply": reply}

    return router
