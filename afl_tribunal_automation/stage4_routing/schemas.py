"""Payload shape for an inbound umpire report. Field names are a reasonable
guess at what an umpiring platform's export/webhook would send — adjust to
match the real platform's schema once known; this is the one place that
would need to change."""

from __future__ import annotations

from pydantic import BaseModel


class IncomingUmpireReport(BaseModel):
    game_id: int
    reporting_umpire: str = ""
    offender_jumper_number: int
    offender_team: str
    victim_jumper_number: int
    victim_team: str
    incident_type: str
    expected_damage: str = ""
    ground_zone: str = ""
    quarter: int
    game_clock_seconds: int
