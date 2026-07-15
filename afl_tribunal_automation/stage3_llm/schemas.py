from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OffenceCategory = Literal[
    "striking",
    "rough_conduct",
    "charging",
    "tripping",
    "kicking",
    "head_high_or_dangerous_tackle",
    "umpire_contact",
    "misconduct_contrary_to_interests_of_game",
    "not_reportable",
]


class PlayerInvolved(BaseModel):
    jumper_number: int | None = Field(None, description="Jersey number if legible, else null")
    team_guess: str | None = Field(None, description="'offender', 'victim', or null if unclear")


class OffenceAssessment(BaseModel):
    offence_category: OffenceCategory
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    players_involved: list[PlayerInvolved] = Field(default_factory=list)
    needs_human_review: bool = True


# JSON schema handed to Claude as a tool's input_schema, forcing structured output.
OFFENCE_ASSESSMENT_TOOL_SCHEMA = {
    "name": "record_offence_assessment",
    "description": "Record the structured assessment of a candidate AFL incident clip.",
    "input_schema": {
        "type": "object",
        "properties": {
            "offence_category": {
                "type": "string",
                "enum": list(OffenceCategory.__args__),
                "description": "Best-matching reportable-offence category, or 'not_reportable'.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Confidence this is a genuine reportable incident.",
            },
            "rationale": {
                "type": "string",
                "description": "Short, concrete justification grounded in what's visible in the frames.",
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
            "needs_human_review": {
                "type": "boolean",
                "description": "True unless this is clearly benign incidental contact.",
            },
        },
        "required": ["offence_category", "confidence", "rationale", "needs_human_review"],
    },
}
