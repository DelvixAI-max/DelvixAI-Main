# AFL Reportable Offence Categories — Reference Summary

This is a simplified working reference for triage purposes, not the official
AFL Match Review Officer (MRO) guidelines document — a human at the league
must always confirm the actual charge and grading. It exists so Claude has a
consistent vocabulary of offence categories and severity factors to reason
against when assessing a candidate clip.

## Offence categories

- **Striking** — any strike with the arm/hand/fist to an opponent.
- **Rough Conduct** — forceful contact (bump, hip-and-shoulder, tackle-adjacent
  contact) deemed unreasonable in the circumstances.
- **Charging** — forceful contact where the primary infringement is a
  failure to give a reasonable opportunity to dispose of the ball, or a
  head-down/blind-side collision.
- **Tripping** — using the leg/foot (or hand to the leg) to trip an opponent.
- **Kicking** — any kicking motion directed at another player.
- **Head-High / Dangerous Tackle** — a tackle or bump that makes forceful
  contact with the head/neck, including driving an opponent into the ground.
- **Umpire Contact** — any contact, intentional or careless, with a field
  umpire, boundary umpire, or goal umpire.
- **Misconduct / Contrary to the Interests of the Game** — behaviour that
  doesn't fit a specific physical-contact category but is still reportable
  (e.g. eye-gouging, biting, racial or homophobic vilification, spitting).

## Grading factors (for context, not for Claude to formally adjudicate)

Each offence is ultimately graded on:

- **Impact**: Low / Medium / High / Severe — outcome for the victim.
- **Contact**: Low / High — level of contact.
- **Conduct**: Intentional / Reckless / Negligent — the offender's intent.

## What we want from the model (per clip)

Given a short sequence of frames from a candidate clip, classify:

1. Whether this looks like it contains a reportable act, and if so which
   category above it most resembles.
2. A short rationale grounded in what's visible (player movement, contact
   point, apparent forcefulness) — not a legal ruling.
3. Which players appear to be involved, if jersey numbers are legible.
4. Whether this needs a human reviewer's eyes regardless of confidence
   (default to `true` whenever contact is head-high, whenever there's any
   doubt, or when players/jerseys aren't clearly identifiable).

Err generously toward `needs_human_review: true` — this tool is a triage
aid for the league's review officer, not a replacement for their judgement.
