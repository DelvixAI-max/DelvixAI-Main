from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# The human reviewer decides whether an act is reportable and which rule it
# breaks. The model's job is only to say whether a clip contains something
# *potentially* reportable and describe what it saw. The category below is
# an optional hint for sorting the reviewer's list, keyed to AFL Law 22.2.2
# sub-clauses as adopted by VAFA (see rules.md) — never a ruling.
OffenceHint = Literal[
    "22.2.2(a)(i) striking",
    "22.2.2(a)(ii) kicking",
    "22.2.2(a)(iii) kneeing",
    "22.2.2(a)(iv) charging",
    "22.2.2(a)(v) rough_conduct",
    "22.2.2(a)(vi) front_on_head_down_bump",
    "22.2.2(a)(vii) head_butt_or_head_contact",
    "22.2.2(a)(viii-ix) eye_or_face_contact",
    "22.2.2(a)(xi) tripping",
    "22.2.2(b-c) eye_gouging_or_stomping",
    "22.2.2(d,i,j) umpire_contact",
    "22.2.2(m) attempting_to_strike",
    "22.2.2(p) contact_with_injured_player",
    "22.2.2(q-r) melee_or_wrestling",
    "22.2.2(bb) other_misconduct",
]

OrdinaryContact = Literal["legal_tackle", "marking_contest", "bump_within_rules", "ball_up_scrimmage", "none"]


class PlayerInvolved(BaseModel):
    jumper_number: int | None = Field(None, description="Jersey number only if clearly legible, else null")
    team_guess: str | None = Field(None, description="'offender', 'victim', or null if unclear")


class OffenceAssessment(BaseModel):
    potentially_reportable: bool
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that a human would want to look at this")
    what_was_seen: str
    possible_category: OffenceHint | None = None
    ordinary_contact_type: OrdinaryContact = "none"
    players_involved: list[PlayerInvolved] = Field(default_factory=list)


# JSON schema handed to Claude as a tool's input_schema, forcing structured output.
OFFENCE_ASSESSMENT_TOOL_SCHEMA = {
    "name": "record_clip_assessment",
    "description": "Record whether a candidate clip contains a potentially reportable act and what was seen.",
    "input_schema": {
        "type": "object",
        "properties": {
            "potentially_reportable": {
                "type": "boolean",
                "description": "True if a human reviewer should look at this clip for a possible reportable act.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "How confident you are that this warrants a human look (0 = clearly ordinary play).",
            },
            "what_was_seen": {
                "type": "string",
                "description": (
                    "Plain description of what is visible: contact point (head/high/body/legs), whether the "
                    "player hit had the ball, front-on or side, strike vs push vs tackle, how many players "
                    "are grappling, whether anyone stays down, umpire involvement."
                ),
            },
            "possible_category": {
                "type": ["string", "null"],
                "enum": list(OffenceHint.__args__) + [None],
                "description": "Optional hint of the closest Law 22.2.2 category. Null if not reportable or unsure.",
            },
            "ordinary_contact_type": {
                "type": "string",
                "enum": list(OrdinaryContact.__args__),
                "description": "If this is ordinary football, which kind of contact it is.",
            },
            "players_involved": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "jumper_number": {"type": ["integer", "null"]},
                        "team_guess": {"type": ["string", "null"], "enum": ["offender", "victim", None]},
                    },
                },
            },
        },
        "required": ["potentially_reportable", "confidence", "what_was_seen"],
    },
}
