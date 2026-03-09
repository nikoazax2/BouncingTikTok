"""Interactive GUI with live preview for BouncingTikTok."""

import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox
import threading
import math
import os
import random
import colorsys
import time

import pygame
import numpy as np
from PIL import Image, ImageTk

from config import SceneConfig, BallConfig, PRESETS, VIDEO_WIDTH, VIDEO_HEIGHT
from shapes import get_shape_vertices, closest_edge_collision, point_in_polygon
from renderer import generate_spikes, check_circle_collision, circle_intersects_triangle

ASPECT_RATIO = VIDEO_WIDTH / VIDEO_HEIGHT  # 9:16


class BouncingTikTokGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BouncingTikTok")
        self.root.configure(bg="#1a1a2e")

        # Init pygame (hidden)
        pygame.init()
        pygame.display.set_mode((1, 1), pygame.NOFRAME)
        self.surface = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
        self.trail_surface = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)

        # Simulation state
        self.ball_x = VIDEO_WIDTH / 2.0
        self.ball_y = VIDEO_HEIGHT / 2.0
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.ball_radius = 5.0
        self.ball_base_radius = 20
        self.grow_speed = 0.0
        self.dead_balls = []
        self.impact_effects = []
        self.spikes_list = []
        self.vertices = []
        self.cx = VIDEO_WIDTH / 2
        self.cy = VIDEO_HEIGHT / 2
        self.circle_r = 0
        self.frame_idx = 0
        self.bounces = 0
        self.deaths = 0
        self.paused = False
        self.running = True
        self.spawn_timer = 0
        self.image_surface = None

        # Load ball.png
        ball_png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ball.png")
        if os.path.exists(ball_png):
            raw = pygame.image.load(ball_png)
            self.image_surface = raw.convert_alpha()

        # Bounce sound (synth tone via pygame mixer)
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self._note_idx = 0
        from sounds import generate_synth_lead, generate_death_sound, midi_to_freq, extract_notes_from_midi
        import glob as _glob
        script_dir = os.path.dirname(os.path.abspath(__file__))
        mid_files = _glob.glob(os.path.join(script_dir, "*.mid")) + _glob.glob(os.path.join(script_dir, "*.midi"))
        if mid_files:
            self._midi_sequence = extract_notes_from_midi(mid_files[0]) or [60, 62, 64, 65, 67, 69, 71, 72]
        else:
            self._midi_sequence = [60, 62, 64, 65, 67, 69, 71, 72]
        # Pre-generate only unique notes
        unique_notes = sorted(set(self._midi_sequence))
        self._sound_cache = {}
        for midi_note in unique_notes:
            freq = midi_to_freq(midi_note)
            tone = generate_synth_lead(freq, duration=0.3, volume=0.4)
            mono = (tone * 32767).astype(np.int16)
            samples = np.column_stack((mono, mono))
            self._sound_cache[midi_note] = pygame.sndarray.make_sound(samples)
        death_tone = generate_death_sound(duration=0.4, volume=0.5)
        death_mono = (death_tone * 32767).astype(np.int16)
        self._death_sound = pygame.sndarray.make_sound(np.column_stack((death_mono, death_mono)))

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#1a1a2e")
        self.style.configure("TLabel", background="#1a1a2e", foreground="#e0e0e0", font=("Segoe UI", 9))
        self.style.configure("Header.TLabel", background="#1a1a2e", foreground="#00d4ff", font=("Segoe UI", 12, "bold"))
        self.style.configure("Stats.TLabel", background="#1a1a2e", foreground="#aaffaa", font=("Consolas", 9))
        self.style.configure("TLabelframe", background="#1a1a2e", foreground="#00d4ff")
        self.style.configure("TLabelframe.Label", background="#1a1a2e", foreground="#00d4ff", font=("Segoe UI", 9, "bold"))

        self._build_ui()
        self._reset()
        self._loop()

    def _build_ui(self):
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)

        # Left: scrollable controls
        left_container = ttk.Frame(main, width=420)
        left_container.pack(side="left", fill="y")
        left_container.pack_propagate(False)

        canvas = tk.Canvas(left_container, bg="#1a1a2e", highlightthickness=0, width=400)
        scrollbar = ttk.Scrollbar(left_container, orient="vertical", command=canvas.yview)
        self.ctrl_frame = ttk.Frame(canvas)
        self.ctrl_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.ctrl_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        pad = {"padx": 8, "pady": 3}

        ttk.Label(self.ctrl_frame, text="BouncingTikTok", style="Header.TLabel").pack(padx=8, pady=(10, 2))

        # --- Presets ---
        pf = ttk.LabelFrame(self.ctrl_frame, text="Preset", padding=5)
        pf.pack(fill="x", **pad)
        self.preset_var = tk.StringVar(value="(custom)")
        combo = ttk.Combobox(pf, textvariable=self.preset_var,
                             values=["(custom)"] + list(PRESETS.keys()), state="readonly", width=20)
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", self._on_preset)

        # --- Shape ---
        sf = ttk.LabelFrame(self.ctrl_frame, text="Shape", padding=5)
        sf.pack(fill="x", **pad)

        r = 0
        ttk.Label(sf, text="Type:").grid(row=r, column=0, sticky="w")
        self.shape_var = tk.StringVar(value="circle")
        ttk.Combobox(sf, textvariable=self.shape_var,
                     values=["rectangle", "circle", "triangle", "hexagon", "pentagon", "star", "diamond"],
                     state="readonly", width=12).grid(row=r, column=1, padx=3)

        r += 1
        ttk.Label(sf, text="Padding:").grid(row=r, column=0, sticky="w")
        self.padding_var = tk.IntVar(value=100)
        ttk.Scale(sf, from_=30, to=400, variable=self.padding_var, orient="horizontal").grid(row=r, column=1, sticky="ew")

        r += 1
        ttk.Label(sf, text="Rotation:").grid(row=r, column=0, sticky="w")
        self.rotation_var = tk.DoubleVar(value=0)
        ttk.Scale(sf, from_=0, to=360, variable=self.rotation_var, orient="horizontal").grid(row=r, column=1, sticky="ew")

        r += 1
        ttk.Label(sf, text="Thickness:").grid(row=r, column=0, sticky="w")
        self.thickness_var = tk.IntVar(value=3)
        ttk.Scale(sf, from_=1, to=10, variable=self.thickness_var, orient="horizontal").grid(row=r, column=1, sticky="ew")

        r += 1
        self.spikes_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sf, text="Spikes", variable=self.spikes_var).grid(row=r, column=0, columnspan=2, sticky="w")

        sf.columnconfigure(1, weight=1)

        # --- Ball ---
        bf = ttk.LabelFrame(self.ctrl_frame, text="Ball", padding=5)
        bf.pack(fill="x", **pad)

        r = 0
        ttk.Label(bf, text="Speed:").grid(row=r, column=0, sticky="w")
        self.speed_var = tk.DoubleVar(value=13.0)
        ttk.Scale(bf, from_=1, to=25, variable=self.speed_var, orient="horizontal").grid(row=r, column=1, sticky="ew")

        r += 1
        ttk.Label(bf, text="Launch angle:").grid(row=r, column=0, sticky="w")
        self.launch_var = tk.DoubleVar(value=19.0)
        ttk.Scale(bf, from_=0, to=360, variable=self.launch_var, orient="horizontal").grid(row=r, column=1, sticky="ew")

        r += 1
        ttk.Label(bf, text="Radius:").grid(row=r, column=0, sticky="w")
        self.radius_var = tk.IntVar(value=20)
        ttk.Scale(bf, from_=5, to=80, variable=self.radius_var, orient="horizontal").grid(row=r, column=1, sticky="ew")

        r += 1
        ttk.Label(bf, text="Trail:").grid(row=r, column=0, sticky="w")
        self.trail_var = tk.IntVar(value=30)
        ttk.Scale(bf, from_=0, to=200, variable=self.trail_var, orient="horizontal").grid(row=r, column=1, sticky="ew")

        r += 1
        self.use_image_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bf, text="Use ball.png", variable=self.use_image_var).grid(row=r, column=0, columnspan=2, sticky="w")

        r += 1
        self.growth_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bf, text="Growth (no-spike mode)", variable=self.growth_var).grid(row=r, column=0, columnspan=2, sticky="w")

        bf.columnconfigure(1, weight=1)

        # --- Physics ---
        phf = ttk.LabelFrame(self.ctrl_frame, text="Physics", padding=5)
        phf.pack(fill="x", **pad)

        r = 0
        ttk.Label(phf, text="Gravity:").grid(row=r, column=0, sticky="w")
        self.gravity_var = tk.DoubleVar(value=0.2)
        ttk.Scale(phf, from_=0, to=1.0, variable=self.gravity_var, orient="horizontal").grid(row=r, column=1, sticky="ew")

        r += 1
        ttk.Label(phf, text="Nudge (rad):").grid(row=r, column=0, sticky="w")
        self.nudge_var = tk.DoubleVar(value=0.3)
        ttk.Scale(phf, from_=0, to=1.0, variable=self.nudge_var, orient="horizontal").grid(row=r, column=1, sticky="ew")

        phf.columnconfigure(1, weight=1)

        # --- Colors ---
        cf = ttk.LabelFrame(self.ctrl_frame, text="Colors", padding=5)
        cf.pack(fill="x", **pad)

        self.bg_color = (10, 10, 15)
        self.shape_color = (255, 255, 255)
        self.ball_color = (255, 100, 50)

        ttk.Label(cf, text="Background:").grid(row=0, column=0, sticky="w")
        self.bg_btn = tk.Button(cf, bg="#0a0a0f", width=4, command=lambda: self._pick_color("bg"))
        self.bg_btn.grid(row=0, column=1, padx=3)

        ttk.Label(cf, text="Shape:").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.shape_btn = tk.Button(cf, bg="#ffffff", width=4, command=lambda: self._pick_color("shape"))
        self.shape_btn.grid(row=0, column=3, padx=3)

        ttk.Label(cf, text="Ball:").grid(row=1, column=0, sticky="w")
        self.ball_btn = tk.Button(cf, bg="#ff6432", width=4, command=lambda: self._pick_color("ball"))
        self.ball_btn.grid(row=1, column=1, padx=3)

        # --- Output ---
        of = ttk.LabelFrame(self.ctrl_frame, text="Output", padding=5)
        of.pack(fill="x", **pad)

        ttk.Label(of, text="Duration (s):").grid(row=0, column=0, sticky="w")
        self.duration_var = tk.IntVar(value=40)
        ttk.Spinbox(of, from_=5, to=120, textvariable=self.duration_var, width=5).grid(row=0, column=1, padx=3)

        ttk.Label(of, text="FPS:").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.fps_var = tk.IntVar(value=60)
        ttk.Combobox(of, textvariable=self.fps_var, values=[30, 60], state="readonly", width=4).grid(row=0, column=3, padx=3)

        ttk.Label(of, text="File:").grid(row=1, column=0, sticky="w")
        self.output_var = tk.StringVar(value="output.mp4")
        ttk.Entry(of, textvariable=self.output_var, width=20).grid(row=1, column=1, columnspan=2, sticky="ew")
        ttk.Button(of, text="...", width=3, command=self._browse_output).grid(row=1, column=3, padx=3)

        ttk.Label(of, text="Music:").grid(row=2, column=0, sticky="w")
        self.music_var = tk.StringVar(value="")
        ttk.Entry(of, textvariable=self.music_var, width=20).grid(row=2, column=1, columnspan=2, sticky="ew")
        ttk.Button(of, text="...", width=3, command=self._browse_music).grid(row=2, column=3, padx=3)

        of.columnconfigure(1, weight=1)

        # --- Buttons ---
        btn_frame = ttk.Frame(self.ctrl_frame)
        btn_frame.pack(fill="x", padx=8, pady=8)

        tk.Button(btn_frame, text="Reset", font=("Segoe UI", 10),
                  bg="#444466", fg="#e0e0e0", relief="flat", padx=10, pady=4,
                  command=self._reset).pack(side="left", padx=3)

        self.pause_btn = tk.Button(btn_frame, text="Pause", font=("Segoe UI", 10),
                                   bg="#444466", fg="#e0e0e0", relief="flat", padx=10, pady=4,
                                   command=self._toggle_pause)
        self.pause_btn.pack(side="left", padx=3)

        tk.Button(btn_frame, text="Export Video", font=("Segoe UI", 10, "bold"),
                  bg="#00d4ff", fg="#1a1a2e", relief="flat", padx=15, pady=4,
                  command=self._export).pack(side="right", padx=3)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.ctrl_frame, textvariable=self.status_var, style="Stats.TLabel").pack(**pad)

        self.stats_var = tk.StringVar(value="Frame: 0 | Bounces: 0 | Deaths: 0")
        ttk.Label(self.ctrl_frame, textvariable=self.stats_var, style="Stats.TLabel").pack(**pad)

        # Right: preview
        right = ttk.Frame(main)
        right.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        self.preview_label = tk.Label(right, bg="#000000")
        self.preview_label.pack(fill="both", expand=True)

        # Auto-reset preview when any param changes
        for var in (self.shape_var, self.spikes_var, self.padding_var, self.rotation_var,
                    self.thickness_var, self.speed_var, self.launch_var, self.radius_var,
                    self.trail_var, self.use_image_var, self.growth_var,
                    self.gravity_var, self.nudge_var):
            var.trace_add("write", lambda *_: self._schedule_reset())
        self._reset_pending = None

    def _schedule_reset(self):
        if self._reset_pending:
            self.root.after_cancel(self._reset_pending)
        self._reset_pending = self.root.after(80, self._reset)

    def _pick_color(self, which):
        current = getattr(self, f"{which}_color")
        result = colorchooser.askcolor(current, title=f"{which.title()} color")
        if result[0]:
            color = tuple(int(c) for c in result[0])
            setattr(self, f"{which}_color", color)
            btn = getattr(self, f"{which}_btn")
            btn.configure(bg=result[1])
            self._schedule_reset()

    def _browse_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if path:
            self.output_var.set(path)

    def _browse_music(self):
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.ogg *.mid *.midi")])
        if path:
            self.music_var.set(path)

    def _on_preset(self, event=None):
        name = self.preset_var.get()
        if name == "(custom)" or name not in PRESETS:
            return
        cfg = PRESETS[name]
        self.shape_var.set(cfg.shape)
        self.bg_color = cfg.bg_color
        self.bg_btn.configure(bg="#%02x%02x%02x" % cfg.bg_color)
        self.shape_color = cfg.shape_color
        self.shape_btn.configure(bg="#%02x%02x%02x" % cfg.shape_color)
        self.gravity_var.set(cfg.gravity)
        self.spikes_var.set(cfg.spikes)
        self.padding_var.set(cfg.shape_padding)
        self.thickness_var.set(cfg.shape_thickness)
        if cfg.balls:
            b = cfg.balls[0]
            self.radius_var.set(b.radius)
            self.speed_var.set(math.sqrt(b.speed_x ** 2 + b.speed_y ** 2))
            self.trail_var.set(b.trail_length)
            self.ball_color = b.color
            self.ball_btn.configure(bg="#%02x%02x%02x" % b.color)
        self._reset()

    def _reset(self):
        shape = self.shape_var.get()
        padding = self.padding_var.get()
        rotation = self.rotation_var.get()

        self.vertices = get_shape_vertices(shape, padding, rotation)

        cx, cy = VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2
        circle_r = min(VIDEO_WIDTH / 2 - padding, VIDEO_HEIGHT / 2 - padding)
        self.cx, self.cy, self.circle_r = cx, cy, circle_r

        speed = self.speed_var.get()
        angle = self.launch_var.get()
        self.ball_x = cx
        self.ball_y = cy
        self.ball_vx = speed * math.sin(math.radians(angle))
        self.ball_vy = speed * math.cos(math.radians(angle))

        has_spikes = self.spikes_var.get()
        if has_spikes:
            spike_width = circle_r * 2 * math.pi / 36
            self.spikes_list = generate_spikes(cx, cy, circle_r, num_spikes=36,
                                               spike_length=60, spike_width=spike_width)
        else:
            self.spikes_list = []

        base_r = self.radius_var.get()
        if not has_spikes and self.growth_var.get():
            self.ball_radius = 5.0
            self.ball_base_radius = int(circle_r * 0.6)
            total = self.duration_var.get() * self.fps_var.get()
            self.grow_speed = (self.ball_base_radius - 5) / total if total > 0 else 0
        else:
            self.ball_radius = float(base_r)
            self.ball_base_radius = base_r
            self.grow_speed = 0

        self.trail_surface = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
        self.dead_balls = []
        self.impact_effects = []
        self.frame_idx = 0
        self.bounces = 0
        self.deaths = 0
        self.spawn_timer = 0
        self.paused = False
        self.pause_btn.configure(text="Pause")

    def _toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.configure(text="Play" if self.paused else "Pause")

    def _closest_point_on_polygon(self, px, py):
        best_dist = float('inf')
        best_x, best_y = px, py
        n = len(self.vertices)
        for i in range(n):
            x1, y1 = self.vertices[i]
            x2, y2 = self.vertices[(i + 1) % n]
            ex, ey = x2 - x1, y2 - y1
            edge_len_sq = ex * ex + ey * ey
            if edge_len_sq == 0:
                continue
            t = max(0, min(1, ((px - x1) * ex + (py - y1) * ey) / edge_len_sq))
            cx, cy = x1 + t * ex, y1 + t * ey
            d = (px - cx) ** 2 + (py - cy) ** 2
            if d < best_dist:
                best_dist = d
                best_x, best_y = cx, cy
        return best_x, best_y

    def _play_bounce(self):
        midi_note = self._midi_sequence[self._note_idx % len(self._midi_sequence)]
        snd = self._sound_cache.get(midi_note)
        if snd:
            snd.play()
        self._note_idx += 1

    def _step(self):
        if self.paused:
            return

        gravity = self.gravity_var.get()
        nudge = self.nudge_var.get()
        has_spikes = bool(self.spikes_list)

        self.ball_vy += gravity

        if self.grow_speed > 0 and self.ball_radius < self.ball_base_radius:
            self.ball_radius = min(self.ball_base_radius, self.ball_radius + self.grow_speed)

        # Draw trail point on persistent surface
        hue = (self.frame_idx * 0.01) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        tr = max(2, int(self.ball_radius * 0.8))
        pygame.draw.circle(self.trail_surface, (int(r * 255), int(g * 255), int(b * 255), 180),
                           (int(self.ball_x), int(self.ball_y)), tr)

        # Fade trail for finite mode
        max_trail = self.trail_var.get() if has_spikes else 0
        if max_trail > 0:
            fade = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
            fade_alpha = max(1, 255 // max(max_trail, 1))
            fade.fill((0, 0, 0, fade_alpha))
            self.trail_surface.blit(fade, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy

        new_vx, new_vy, wall_hit = closest_edge_collision(
            self.ball_x, self.ball_y, self.ball_radius,
            self.ball_vx, self.ball_vy, self.vertices
        )
        if wall_hit:
            old_speed = math.sqrt(self.ball_vx ** 2 + self.ball_vy ** 2)
            a = math.atan2(new_vy, new_vx)
            a += random.uniform(-nudge, nudge)
            self.ball_vx = old_speed * math.cos(a)
            self.ball_vy = old_speed * math.sin(a)
            self.ball_x += self.ball_vx * 0.5
            self.ball_y += self.ball_vy * 0.5
            self.bounces += 1
            self._play_bounce()
            if not has_spikes:
                ix, iy = self._closest_point_on_polygon(self.ball_x, self.ball_y)
                self.impact_effects.append((ix, iy, 15))

        for db in self.dead_balls:
            nv_x, nv_y, hit = check_circle_collision(
                self.ball_x, self.ball_y, self.ball_radius,
                self.ball_vx, self.ball_vy, db[0], db[1], db[2]
            )
            if hit:
                self.ball_vx = nv_x
                self.ball_vy = nv_y
                self.bounces += 1
                self._play_bounce()
                break

        if self.spawn_timer > 0:
            self.spawn_timer -= 1
        elif self.spikes_list:
            for spike in self.spikes_list:
                if circle_intersects_triangle(self.ball_x, self.ball_y,
                                              self.ball_radius, spike.vertices):
                    self.deaths += 1
                    self._death_sound.play()
                    self.dead_balls.append((self.ball_x, self.ball_y, int(self.ball_radius)))
                    self.ball_x = VIDEO_WIDTH / 2.0
                    self.ball_y = VIDEO_HEIGHT / 2.0
                    speed = self.speed_var.get()
                    la = self.launch_var.get()
                    self.ball_vx = speed * math.sin(math.radians(la))
                    self.ball_vy = speed * math.cos(math.radians(la))
                    self.trail_surface = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
                    self.spawn_timer = 20
                    break

        if not point_in_polygon(self.ball_x, self.ball_y, self.vertices):
            self.ball_x = VIDEO_WIDTH / 2
            self.ball_y = VIDEO_HEIGHT / 2
            self.ball_vx = -self.ball_vx
            self.ball_vy = -self.ball_vy

        self.frame_idx += 1

    def _render(self):
        self.surface.fill(self.bg_color)
        has_spikes = bool(self.spikes_list)

        if has_spikes:
            for spike in self.spikes_list:
                spike.draw(self.surface)
            pygame.draw.polygon(self.surface, self.shape_color,
                                [(int(x), int(y)) for x, y in self.vertices],
                                self.thickness_var.get())
        else:
            thickness = self.thickness_var.get()
            border_surf = pygame.Surface((VIDEO_WIDTH, VIDEO_HEIGHT), pygame.SRCALPHA)
            # Rainbow border along actual shape vertices
            n_verts = len(self.vertices)
            seg_idx = 0
            total_segs = 0
            # Count total segments for even hue distribution
            edge_subs = []
            for i in range(n_verts):
                x1, y1 = self.vertices[i]
                x2, y2 = self.vertices[(i + 1) % n_verts]
                edge_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                ns = max(1, int(edge_len / 20))
                edge_subs.append(ns)
                total_segs += ns
            for i in range(n_verts):
                x1, y1 = self.vertices[i]
                x2, y2 = self.vertices[(i + 1) % n_verts]
                ns = edge_subs[i]
                for j in range(ns):
                    t1 = j / ns
                    t2 = (j + 1) / ns
                    p1 = (int(x1 + (x2 - x1) * t1), int(y1 + (y2 - y1) * t1))
                    p2 = (int(x1 + (x2 - x1) * t2), int(y1 + (y2 - y1) * t2))
                    hue = ((seg_idx / total_segs) + self.frame_idx * 0.003) % 1.0
                    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                    sc = (int(r * 255), int(g * 255), int(b * 255))
                    pygame.draw.line(border_surf, (*sc, 60), p1, p2, thickness + 12)
                    pygame.draw.line(border_surf, (*sc, 100), p1, p2, thickness + 6)
                    pygame.draw.line(border_surf, (*sc, 255), p1, p2, thickness + 2)
                    seg_idx += 1
            self.surface.blit(border_surf, (0, 0))

            new_fx = []
            for ix, iy, t in self.impact_effects:
                if t > 0:
                    alpha = min(255, t * 20)
                    rad = int(30 + (20 - t) * 4)
                    fx_surf = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
                    pygame.draw.circle(fx_surf, (255, 255, 255, alpha), (rad, rad), rad)
                    self.surface.blit(fx_surf, (int(ix) - rad, int(iy) - rad))
                    new_fx.append((ix, iy, t - 1))
            self.impact_effects = new_fx

        for dx, dy, dr in self.dead_balls:
            pygame.draw.circle(self.surface, (120, 120, 120), (int(dx), int(dy)), dr)

        # Trail
        self.surface.blit(self.trail_surface, (0, 0))

        # Ball
        blink = self.spawn_timer > 0 and self.spawn_timer % 4 < 2
        if not blink:
            angle = -math.degrees(math.atan2(self.ball_vy, self.ball_vx))
            if self.use_image_var.get() and self.image_surface:
                size = max(4, int(self.ball_radius * 2))
                scaled = pygame.transform.scale(self.image_surface, (size, size))
                rotated = pygame.transform.rotate(scaled, angle)
                rect = rotated.get_rect(center=(int(self.ball_x), int(self.ball_y)))
                self.surface.blit(rotated, rect)
            else:
                bc = self.ball_color
                for r_off in range(3, 0, -1):
                    ga = 60 * r_off
                    gr = int(self.ball_radius) + r_off * 4
                    gs = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
                    pygame.draw.circle(gs, (*bc[:3], min(255, ga)), (gr, gr), gr)
                    self.surface.blit(gs, (int(self.ball_x) - gr, int(self.ball_y) - gr))
                pygame.draw.circle(self.surface, bc,
                                   (int(self.ball_x), int(self.ball_y)), int(self.ball_radius))

        # Convert to PIL, scale to fit available space
        data = pygame.image.tostring(self.surface, "RGB")
        img = Image.frombytes("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), data)
        lh = self.preview_label.winfo_height()
        lw = self.preview_label.winfo_width()
        if lh < 10 or lw < 10:
            lh, lw = 480, 270
        # Fit 9:16 into available space
        ph = lh
        pw = int(ph * ASPECT_RATIO)
        if pw > lw:
            pw = lw
            ph = int(pw / ASPECT_RATIO)
        pw = max(pw, 10)
        ph = max(ph, 10)
        return img.resize((pw, ph), Image.NEAREST)

    def _loop(self):
        if not self.running:
            return

        t0 = time.time()
        self._step()
        img = self._render()
        self.tk_img = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=self.tk_img)

        elapsed_ms = (time.time() - t0) * 1000
        fps_actual = 1000 / max(1, elapsed_ms)
        self.stats_var.set(
            f"Frame: {self.frame_idx} | Bounces: {self.bounces} | "
            f"Deaths: {self.deaths} | {fps_actual:.0f} fps")

        delay = max(1, int(16 - elapsed_ms))
        self.root.after(delay, self._loop)

    def _export(self):
        speed = self.speed_var.get()
        la = self.launch_var.get()
        scene = SceneConfig(
            shape=self.shape_var.get(),
            shape_color=self.shape_color,
            shape_thickness=self.thickness_var.get(),
            shape_padding=self.padding_var.get(),
            shape_rotation=self.rotation_var.get(),
            bg_color=self.bg_color,
            gravity=self.gravity_var.get(),
            balls=[BallConfig(
                radius=self.radius_var.get(),
                color=self.ball_color,
                speed_x=speed * math.sin(math.radians(la)),
                speed_y=speed * math.cos(math.radians(la)),
                trail_length=self.trail_var.get(),
            )],
            spikes=self.spikes_var.get(),
            duration=self.duration_var.get(),
            fps=self.fps_var.get(),
            output_file=self.output_var.get(),
            music_file=self.music_var.get() or None,
        )

        self.status_var.set("Exporting...")

        def run():
            try:
                from renderer import render_scene
                output = render_scene(scene, preview=False)
                self.root.after(0, lambda: self.status_var.set(f"Saved: {output}"))
                self.root.after(0, lambda: messagebox.showinfo("Done", f"Video saved to:\n{output}"))
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"Error: {e}"))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def run(self):
        def on_close():
            self.running = False
            self.root.destroy()
            pygame.quit()
        self.root.protocol("WM_DELETE_WINDOW", on_close)
        self.root.mainloop()


def launch_gui():
    app = BouncingTikTokGUI()
    app.run()


if __name__ == "__main__":
    launch_gui()
