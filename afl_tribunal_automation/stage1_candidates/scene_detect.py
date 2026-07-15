"""Shot-boundary segmentation via PySceneDetect.

Not used to detect incidents directly — used so the scoring pipeline in
`scoring.py` can skip (or down-weight) shots that are almost certainly replay
cutaways rather than live action: very short shots produced by a rapid
sequence of cuts (graphics stings, replay-angle switching) are a decent,
cheap proxy for "this isn't continuous live play". Real replay detection
(slow-motion cadence, the broadcast's on-screen replay bug) is a natural v2
improvement and is out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Shot:
    start_seconds: float
    end_seconds: float

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds


def detect_shots(video_path: str, threshold: float = 27.0) -> list[Shot]:
    """Segment a video into shots using content-aware cut detection."""
    from scenedetect import ContentDetector, SceneManager, open_video

    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))
    scene_manager.detect_scenes(video=video)
    scene_list = scene_manager.get_scene_list()

    return [Shot(start.get_seconds(), end.get_seconds()) for start, end in scene_list]


def likely_live_play_shots(shots: list[Shot], min_shot_seconds: float = 2.0) -> list[Shot]:
    """Filter out shots too short to plausibly be continuous live action."""
    return [shot for shot in shots if shot.duration >= min_shot_seconds]
