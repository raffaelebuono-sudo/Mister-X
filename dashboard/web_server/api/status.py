"""REST-Route für System- und JARVIS-Status."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from tools import system_monitor

if TYPE_CHECKING:
    from core import JarvisCore


def build_router(core: "JarvisCore") -> APIRouter:
    router = APIRouter(prefix="/api", tags=["status"])

    @router.get("/status")
    def get_status():
        return {
            "state": core.bus.state_snapshot(),
            "system": system_monitor.get_status(),
        }

    return router
