#!/usr/bin/env python3
"""Render the two route-comparison panels used in the Gridnberg paper."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = Path(__file__).with_name("dataset_summary.json")
ROUTING_PATH = ROOT / "app" / "data" / "routing-data.json"
OUTPUT_PATH = ROOT / "paper" / "figures" / "route_cases.pdf"

PAGE_WIDTH = 8.2 * 72
PAGE_HEIGHT = 3.75 * 72
OUTER_MARGIN = 14
GUTTER = 13
PANEL_WIDTH = (PAGE_WIDTH - 2 * OUTER_MARGIN - GUTTER) / 2
MAP_BOTTOM = 49
MAP_TOP = PAGE_HEIGHT - 27

ROUTE_STYLES = {
    "distance": (HexColor("#16BDEB"), None, 2.1),
    "comfort": (HexColor("#BB197F"), None, 3.0),
    "accessible": (HexColor("#F47F61"), [4, 2], 1.45),
}


def slope_color(maximum_grade: float) -> HexColor:
    if maximum_grade >= 25:
        return HexColor("#E8A08A")
    if maximum_grade >= 8.333333:
        return HexColor("#D9A4C5")
    if maximum_grade >= 5:
        return HexColor("#C8B0D6")
    return HexColor("#E3DFE9")


def route_bounds(case: dict[str, Any]) -> tuple[float, float, float, float]:
    points = [
        point
        for profile in case["profiles"].values()
        for point in profile["coordinates"]
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    x_padding = max((max_x - min_x) * 0.12, 0.0008)
    y_padding = max((max_y - min_y) * 0.12, 0.0008)
    return (
        min_x - x_padding,
        min_y - y_padding,
        max_x + x_padding,
        max_y + y_padding,
    )


def projector(
    bounds: tuple[float, float, float, float],
    panel_x: float,
) -> tuple[Any, tuple[float, float, float, float]]:
    min_x, min_y, max_x, max_y = bounds
    mid_lat = (min_y + max_y) / 2
    longitude_scale = math.cos(math.radians(mid_lat))
    world_width = (max_x - min_x) * longitude_scale
    world_height = max_y - min_y
    map_width = PANEL_WIDTH
    map_height = MAP_TOP - MAP_BOTTOM
    scale = min(map_width / world_width, map_height / world_height)
    drawn_width = world_width * scale
    drawn_height = world_height * scale
    left = panel_x + (PANEL_WIDTH - drawn_width) / 2
    bottom = MAP_BOTTOM + (map_height - drawn_height) / 2

    def project(point: list[float]) -> tuple[float, float]:
        return (
            left + (point[0] - min_x) * longitude_scale * scale,
            bottom + (point[1] - min_y) * scale,
        )

    return project, (left, bottom, left + drawn_width, bottom + drawn_height)


def intersects(
    segment: dict[str, Any], bounds: tuple[float, float, float, float]
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    xs = [point[0] for point in segment["g"]]
    ys = [point[1] for point in segment["g"]]
    return not (
        max(xs) < min_x or min(xs) > max_x or max(ys) < min_y or min(ys) > max_y
    )


def draw_polyline(
    pdf: canvas.Canvas,
    points: list[list[float]],
    project: Any,
    color: Any,
    width: float,
    dash: list[float] | None = None,
) -> None:
    if len(points) < 2:
        return
    path = pdf.beginPath()
    first_x, first_y = project(points[0])
    path.moveTo(first_x, first_y)
    for point in points[1:]:
        x, y = project(point)
        path.lineTo(x, y)
    pdf.setStrokeColor(color)
    pdf.setLineWidth(width)
    pdf.setLineCap(1)
    pdf.setLineJoin(1)
    pdf.setDash(dash or [])
    pdf.drawPath(path, stroke=1, fill=0)


def draw_marker(
    pdf: canvas.Canvas, point: list[float], project: Any, label: str
) -> None:
    x, y = project(point)
    pdf.setFillColor(white)
    pdf.setStrokeColor(HexColor("#25222B"))
    pdf.setLineWidth(0.8)
    pdf.circle(x, y, 6.3, stroke=1, fill=1)
    pdf.setFillColor(HexColor("#25222B"))
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.drawCentredString(x, y - 2.2, label)


def format_profile(label: str, profile: dict[str, Any]) -> str:
    return (
        f"{label}: {profile['length_m'] / 1000:.2f} km; "
        f"endpoint gain {profile['net_segment_gain_m']:.0f} m; "
        f"max {profile['maximum_reported_local_grade_pct']:.1f}%"
    )


def draw_panel(
    pdf: canvas.Canvas,
    panel_x: float,
    panel_label: str,
    case: dict[str, Any],
    segments: list[dict[str, Any]],
) -> None:
    bounds = route_bounds(case)
    project, clip_bounds = projector(bounds, panel_x)
    clip_left, clip_bottom, clip_right, clip_top = clip_bounds

    pdf.saveState()
    clip = pdf.beginPath()
    clip.rect(clip_left, clip_bottom, clip_right - clip_left, clip_top - clip_bottom)
    pdf.clipPath(clip, stroke=0, fill=0)
    pdf.setStrokeAlpha(0.82)
    for segment in segments:
        if intersects(segment, bounds):
            draw_polyline(
                pdf,
                segment["g"],
                project,
                slope_color(float(segment.get("st", 0.0))),
                0.42,
            )

    for profile_name in ("distance", "comfort", "accessible"):
        profile = case["profiles"][profile_name]
        draw_polyline(pdf, profile["coordinates"], project, white, 4.5)
    for profile_name in ("distance", "comfort", "accessible"):
        profile = case["profiles"][profile_name]
        color, dash, width = ROUTE_STYLES[profile_name]
        draw_polyline(pdf, profile["coordinates"], project, color, width, dash)

    draw_marker(pdf, case["snapped_origin"], project, "O")
    draw_marker(pdf, case["snapped_destination"], project, "D")
    pdf.restoreState()

    pdf.setFillColor(HexColor("#25222B"))
    pdf.setFont("Helvetica-Bold", 8.3)
    pdf.drawString(panel_x, PAGE_HEIGHT - 15, f"{panel_label}  {case['label']}")

    legend_y = 37
    legend_labels = {
        "distance": "Distance",
        "comfort": "Comfort",
        "accessible": "Accessibility-sensitive",
    }
    for profile_name in ("distance", "comfort", "accessible"):
        color, dash, width = ROUTE_STYLES[profile_name]
        pdf.setStrokeColor(color)
        pdf.setLineWidth(width)
        pdf.setDash(dash or [])
        pdf.line(panel_x, legend_y + 1.5, panel_x + 12, legend_y + 1.5)
        pdf.setFillColor(HexColor("#35313B"))
        pdf.setFont("Helvetica", 6.2)
        pdf.drawString(
            panel_x + 16,
            legend_y - 1,
            format_profile(legend_labels[profile_name], case["profiles"][profile_name]),
        )
        legend_y -= 10.5
    pdf.setDash([])


def main() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(OUTPUT_PATH), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf.setTitle("Gridnberg illustrative route comparisons")
    pdf.setAuthor("Ariel Noyman")
    pdf.setFillColor(white)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)

    draw_panel(
        pdf,
        OUTER_MARGIN,
        "A",
        summary["route_cases"]["morningside"],
        routing["segments"],
    )
    draw_panel(
        pdf,
        OUTER_MARGIN + PANEL_WIDTH + GUTTER,
        "B",
        summary["route_cases"]["st_george"],
        routing["segments"],
    )
    pdf.save()
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
