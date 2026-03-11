"""Configuration for BouncingTikTok video generator."""

from dataclasses import dataclass, field
from typing import Literal

# Video dimensions (TikTok 9:16 format)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 60
DURATION = 40  # seconds

# Colors
BG_COLOR = (10, 10, 15)
TRAIL_FADE_SPEED = 8  # lower = longer trails (alpha decrement per frame)

ShapeType = Literal["rectangle", "circle", "triangle", "hexagon", "pentagon", "star", "diamond"]


@dataclass
class BallConfig:
    radius: int = 20
    color: tuple = (255, 100, 50)
    speed_x: float = 6.0
    speed_y: float = 5.0
    emoji: str | None = None  # If set, renders emoji instead of circle
    emoji_size: int = 48
    trail_length: int = 30  # number of trail positions to keep
    trail_color: tuple | None = None  # None = same as ball color


@dataclass
class SceneConfig:
    shape: ShapeType = "rectangle"
    shape_color: tuple = (255, 255, 255)
    shape_thickness: int = 3
    shape_padding: int = 100  # padding from screen edges
    shape_rotation: float = 0.0  # degrees
    bg_color: tuple = (10, 10, 15)
    gravity: float = 0.0  # 0 = no gravity, positive = downward
    nudge: float = 0.18  # random angle perturbation on bounce (radians)
    energy_loss: float = 0.0  # fraction of speed lost per bounce
    balls: list[BallConfig] = field(default_factory=lambda: [BallConfig()])
    music_file: str | None = None  # path to music file
    sound_on_bounce: bool = True
    bounce_sound_file: str | None = None  # None = generate synthetic sound
    note_sequence: list[int] = field(default_factory=lambda: [
        60, 62, 64, 65, 67, 69, 71, 72  # C major scale MIDI notes
    ])
    spikes: bool = True
    growth: bool = False
    use_image: bool = False
    mp3_mode: bool = False
    selected_channels: list[int] | None = None
    trail_type: str = "fill"
    grow_time: int = 10
    mp3_chunk_ms: int = 200
    duration: int = DURATION
    fps: int = FPS
    output_file: str = "output.mp4"


# Preset configurations
PRESETS = {
    "classic": SceneConfig(
        shape="rectangle",
        balls=[BallConfig(radius=15, color=(255, 80, 40), speed_x=7, speed_y=5, trail_length=25)],
    ),
    "emoji_party": SceneConfig(
        shape="circle",
        balls=[
            BallConfig(emoji="⚽", speed_x=5, speed_y=6, emoji_size=40),
            BallConfig(emoji="🏀", speed_x=-4, speed_y=7, emoji_size=40),
            BallConfig(emoji="🎾", speed_x=6, speed_y=-4, emoji_size=40),
        ],
    ),
    "neon_triangle": SceneConfig(
        shape="triangle",
        shape_color=(0, 255, 200),
        bg_color=(5, 5, 20),
        balls=[
            BallConfig(radius=12, color=(255, 0, 255), speed_x=6, speed_y=4, trail_length=40, trail_color=(255, 0, 150)),
            BallConfig(radius=12, color=(0, 255, 255), speed_x=-5, speed_y=6, trail_length=40, trail_color=(0, 150, 255)),
        ],
    ),
    "hexagon_chaos": SceneConfig(
        shape="hexagon",
        shape_color=(255, 200, 0),
        balls=[
            BallConfig(radius=10, color=(255, 50, 50), speed_x=8, speed_y=3),
            BallConfig(radius=10, color=(50, 255, 50), speed_x=-3, speed_y=8),
            BallConfig(radius=10, color=(50, 50, 255), speed_x=5, speed_y=-6),
            BallConfig(radius=10, color=(255, 255, 50), speed_x=-7, speed_y=-4),
        ],
    ),
    "star_bounce": SceneConfig(
        shape="star",
        shape_color=(255, 215, 0),
        bg_color=(15, 5, 25),
        balls=[
            BallConfig(emoji="🌟", speed_x=5, speed_y=4, emoji_size=36),
            BallConfig(emoji="✨", speed_x=-6, speed_y=5, emoji_size=36),
        ],
    ),
    "diamond_zen": SceneConfig(
        shape="diamond",
        shape_color=(100, 200, 255),
        bg_color=(5, 10, 20),
        gravity=0.15,
        balls=[BallConfig(radius=18, color=(255, 150, 50), speed_x=4, speed_y=0, trail_length=50)],
    ),
}
