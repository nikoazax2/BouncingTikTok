"""Main rendering engine - simulates and renders bouncing balls."""

import math
import os
import sys
import random
import pygame
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
        self.vx = cfg.speed_x
        self.vy = cfg.speed_y
        self.base_radius = cfg.radius
        self.radius = cfg.radius
        self.grow_speed = 0  # set externally if needed
        self.grow_frame = None  # for exponential growth
        self.grow_total = 0
        self.grow_start = 5
        self.emoji_surface = None
        self.image_surface = None  # loaded from ball.png
        self.angle = 0.0  # current rotation angle in degrees
        self.alive = True
        self.spawn_timer = 0

    def respawn(self):
        self.x = VIDEO_WIDTH / 2.0
        self.y = VIDEO_HEIGHT / 2.0
        self.vx = self.cfg.speed_x
        self.vy = self.cfg.speed_y
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
               has_spikes: bool = True,
               nudge: float = 0.3, energy_loss: float = 0.0
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

        self.x += self.vx
        self.y += self.vy

        # 1) Check collision with circle border → MUSIC
        new_vx, new_vy, wall_hit, px, py = closest_edge_collision(
            self.x, self.y, self.radius, self.vx, self.vy, vertices
        )
        self.x += px
        self.y += py
        if wall_hit:
            old_speed = math.sqrt(self.vx ** 2 + self.vy ** 2) * (1 - energy_loss)
            angle = math.atan2(new_vy, new_vx)
            angle += random.uniform(-nudge, nudge)
            self.vx = old_speed * math.cos(angle)
            self.vy = old_speed * math.sin(angle)
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

        if self.spawn_timer > 0 and self.spawn_timer % 4 < 2:
            return

        # Update rotation angle from velocity direction
        self.angle = -math.degrees(math.atan2(self.vy, self.vx))

        if self.image_surface:
            size = max(4, int(self.radius * 2))
            scaled = pygame.transform.scale(self.image_surface, (size, size))
            rotated = pygame.transform.rotate(scaled, self.angle)
            rect = rotated.get_rect(center=(int(self.x), int(self.y)))
            surface.blit(rotated, rect)
        elif self.emoji_surface:
            rect = self.emoji_surface.get_rect(center=(int(self.x), int(self.y)))
            surface.blit(self.emoji_surface, rect)
        else:
            # Glow (matches JS shadowBlur=16)
            glow_r = self.radius + 16
            glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            glow_color = (*self.cfg.color[:3], 80)
            pygame.draw.circle(glow_surf, glow_color, (glow_r, glow_r), glow_r)
            surface.blit(glow_surf, (int(self.x) - glow_r, int(self.y) - glow_r))
            # Solid ball
            pygame.draw.circle(surface, self.cfg.color, (int(self.x), int(self.y)), self.radius)


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
    if scene.use_image:
        ball_png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ball.png")
        ball.init_image(ball_png)

    dead_balls: list[DeadBall] = []
    impact_effects: list[tuple[float, float, int]] = []  # (x, y, timer)
    total_frames = scene.duration * scene.fps

    if not scene.spikes and scene.growth:
        ball.radius = 5
        ball.base_radius = int(circle_r * 0.6)
        grow_frames = scene.grow_time * scene.fps
        ball.grow_speed = (ball.base_radius - 5) / grow_frames if grow_frames > 0 else 0
    bounce_events: list[tuple[float, str]] = []
    death_count = 0

    # Stream frames to ffmpeg via pipe (saves RAM)
    import subprocess as _sp
    video_tmp = scene.output_file + ".video.mp4"
    ffmpeg_proc = None
    if not preview:
        ffmpeg_proc = _sp.Popen([
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "-r", str(scene.fps),
            "-i", "pipe:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            video_tmp,
        ], stdin=_sp.PIPE, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    # Persistent trail surface (like JS trailCtx)
    trail_surface = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
    trail_surface.fill((0, 0, 0, 0))
    has_spikes = bool(spikes)
    trail_length = ball_cfg.trail_length if ball_cfg.trail_length > 0 else 0

    print(f"Rendering {total_frames} frames at {scene.fps} FPS...")
    print(f"  {len(spikes)} spikes around the circle border")

    clock = pygame.time.Clock()
    import colorsys as _cs

    for frame_idx in range(total_frames):
        if preview:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return ""

        # 1) Paint trail at ball position (before move, like JS)
        tt = scene.trail_type
        if ball.alive and tt != "none":
            hue = (frame_idx * 0.01) % 1.0
            tr, tg, tb = _cs.hsv_to_rgb(hue, 1.0, 1.0)
            t_rad = max(2, int(ball.radius * 0.8))
            trail_color = (int(tr * 255), int(tg * 255), int(tb * 255), 178)
            if tt == "fill":
                t_surf = pygame.Surface((t_rad * 2, t_rad * 2), pygame.SRCALPHA)
                pygame.draw.circle(t_surf, trail_color, (t_rad, t_rad), t_rad)
                trail_surface.blit(t_surf, (int(ball.x) - t_rad, int(ball.y) - t_rad))
            elif tt == "ring":
                pygame.draw.circle(trail_surface, trail_color, (int(ball.x), int(ball.y)), t_rad, 2)
            elif tt == "dots":
                dot_r = max(1, int(t_rad * 0.3))
                dot_color = (int(tr * 255), int(tg * 255), int(tb * 255), 229)
                pygame.draw.circle(trail_surface, dot_color, (int(ball.x), int(ball.y)), dot_r)
            elif tt == "line":
                if hasattr(ball, '_prev_trail') and ball._prev_trail is not None:
                    lw = ball.radius * 2
                    pygame.draw.line(trail_surface, trail_color, ball._prev_trail, (int(ball.x), int(ball.y)), lw)
                ball._prev_trail = (int(ball.x), int(ball.y))

        # 2) Fade trail (like JS destination-out) — 200 = infinite
        if trail_length > 0 and trail_length < 200 and tt != "none":
            fade_alpha = max(1, int(255 / trail_length))
            fade_surf = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
            fade_surf.fill((0, 0, 0, fade_alpha))
            trail_surface.blit(fade_surf, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

        surface.fill(scene.bg_color)

        if spikes:
            for spike in spikes:
                spike.draw(surface)
            # Draw shape border (like JS)
            int_verts = [(int(v[0]), int(v[1])) for v in vertices]
            pygame.draw.polygon(surface, scene.shape_color, int_verts, scene.shape_thickness)
        else:
            # Rainbow border: draw segments with shifting hue (like JS)
            n_verts = len(vertices)
            seg_idx = 0
            total_segs = 0
            edge_subs = []
            for vi in range(n_verts):
                x1, y1 = vertices[vi]
                x2, y2 = vertices[(vi + 1) % n_verts]
                ns = max(1, int(math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) / 20))
                edge_subs.append(ns)
                total_segs += ns

            border_surf = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
            seg_idx = 0
            for vi in range(n_verts):
                x1, y1 = vertices[vi]
                x2, y2 = vertices[(vi + 1) % n_verts]
                ns = edge_subs[vi]
                for j in range(ns):
                    t1 = j / ns
                    t2 = (j + 1) / ns
                    px1 = x1 + (x2 - x1) * t1
                    py1 = y1 + (y2 - y1) * t1
                    px2 = x1 + (x2 - x1) * t2
                    py2 = y1 + (y2 - y1) * t2
                    hue = ((seg_idx / total_segs) + frame_idx * 0.003) % 1.0
                    r, g, b = _cs.hsv_to_rgb(hue, 1.0, 1.0)
                    seg_color = (int(r * 255), int(g * 255), int(b * 255))
                    # Glow layers
                    pygame.draw.line(border_surf, (*seg_color, 60), (int(px1), int(py1)), (int(px2), int(py2)), scene.shape_thickness + 12)
                    pygame.draw.line(border_surf, (*seg_color, 100), (int(px1), int(py1)), (int(px2), int(py2)), scene.shape_thickness + 6)
                    # Main line
                    pygame.draw.line(border_surf, (*seg_color, 255), (int(px1), int(py1)), (int(px2), int(py2)), scene.shape_thickness + 2)
                    seg_idx += 1
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

        # Blit persistent trail
        surface.blit(trail_surface, (0, 0))

        # Update ball
        event_type, hit_spike = ball.update(scene.gravity, vertices, spikes, dead_balls, has_spikes=scene.spikes, nudge=scene.nudge, energy_loss=scene.energy_loss)

        if event_type == EVENT_MUSIC:
            bounce_events.append((frame_idx / scene.fps, EVENT_MUSIC))
            if not spikes:
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
            trail_surface.fill((0, 0, 0, 0))  # clear trail on death (like JS)
            ball._prev_trail = None

        ball.draw(surface, frame_idx)

        # Write frame to ffmpeg pipe (or store for preview)
        frame_data = pygame.image.tostring(surface, "RGB")
        if ffmpeg_proc:
            ffmpeg_proc.stdin.write(frame_data)

        if preview and screen:
            preview_surface = pygame.transform.scale(surface, (VIDEO_WIDTH // 2, VIDEO_HEIGHT // 2))
            screen.blit(preview_surface, (0, 0))
            pygame.display.flip()
            clock.tick(scene.fps)

        if (frame_idx + 1) % (scene.fps * 5) == 0:
            pct = (frame_idx + 1) / total_frames * 100
            print(f"  {pct:.0f}% ({frame_idx + 1}/{total_frames} frames) - {death_count} deaths")

    # Close ffmpeg pipe
    if ffmpeg_proc:
        ffmpeg_proc.stdin.close()
        ffmpeg_proc.wait()

    pygame.quit()

    music_count = sum(1 for _, e in bounce_events if e == EVENT_MUSIC)
    death_event_count = sum(1 for _, e in bounce_events if e == EVENT_DEATH)

    # Detect music source based on user's mode
    import glob
    script_dir = os.path.dirname(os.path.abspath(__file__))
    midi_path = None
    music_path = scene.music_file

    if scene.mp3_mode:
        mp3_files = glob.glob(os.path.join(script_dir, "*.mp3"))
        if mp3_files:
            music_path = mp3_files[0]
            print(f"Using MP3: {os.path.basename(music_path)}")
    else:
        mid_files = glob.glob(os.path.join(script_dir, "*.mid")) + glob.glob(os.path.join(script_dir, "*.midi"))
        if mid_files:
            midi_path = mid_files[0]
            print(f"Using MIDI: {os.path.basename(midi_path)}")

    print(f"Generating soundtrack ({music_count} music bounces, {death_event_count} deaths)...")
    wav_path = create_bounce_soundtrack(
        bounce_events, scene.duration, scene.note_sequence,
        music_path=music_path, midi_path=midi_path,
        chunk_ms=scene.mp3_chunk_ms,
        filter_channels=scene.selected_channels,
    )

    # Mux video + audio with ffmpeg
    output_path = scene.output_file
    print("Muxing audio...")
    _sp.run([
        "ffmpeg", "-y",
        "-i", video_tmp,
        "-i", wav_path,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", output_path,
    ], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)

    # Cleanup temp files
    for f in [video_tmp, wav_path]:
        try:
            os.remove(f)
        except OSError:
            pass

    print(f"Video saved to: {output_path}")
    return output_path
