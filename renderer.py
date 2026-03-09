"""Main rendering engine - simulates and renders bouncing balls."""

import math
import os
import sys
import random
import pygame
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import VIDEO_WIDTH, VIDEO_HEIGHT, SceneConfig, BallConfig, TRAIL_FADE_SPEED
from shapes import get_shape_vertices, draw_shape, closest_edge_collision, point_in_polygon
from sounds import create_bounce_soundtrack, EVENT_MUSIC, EVENT_DEATH


class Spike:
    """Triangular spike attached to the inner circle border, pointing inward."""
    def __init__(self, angle: float, cx: float, cy: float, circle_r: float,
                 spike_length: float = 60, spike_width: float = 30,
                 color: tuple = (255, 50, 50)):
        self.angle = angle
        self.cx = cx
        self.cy = cy
        self.circle_r = circle_r
        self.spike_length = spike_length
        self.spike_width = spike_width
        self.color = color
        self.alive = True

        # Base points on the circle border
        half_w = spike_width / 2
        perp_angle = angle + math.pi / 2
        base_x = cx + circle_r * math.cos(angle)
        base_y = cy + circle_r * math.sin(angle)
        self.base1 = (base_x + half_w * math.cos(perp_angle),
                      base_y + half_w * math.sin(perp_angle))
        self.base2 = (base_x - half_w * math.cos(perp_angle),
                      base_y - half_w * math.sin(perp_angle))
        # Tip points inward
        self.tip_x = cx + (circle_r - spike_length) * math.cos(angle)
        self.tip_y = cy + (circle_r - spike_length) * math.sin(angle)
        self.vertices = [self.base1, self.base2, (self.tip_x, self.tip_y)]

        # Collision hitbox: circle around the tip
        self.hit_radius = spike_width * 0.45

    def draw(self, surface: pygame.Surface):
        int_verts = [(int(v[0]), int(v[1])) for v in self.vertices]
        pygame.draw.polygon(surface, self.color, int_verts)
        # Darker inner triangle
        inner_scale = 0.6
        mid_base_x = (self.base1[0] + self.base2[0]) / 2
        mid_base_y = (self.base1[1] + self.base2[1]) / 2
        inner_verts = [
            (int(mid_base_x + (self.base1[0] - mid_base_x) * inner_scale),
             int(mid_base_y + (self.base1[1] - mid_base_y) * inner_scale)),
            (int(mid_base_x + (self.base2[0] - mid_base_x) * inner_scale),
             int(mid_base_y + (self.base2[1] - mid_base_y) * inner_scale)),
            (int(mid_base_x + (self.tip_x - mid_base_x) * inner_scale),
             int(mid_base_y + (self.tip_y - mid_base_y) * inner_scale)),
        ]
        dark_color = (max(0, self.color[0] - 120), max(0, self.color[1] - 40), max(0, self.color[2] - 40))
        pygame.draw.polygon(surface, dark_color, inner_verts)


class DeadBall:
    """A ball that died on a spike - stays stuck there, becomes a bouncing wall."""
    def __init__(self, x: float, y: float, radius: float, color: tuple):
        self.x = x
        self.y = y
        self.radius = radius
        self.color = color
        self.flash_timer = 15

    def draw(self, surface: pygame.Surface):
        if self.flash_timer > 0:
            alpha = min(255, self.flash_timer * 17)
            sz = self.radius * 4
            flash_surf = pygame.Surface((sz, sz), pygame.SRCALPHA)
            pygame.draw.circle(flash_surf, (255, 255, 255, alpha),
                               (int(sz // 2), int(sz // 2)), int(sz // 2))
            surface.blit(flash_surf, (int(self.x - sz // 2), int(self.y - sz // 2)))
            self.flash_timer -= 1

        pygame.draw.circle(surface, (120, 120, 120), (int(self.x), int(self.y)), self.radius)


def generate_spikes(cx: float, cy: float, circle_r: float,
                    num_spikes: int = 20, spike_length: float = 65,
                    spike_width: float = 28) -> list[Spike]:
    """Place spikes evenly around the inner border of the circle, pointing inward."""
    spikes = []
    colors = [(255, 50, 50), (255, 80, 30), (255, 40, 70), (220, 50, 50)]
    for i in range(num_spikes):
        angle = 2 * math.pi * i / num_spikes - math.pi / 2
        spikes.append(Spike(angle, cx, cy, circle_r, spike_length, spike_width, colors[i % len(colors)]))
    return spikes


def check_circle_collision(bx, by, b_radius, bvx, bvy, ox, oy, o_radius):
    """Check collision between ball and a circular object."""
    dx = bx - ox
    dy = by - oy
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < b_radius + o_radius and dist > 0:
        nx = dx / dist
        ny = dy / dist
        vel_dot = bvx * nx + bvy * ny
        if vel_dot < 0:
            new_vx = bvx - 2 * vel_dot * nx
            new_vy = bvy - 2 * vel_dot * ny
            return new_vx, new_vy, True
    return bvx, bvy, False


def circle_intersects_triangle(cx, cy, radius, triangle):
    """Check if a circle (cx, cy, radius) intersects a triangle (list of 3 vertices)."""
    # 1) Check if center is inside triangle
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1 = sign((cx, cy), triangle[0], triangle[1])
    d2 = sign((cx, cy), triangle[1], triangle[2])
    d3 = sign((cx, cy), triangle[2], triangle[0])
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    if not (has_neg and has_pos):
        return True
    # 2) Check distance from center to each edge
    for i in range(3):
        ax, ay = triangle[i]
        bx, by = triangle[(i + 1) % 3]
        ex, ey = bx - ax, by - ay
        edge_len_sq = ex * ex + ey * ey
        if edge_len_sq == 0:
            continue
        t = max(0, min(1, ((cx - ax) * ex + (cy - ay) * ey) / edge_len_sq))
        closest_x = ax + t * ex
        closest_y = ay + t * ey
        dx = cx - closest_x
        dy = cy - closest_y
        if dx * dx + dy * dy < radius * radius:
            return True
    return False


class Ball:
    def __init__(self, cfg: BallConfig, index: int):
        self.cfg = cfg
        self.index = index
        self.x = VIDEO_WIDTH / 2.0
        self.y = VIDEO_HEIGHT / 2.0
        # Initial launch: straight down, 1° offset to the right
        speed = math.sqrt(cfg.speed_x ** 2 + cfg.speed_y ** 2)
        self.vx = speed * math.sin(math.radians(19))   # tiny rightward
        self.vy = speed * math.cos(math.radians(19))   # almost full speed downward
        self.base_radius = cfg.radius
        self.radius = 5  # start small
        self.grow_speed = 0  # set externally if needed
        self.grow_frame = None  # for exponential growth
        self.grow_total = 0
        self.grow_start = 5
        self.trail: list[tuple[float, float]] = []
        self.max_trail = 120  # 0 = infinite
        self.emoji_surface = None
        self.image_surface = None  # loaded from ball.png
        self.angle = 0.0  # current rotation angle in degrees
        self.alive = True
        self.spawn_timer = 0

    def respawn(self):
        self.x = VIDEO_WIDTH / 2.0
        self.y = VIDEO_HEIGHT / 2.0
        speed = math.sqrt(self.cfg.speed_x ** 2 + self.cfg.speed_y ** 2)
        self.vx = speed * math.sin(math.radians(19))
        self.vy = speed * math.cos(math.radians(19))
        self.trail.clear()
        self.alive = True
        self.spawn_timer = 20

    def init_image(self, image_path: str):
        """Load ball.png as the ball sprite."""
        if os.path.exists(image_path):
            raw = pygame.image.load(image_path)
            self.image_surface = raw.convert_alpha() if pygame.display.get_surface() else raw

    def init_emoji_surface(self):
        if self.cfg.emoji:
            size = self.cfg.emoji_size
            img = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("seguiemj.ttf", size)
            except (OSError, IOError):
                try:
                    font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", size)
                except (OSError, IOError):
                    font = ImageFont.load_default()
            draw.text((size // 2, size // 4), self.cfg.emoji, font=font, embedded_color=True)
            raw = img.tobytes()
            self.emoji_surface = pygame.image.fromstring(raw, img.size, "RGBA")
            self.radius = size // 2

    def update(self, gravity: float, vertices: list[tuple[float, float]],
               spikes: list[Spike], dead_balls: list[DeadBall],
               has_spikes: bool = True
               ) -> tuple[str | None, Spike | None]:
        if not self.alive:
            return None, None

        if self.spawn_timer > 0:
            self.spawn_timer -= 1

        self.vy += gravity

        if self.grow_speed > 0 and self.radius < self.base_radius:
            # grow_speed used as frame counter for exponential growth
            self.radius = min(self.base_radius, self.radius + self.grow_speed)
        elif self.grow_frame is not None:
            # Exponential growth: slow at start, fast at end
            t = self.grow_frame / self.grow_total if self.grow_total > 0 else 1.0
            self.radius = int(self.grow_start + (self.base_radius - self.grow_start) * (t ** 3))
            self.grow_frame += 1

        self.trail.append((self.x, self.y))
        if self.max_trail > 0 and len(self.trail) > self.max_trail:
            self.trail.pop(0)

        self.x += self.vx
        self.y += self.vy

        # 1) Check collision with circle border → MUSIC
        new_vx, new_vy, wall_hit = closest_edge_collision(
            self.x, self.y, self.radius, self.vx, self.vy, vertices
        )
        if wall_hit:
            # Preserve speed + add random angle perturbation to prevent rolling
            old_speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
            angle = math.atan2(new_vy, new_vx)
            angle += random.uniform(-0.3, 0.3)  # ~±17° random nudge
            self.vx = old_speed * math.cos(angle)
            self.vy = old_speed * math.sin(angle)
            self.x += self.vx * 0.5
            self.y += self.vy * 0.5
            return EVENT_MUSIC, None

        # 2) Check collision with dead balls → MUSIC (they act as walls)
        for db in dead_balls:
            new_vx, new_vy, hit = check_circle_collision(
                self.x, self.y, self.radius, self.vx, self.vy,
                db.x, db.y, db.radius
            )
            if hit:
                self.vx = new_vx
                self.vy = new_vy
                dx = self.x - db.x
                dy = self.y - db.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > 0:
                    overlap = (self.radius + db.radius) - dist
                    self.x += (dx / dist) * overlap * 0.6
                    self.y += (dy / dist) * overlap * 0.6
                return EVENT_MUSIC, None

        # 3) Check collision with spike tips → DEATH
        if self.spawn_timer <= 0:
            for spike in spikes:
                if circle_intersects_triangle(self.x, self.y, self.radius, spike.vertices):
                    self.alive = False
                    return EVENT_DEATH, spike

        # Fallback
        if not point_in_polygon(self.x, self.y, vertices):
            self.x = VIDEO_WIDTH / 2
            self.y = VIDEO_HEIGHT / 2
            self.vx = -self.vx
            self.vy = -self.vy
            return EVENT_MUSIC, None

        return None, None

    def draw(self, surface: pygame.Surface, frame_idx: int = 0):
        if not self.alive:
            return

        # Draw rainbow trail
        import colorsys
        for i, (tx, ty) in enumerate(self.trail):
            ratio = (i + 1) / len(self.trail) if self.trail else 0
            alpha = int(255 * ratio * 0.7)
            if alpha <= 0:
                continue
            # Rainbow: hue shifts along the trail + over time
            hue = ((i * 0.02) + frame_idx * 0.002) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            color = (int(r * 255), int(g * 255), int(b * 255), alpha)
            t_radius = max(2, int(self.radius * ratio * 0.8))
            trail_surf = pygame.Surface((t_radius * 2, t_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(trail_surf, color, (t_radius, t_radius), t_radius)
            surface.blit(trail_surf, (int(tx) - t_radius, int(ty) - t_radius))

        if self.spawn_timer > 0 and self.spawn_timer % 4 < 2:
            return

        # Update rotation angle from velocity direction
        self.angle = -math.degrees(math.atan2(self.vy, self.vx))

        if self.image_surface:
            # Scale image to current radius * 2
            size = max(4, int(self.radius * 2))
            scaled = pygame.transform.scale(self.image_surface, (size, size))
            rotated = pygame.transform.rotate(scaled, self.angle)
            rect = rotated.get_rect(center=(int(self.x), int(self.y)))
            surface.blit(rotated, rect)
        elif self.emoji_surface:
            rect = self.emoji_surface.get_rect(center=(int(self.x), int(self.y)))
            surface.blit(self.emoji_surface, rect)
        else:
            for r_offset in range(3, 0, -1):
                glow_alpha = 60 * r_offset
                glow_r = self.radius + r_offset * 4
                glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
                glow_color = (*self.cfg.color[:3], min(255, glow_alpha))
                pygame.draw.circle(glow_surf, glow_color, (glow_r, glow_r), glow_r)
                surface.blit(glow_surf, (int(self.x) - glow_r, int(self.y) - glow_r))

            pygame.draw.circle(surface, self.cfg.color, (int(self.x), int(self.y)), self.radius)
            highlight_pos = (int(self.x - self.radius * 0.3), int(self.y - self.radius * 0.3))
            highlight_r = max(2, self.radius // 3)
            pygame.draw.circle(surface, (255, 255, 255, 180), highlight_pos, highlight_r)


def render_scene(scene: SceneConfig, preview: bool = False) -> str:
    pygame.init()

    if preview:
        screen = pygame.display.set_mode((VIDEO_WIDTH // 2, VIDEO_HEIGHT // 2))
        pygame.display.set_caption("BouncingTikTok Preview")
    else:
        screen = None
        pygame.display.set_mode((1, 1), pygame.NOFRAME)  # tiny hidden window for convert_alpha

    surface = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
    vertices = get_shape_vertices(scene.shape, scene.shape_padding, scene.shape_rotation)

    # Spikes (optional)
    cx, cy = VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2
    circle_r = min(VIDEO_WIDTH / 2 - scene.shape_padding, VIDEO_HEIGHT / 2 - scene.shape_padding)
    if scene.spikes:
        spike_width = circle_r * 2 * math.pi / 36
        spikes = generate_spikes(cx, cy, circle_r, num_spikes=36, spike_length=60, spike_width=spike_width)
    else:
        spikes = []

    ball_cfg = scene.balls[0]
    ball = Ball(ball_cfg, 0)
    ball.init_emoji_surface()
    ball_png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ball.png")
    ball.init_image(ball_png)
    if not scene.spikes:
        ball.max_trail = 0  # infinite trail

    dead_balls: list[DeadBall] = []
    impact_effects: list[tuple[float, float, int]] = []  # (x, y, timer)
    total_frames = scene.duration * scene.fps

    if not scene.spikes:
        ball.radius = 5
        ball.base_radius = int(circle_r * 0.6)  # grow to 60% of circle
        ball.grow_speed = (ball.base_radius - 5) / total_frames
    bounce_events: list[tuple[float, str]] = []
    frames: list[np.ndarray] = []
    death_count = 0

    print(f"Rendering {total_frames} frames at {scene.fps} FPS...")
    print(f"  {len(spikes)} spikes around the circle border")

    clock = pygame.time.Clock()

    for frame_idx in range(total_frames):
        if preview:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return ""

        surface.fill(scene.bg_color)

        if spikes:
            for spike in spikes:
                spike.draw(surface)
        else:
            import colorsys as _cs
            # Rainbow border: draw arc segments with shifting hue
            num_segments = 120
            border_surf = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
            for seg_i in range(num_segments):
                a1 = 2 * math.pi * seg_i / num_segments
                a2 = 2 * math.pi * (seg_i + 1) / num_segments
                hue = ((seg_i / num_segments) + frame_idx * 0.003) % 1.0
                r, g, b = _cs.hsv_to_rgb(hue, 1.0, 1.0)
                seg_color = (int(r * 255), int(g * 255), int(b * 255))
                p1 = (int(cx + circle_r * math.cos(a1)), int(cy + circle_r * math.sin(a1)))
                p2 = (int(cx + circle_r * math.cos(a2)), int(cy + circle_r * math.sin(a2)))
                # Glow layer
                pygame.draw.line(border_surf, (*seg_color, 60), p1, p2, scene.shape_thickness + 12)
                pygame.draw.line(border_surf, (*seg_color, 100), p1, p2, scene.shape_thickness + 6)
                # Main line
                pygame.draw.line(border_surf, (*seg_color, 255), p1, p2, scene.shape_thickness + 2)
            surface.blit(border_surf, (0, 0))

            # Draw impact effects
            new_impacts = []
            for ix, iy, timer in impact_effects:
                if timer > 0:
                    alpha = min(255, timer * 20)
                    radius = int(30 + (20 - timer) * 4)
                    impact_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
                    pygame.draw.circle(impact_surf, (255, 255, 255, alpha), (radius, radius), radius)
                    surface.blit(impact_surf, (int(ix) - radius, int(iy) - radius))
                    new_impacts.append((ix, iy, timer - 1))
            impact_effects = new_impacts

        # Draw dead balls
        for db in dead_balls:
            db.draw(surface)

        # Update ball
        event_type, hit_spike = ball.update(scene.gravity, vertices, spikes, dead_balls, has_spikes=scene.spikes)

        if event_type == EVENT_MUSIC:
            bounce_events.append((frame_idx / scene.fps, EVENT_MUSIC))
            if not spikes:
                # Impact effect at the closest border point
                dx = ball.x - cx
                dy = ball.y - cy
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > 0:
                    impact_x = cx + (dx / dist) * circle_r
                    impact_y = cy + (dy / dist) * circle_r
                    impact_effects.append((impact_x, impact_y, 15))
        elif event_type == EVENT_DEATH:
            bounce_events.append((frame_idx / scene.fps, EVENT_DEATH))
            death_count += 1
            dead_balls.append(DeadBall(ball.x, ball.y, ball.radius, ball.cfg.color))
            ball.respawn()

        ball.draw(surface, frame_idx)

        # Capture frame
        frame_data = pygame.image.tostring(surface, "RGB")
        frame_array = np.frombuffer(frame_data, dtype=np.uint8).reshape((VIDEO_HEIGHT, VIDEO_WIDTH, 3))
        frames.append(frame_array)

        if preview and screen:
            preview_surface = pygame.transform.scale(surface, (VIDEO_WIDTH // 2, VIDEO_HEIGHT // 2))
            screen.blit(preview_surface, (0, 0))
            pygame.display.flip()
            clock.tick(scene.fps)

        if (frame_idx + 1) % (scene.fps * 5) == 0:
            pct = (frame_idx + 1) / total_frames * 100
            print(f"  {pct:.0f}% ({frame_idx + 1}/{total_frames} frames) - {death_count} deaths")

    pygame.quit()

    music_count = sum(1 for _, e in bounce_events if e == EVENT_MUSIC)
    death_event_count = sum(1 for _, e in bounce_events if e == EVENT_DEATH)

    # Auto-detect MIDI or MP3
    import glob
    script_dir = os.path.dirname(os.path.abspath(__file__))
    midi_path = None
    music_path = scene.music_file

    # MIDI has priority
    mid_files = glob.glob(os.path.join(script_dir, "*.mid")) + glob.glob(os.path.join(script_dir, "*.midi"))
    if mid_files:
        midi_path = mid_files[0]
        print(f"Auto-detected MIDI: {os.path.basename(midi_path)}")
    elif not music_path:
        mp3_files = glob.glob(os.path.join(script_dir, "*.mp3"))
        if mp3_files:
            music_path = mp3_files[0]
            print(f"Auto-detected music: {os.path.basename(music_path)}")

    print(f"Generating soundtrack ({music_count} music bounces, {death_event_count} deaths)...")
    wav_path = create_bounce_soundtrack(
        bounce_events, scene.duration, scene.note_sequence,
        music_path=music_path, midi_path=midi_path, chunk_ms=250
    )

    print("Encoding video...")
    from moviepy import ImageSequenceClip, AudioFileClip

    clip = ImageSequenceClip(frames, fps=scene.fps)
    audio_clip = AudioFileClip(wav_path)
    clip = clip.with_audio(audio_clip)

    output_path = scene.output_file
    clip.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=scene.fps,
        preset="medium",
        bitrate="8000k",
        logger="bar",
    )

    print(f"Video saved to: {output_path}")
    return output_path
