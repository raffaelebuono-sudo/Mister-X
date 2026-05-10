"""REST-Routen für Aufgaben."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Body, HTTPException

if TYPE_CHECKING:
    from core import JarvisCore


def build_router(core: "JarvisCore") -> APIRouter:
    router = APIRouter(prefix="/api/tasks", tags=["tasks"])

    @router.get("")
    def list_tasks():
        return {"tasks": core.open_tasks_data()}

    @router.post("")
    def add_task(payload: dict = Body(...)):
        title = (payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="Titel fehlt.")
        due_at = payload.get("due_at") or None
        message = core.add_task(title, due_at)
        return {"message": message}

    @router.post("/{task_id}/complete")
    def complete_task(task_id: int):
        message = core.complete_task(task_id)
        return {"message": message}

    return router
