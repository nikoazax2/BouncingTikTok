"""Subprocess export script - runs pygame render in its own process."""
import sys, json, math

params_file = sys.argv[1]
output_file = sys.argv[2]

with open(params_file) as f:
    p = json.load(f)

def hex_to_rgb(h):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

from config import SceneConfig, BallConfig
from renderer import render_scene

speed = float(p.get("speed", 40))
la = float(p.get("launchAngle", 19))
bg = p.get("bgColor", "#0a0a0f")
sc = p.get("shapeColor", "#ffffff")
bc = p.get("ballColor", "#ff6432")

scene = SceneConfig(
    shape=p.get("shape", "circle"),
    shape_color=hex_to_rgb(sc) if isinstance(sc, str) else tuple(sc),
    shape_thickness=int(p.get("thickness", 3)),
    shape_padding=int(p.get("padding", 100)),
    shape_rotation=float(p.get("rotation", 0)),
    bg_color=hex_to_rgb(bg) if isinstance(bg, str) else tuple(bg),
    gravity=float(p.get("gravity", 0.2)),
    nudge=float(p.get("nudge", 0.18)),
    energy_loss=float(p.get("energyLoss", 0)),
    balls=[BallConfig(
        radius=int(p.get("radius", 20)),
        color=hex_to_rgb(bc) if isinstance(bc, str) else tuple(bc),
        speed_x=speed * math.sin(math.radians(la)),
        speed_y=speed * math.cos(math.radians(la)),
        trail_length=int(p.get("trail", 30)),
    )],
    spikes=bool(p.get("spikes", False)),
    growth=bool(p.get("growth", False)),
    use_image=bool(p.get("useImage", False)),
    trail_type=p.get("trailType", "fill"),
    grow_time=int(p.get("growTime", 10)),
    mp3_mode=bool(p.get("mp3Mode", False)),
    selected_channels=p.get("selectedChannels", None),
    mp3_chunk_ms=int(float(p.get("mp3Chunk", 0.2)) * 1000),
    duration=int(p.get("duration", 40)),
    fps=int(p.get("fps", 60)),
    output_file=output_file,
)

import shutil

temp_output = output_file + ".tmp.mp4"
scene.output_file = temp_output
render_scene(scene)
shutil.move(temp_output, output_file)
