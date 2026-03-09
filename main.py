"""BouncingTikTok - Generate satisfying bouncing ball videos for TikTok.

Usage:
    python main.py                          # Use default "classic" preset
    python main.py --preset neon_triangle   # Use a named preset
    python main.py --preview                # Show real-time preview
    python main.py --gui                    # Launch interactive GUI
    python main.py --list-presets           # List available presets

Custom options:
    python main.py --shape hexagon --balls 3 --emoji "⚽🏀🎾" --gravity 0.1 --duration 30
"""

import argparse
import sys
from config import SceneConfig, BallConfig, PRESETS, VIDEO_WIDTH, VIDEO_HEIGHT
from renderer import render_scene


def parse_args():
    parser = argparse.ArgumentParser(
        description="BouncingTikTok - Satisfying bouncing ball video generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Presets: classic, emoji_party, neon_triangle, hexagon_chaos, star_bounce, diamond_zen

Examples:
  python main.py --preset emoji_party
  python main.py --shape circle --balls 2 --emoji "🔥💧"
  python main.py --shape star --gravity 0.2 --duration 30 --preview
        """
    )

    parser.add_argument("--preset", type=str, default=None, help="Use a named preset configuration")
    parser.add_argument("--list-presets", action="store_true", help="List all available presets")
    parser.add_argument("--preview", action="store_true", help="Show real-time preview while rendering")
    parser.add_argument("--gui", action="store_true", help="Launch interactive parameter GUI")

    # Shape options
    parser.add_argument("--shape", type=str, default="rectangle",
                        choices=["rectangle", "circle", "triangle", "hexagon", "pentagon", "star", "diamond"])
    parser.add_argument("--shape-color", type=str, default="255,255,255", help="Shape border color (R,G,B)")
    parser.add_argument("--shape-thickness", type=int, default=3)
    parser.add_argument("--shape-padding", type=int, default=100)
    parser.add_argument("--shape-rotation", type=float, default=0.0, help="Shape rotation in degrees")

    # Ball options
    parser.add_argument("--balls", type=int, default=1, help="Number of balls")
    parser.add_argument("--ball-radius", type=int, default=20)
    parser.add_argument("--ball-color", type=str, default="255,100,50", help="Ball color (R,G,B)")
    parser.add_argument("--emoji", type=str, default=None, help="Emoji(s) to use for balls (one per ball)")
    parser.add_argument("--emoji-size", type=int, default=48)
    parser.add_argument("--trail-length", type=int, default=30)
    parser.add_argument("--speed", type=float, default=6.0, help="Base ball speed")

    # Scene options
    parser.add_argument("--bg-color", type=str, default="10,10,15", help="Background color (R,G,B)")
    parser.add_argument("--gravity", type=float, default=0.0)
    parser.add_argument("--duration", type=int, default=40, help="Video duration in seconds")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--music", type=str, default=None, help="Path to background music file")
    parser.add_argument("--no-spikes", action="store_true", help="Disable spikes around the circle")
    parser.add_argument("--output", "-o", type=str, default="output.mp4", help="Output file path")

    return parser.parse_args()


def parse_color(color_str: str) -> tuple:
    parts = [int(x.strip()) for x in color_str.split(",")]
    return tuple(parts[:3])


def segment_emojis(emoji_str: str) -> list[str]:
    """Split a string of emojis into individual emoji characters."""
    import unicodedata
    emojis = []
    current = ""
    for char in emoji_str:
        cat = unicodedata.category(char)
        if cat.startswith("So") or cat.startswith("Cn") or ord(char) > 0x1F000:
            if current:
                emojis.append(current)
            current = char
        elif char == '\ufe0f' or char == '\u200d':
            current += char
        elif current:
            current += char
        else:
            current = char
    if current:
        emojis.append(current)
    return emojis


def build_scene_from_args(args) -> SceneConfig:
    """Build a SceneConfig from command-line arguments."""
    # Parse emojis if provided
    emojis = []
    if args.emoji:
        emojis = segment_emojis(args.emoji)

    ball_color = parse_color(args.ball_color)
    # Generate varied colors for multiple balls
    import colorsys
    base_hue = 0.05  # orange-ish

    balls = []
    for i in range(args.balls):
        hue = (base_hue + i * 0.15) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
        color = (int(r * 255), int(g * 255), int(b * 255)) if args.balls > 1 else ball_color

        # Vary speed direction for each ball
        import math
        angle = math.pi / 4 + i * math.pi / args.balls
        speed = args.speed + i * 0.5
        sx = speed * math.cos(angle) * (1 if i % 2 == 0 else -1)
        sy = speed * math.sin(angle) * (1 if i % 3 != 0 else -1)

        emoji = emojis[i % len(emojis)] if emojis else None

        balls.append(BallConfig(
            radius=args.ball_radius,
            color=color,
            speed_x=sx,
            speed_y=sy,
            emoji=emoji,
            emoji_size=args.emoji_size,
            trail_length=args.trail_length,
        ))

    return SceneConfig(
        shape=args.shape,
        shape_color=parse_color(args.shape_color),
        shape_thickness=args.shape_thickness,
        shape_padding=args.shape_padding,
        shape_rotation=args.shape_rotation,
        bg_color=parse_color(args.bg_color),
        gravity=args.gravity,
        balls=balls,
        music_file=args.music,
        spikes=not args.no_spikes,
        duration=args.duration,
        fps=args.fps,
        output_file=args.output,
    )


def list_presets():
    print("Available presets:\n")
    for name, cfg in PRESETS.items():
        ball_desc = []
        for b in cfg.balls:
            if b.emoji:
                ball_desc.append(b.emoji)
            else:
                ball_desc.append(f"({b.color[0]},{b.color[1]},{b.color[2]})")
        balls_str = ", ".join(ball_desc)
        grav = f", gravity={cfg.gravity}" if cfg.gravity else ""
        print(f"  {name:20s} | shape={cfg.shape:10s} | balls: {balls_str}{grav}")


def main():
    args = parse_args()

    if args.list_presets:
        list_presets()
        return

    if args.gui:
        from gui import launch_gui
        launch_gui()
        return

    # Build scene
    if args.preset:
        if args.preset not in PRESETS:
            print(f"Unknown preset: {args.preset}")
            print(f"Available: {', '.join(PRESETS.keys())}")
            sys.exit(1)
        scene = PRESETS[args.preset]
        scene.output_file = args.output
        scene.duration = args.duration
        scene.fps = args.fps
        if args.music:
            scene.music_file = args.music
    else:
        scene = build_scene_from_args(args)

    # Summary
    print("=" * 50)
    print("BouncingTikTok Video Generator")
    print("=" * 50)
    print(f"  Shape:    {scene.shape}")
    print(f"  Balls:    {len(scene.balls)}")
    for i, b in enumerate(scene.balls):
        label = b.emoji if b.emoji else f"color={b.color}"
        print(f"    #{i}: {label} speed=({b.speed_x:.1f}, {b.speed_y:.1f})")
    print(f"  Gravity:  {scene.gravity}")
    print(f"  Duration: {scene.duration}s @ {scene.fps}fps")
    print(f"  Output:   {scene.output_file}")
    print("=" * 50)

    render_scene(scene, preview=args.preview)


if __name__ == "__main__":
    main()
