# stat Response 스키마
from __future__ import annotations

from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, ConfigDict


class UserStatsResponse(BaseModel):
    stats: dict[str, int]
    source_type: str
    steam_linked: bool
    last_updated_at: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "stats": {
                    "combat": 80,
                    "strategy": 50,
                    "cooperation": 60,
                    "exploration": 70,
                    "growth": 60,
                    "healing": 35,
                },
                "source_type": "HYBRID_STEAM",
                "steam_linked": True,
                "last_updated_at": "2026-06-05T12:30:00+09:00",
            }
        }
    )
