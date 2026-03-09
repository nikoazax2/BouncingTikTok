"""Shape definitions and collision detection for bouncing boundaries."""

import math
import pygame
import numpy as np
from config import VIDEO_WIDTH, VIDEO_HEIGHT, ShapeType


def get_shape_vertices(shape: ShapeType, padding: int, rotation: float = 0.0) -> list[tuple[float, float]]:
    """Return vertices for the given shape type, centered on screen."""
    cx, cy = VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2
    # Use available space minus padding
    half_w = VIDEO_WIDTH / 2 - padding
    half_h = VIDEO_HEIGHT / 2 - padding

    if shape == "rectangle":
        verts = [
            (cx - half_w, cy - half_h),
            (cx + half_w, cy - half_h),
            (cx + half_w, cy + half_h),
            (cx - half_w, cy + half_h),
        ]
    elif shape == "circle":
        # Approximate circle with many segments
        n = 64
        r = min(half_w, half_h)
        verts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    elif shape == "triangle":
        r = min(half_w, half_h)
        verts = [
            (cx + r * math.cos(math.radians(-90)), cy + r * math.sin(math.radians(-90))),
            (cx + r * math.cos(math.radians(150)), cy + r * math.sin(math.radians(150))),
            (cx + r * math.cos(math.radians(30)), cy + r * math.sin(math.radians(30))),
        ]
    elif shape == "hexagon":
        r = min(half_w, half_h)
        verts = [(cx + r * math.cos(math.radians(60 * i - 90)), cy + r * math.sin(math.radians(60 * i - 90))) for i in range(6)]
    elif shape == "pentagon":
        r = min(half_w, half_h)
        verts = [(cx + r * math.cos(math.radians(72 * i - 90)), cy + r * math.sin(math.radians(72 * i - 90))) for i in range(5)]
    elif shape == "star":
        r_outer = min(half_w, half_h)
        r_inner = r_outer * 0.45
        verts = []
        for i in range(5):
            angle_outer = math.radians(72 * i - 90)
            angle_inner = math.radians(72 * i - 90 + 36)
            verts.append((cx + r_outer * math.cos(angle_outer), cy + r_outer * math.sin(angle_outer)))
            verts.append((cx + r_inner * math.cos(angle_inner), cy + r_inner * math.sin(angle_inner)))
    elif shape == "diamond":
        verts = [
            (cx, cy - half_h),
            (cx + half_w * 0.6, cy),
            (cx, cy + half_h),
            (cx - half_w * 0.6, cy),
        ]
    else:
        raise ValueError(f"Unknown shape: {shape}")

    # Apply rotation
    if rotation != 0:
        angle_rad = math.radians(rotation)
        cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
        verts = [
            (cx + (x - cx) * cos_a - (y - cy) * sin_a,
             cy + (x - cx) * sin_a + (y - cy) * cos_a)
            for x, y in verts
        ]

    return verts


def draw_shape(surface: pygame.Surface, vertices: list[tuple[float, float]], color: tuple, thickness: int):
    """Draw the shape boundary on the surface."""
    pygame.draw.polygon(surface, color, vertices, thickness)


def point_in_polygon(px: float, py: float, vertices: list[tuple[float, float]]) -> bool:
    """Ray casting algorithm to check if point is inside polygon."""
    n = len(vertices)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def closest_edge_collision(bx: float, by: float, radius: float, vx: float, vy: float,
                           vertices: list[tuple[float, float]]) -> tuple[float, float, bool]:
    """Check collision with polygon edges and return reflected velocity.

    Returns (new_vx, new_vy, did_collide).
    """
    n = len(vertices)
    collided = False
    new_vx, new_vy = vx, vy

    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]

        # Edge vector and normal
        ex, ey = x2 - x1, y2 - y1
        edge_len = math.sqrt(ex * ex + ey * ey)
        if edge_len == 0:
            continue

        # Outward normal (pointing inward for our convex shapes)
        nx, ny = -ey / edge_len, ex / edge_len

        # Check if normal points inward (toward center)
        cx, cy = VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2
        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
        to_center_x, to_center_y = cx - mid_x, cy - mid_y
        if nx * to_center_x + ny * to_center_y < 0:
            nx, ny = -nx, -ny

        # Distance from ball center to edge line
        dx, dy = bx - x1, by - y1
        dist = dx * nx + dy * ny

        if dist < radius:
            # Project ball center onto edge to check if within segment
            t = (dx * ex / edge_len + dy * ey / edge_len) / edge_len
            if t < -0.1 or t > 1.1:
                # Check distance to vertices
                d1 = math.sqrt((bx - x1) ** 2 + (by - y1) ** 2)
                d2 = math.sqrt((bx - x2) ** 2 + (by - y2) ** 2)
                if d1 > radius and d2 > radius:
                    continue

            # Only reflect if moving toward the edge
            vel_dot_normal = new_vx * nx + new_vy * ny
            if vel_dot_normal < 0:
                # Reflect velocity
                new_vx = new_vx - 2 * vel_dot_normal * nx
                new_vy = new_vy - 2 * vel_dot_normal * ny
                collided = True

    return new_vx, new_vy, collided
