"""Push a finished clip + umpire report straight to the tribunal team.

Both notification channels are best-effort webhooks — swap in whatever the
tribunal system actually exposes (a real API, an email gateway, etc) behind
the same function signature."""

from __future__ import annotations

import requests

from config import settings
from db.models import Clip, UmpireReport


def send_clip_to_tribunal(report: UmpireReport, clip: Clip) -> None:
    payload = {
        "game_id": report.game_id,
        "quarter": report.quarter,
        "game_clock_seconds": report.game_clock_seconds,
        "offender_jumper_number": report.offender_jumper_number,
        "offender_team": report.offender_team,
        "victim_jumper_number": report.victim_jumper_number,
        "victim_team": report.victim_team,
        "incident_type": report.incident_type,
        "expected_damage": report.expected_damage,
        "ground_zone": report.ground_zone,
        "clip_url": clip.url,
    }

    if settings.tribunal_webhook_url:
        response = requests.post(settings.tribunal_webhook_url, json=payload, timeout=15)
        response.raise_for_status()

    if settings.tribunal_slack_webhook_url:
        text = (
            f":rotating_light: Reported offence — {report.offender_team} #{report.offender_jumper_number} "
            f"on {report.victim_team} #{report.victim_jumper_number} ({report.incident_type}), "
            f"Q{report.quarter}. Clip: {clip.url}"
        )
        requests.post(settings.tribunal_slack_webhook_url, json={"text": text}, timeout=15)
