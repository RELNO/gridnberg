#!/usr/bin/env python3
"""Render the support-distance distribution figure used in the Gridnberg paper."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = Path(__file__).with_name("support_distance_distribution.json")
OUTPUT_PATH = ROOT / "paper" / "figures" / "support_distance_distribution.pdf"

PAGE_WIDTH = 7.22 * 72
PAGE_HEIGHT = 3.02 * 72
OUTER_MARGIN = 17
GUTTER = 31
PANEL_WIDTH = (PAGE_WIDTH - 2 * OUTER_MARGIN - GUTTER) / 2
PLOT_BOTTOM = 36
PLOT_TOP = PAGE_HEIGHT - 28
PLOT_LEFT_INSET = 36
PLOT_RIGHT_INSET = 7

INK = HexColor("#28242D")
MUTED = HexColor("#67616D")
GRID = HexColor("#DDD8E0")
BAR = HexColor("#B51A75")
CURVE = HexColor("#007D8A")
CURVE_LIGHT = HexColor("#D6EEF0")
MARKER = HexColor("#D24B35")


def format_integer(value: int) -> str:
    return f"{value:,}"


def draw_panel_heading(
    pdf: canvas.Canvas, panel_x: float, panel_label: str, title: str
) -> None:
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 9.0)
    pdf.drawString(panel_x, PAGE_HEIGHT - 16, panel_label)
    pdf.setFont("Helvetica-Bold", 8.2)
    pdf.drawString(panel_x + 15, PAGE_HEIGHT - 16, title)


def draw_grid_and_axes(
    pdf: canvas.Canvas,
    left: float,
    bottom: float,
    right: float,
    top: float,
    x_ticks: Iterable[float],
    y_ticks: Iterable[float],
    x_max: float,
    y_max: float,
    y_label: str,
) -> None:
    pdf.setLineWidth(0.45)
    pdf.setFont("Helvetica", 6.4)
    for value in y_ticks:
        y = bottom + value / y_max * (top - bottom)
        pdf.setStrokeColor(GRID)
        pdf.line(left, y, right, y)
        pdf.setFillColor(MUTED)
        pdf.drawRightString(left - 5, y - 2.2, f"{value:g}")

    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.65)
    pdf.line(left, bottom, right, bottom)
    pdf.line(left, bottom, left, top)

    for value in x_ticks:
        x = left + value / x_max * (right - left)
        pdf.line(x, bottom, x, bottom - 2.5)
        pdf.setFillColor(MUTED)
        pdf.drawCentredString(x, bottom - 10, f"{value:g}")

    pdf.saveState()
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 7.0)
    pdf.translate(left - 28, (bottom + top) / 2)
    pdf.rotate(90)
    pdf.drawCentredString(0, 0, y_label)
    pdf.restoreState()


def draw_histogram(pdf: canvas.Canvas, panel_x: float, data: dict) -> None:
    draw_panel_heading(pdf, panel_x, "A", "Nearest-observation distance")
    left = panel_x + PLOT_LEFT_INSET
    right = panel_x + PANEL_WIDTH - PLOT_RIGHT_INSET
    bottom = PLOT_BOTTOM
    top = PLOT_TOP
    y_max = 35.0
    shares = data["histogram"]["shares_pct"]

    draw_grid_and_axes(
        pdf,
        left,
        bottom,
        right,
        top,
        x_ticks=(0, 10, 20, 30, 40, 50),
        y_ticks=(0, 10, 20, 30),
        x_max=50,
        y_max=y_max,
        y_label="Supported vertices (%)",
    )

    bar_slot = (right - left) / len(shares)
    for index, share in enumerate(shares):
        x = left + index * bar_slot + 1.1
        width = bar_slot - 2.2
        height = share / y_max * (top - bottom)
        pdf.setFillColor(BAR)
        pdf.rect(x, bottom, width, height, stroke=0, fill=1)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 5.8)
        pdf.drawCentredString(x + width / 2, bottom + height + 3.2, f"{share:.1f}")

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 7.0)
    pdf.drawCentredString(
        (left + right) / 2,
        8,
        "Distance to nearest contributing elevation observation (m)",
    )
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 5.8)
    pdf.drawRightString(
        right,
        top + 6,
        f"5 m bins; N = {format_integer(data['population']['supported_vertices'])}",
    )


def draw_percentile_marker(
    pdf: canvas.Canvas,
    left: float,
    bottom: float,
    right: float,
    top: float,
    distance: float,
    percentile: float,
    label: str,
    align: str,
) -> None:
    x = left + distance / 50.0 * (right - left)
    y = bottom + percentile / 100.0 * (top - bottom)
    pdf.setStrokeColor(MARKER)
    pdf.setLineWidth(0.7)
    pdf.setDash(2.2, 1.8)
    pdf.line(x, bottom, x, y)
    pdf.setDash([])
    pdf.setFillColor(white)
    pdf.setStrokeColor(MARKER)
    pdf.setLineWidth(0.8)
    pdf.circle(x, y, 2.4, stroke=1, fill=1)

    pdf.setFillColor(MARKER)
    pdf.setFont("Helvetica-Bold", 6.0)
    text_y = min(y + 5.0, top - 2)
    if align == "left":
        pdf.drawRightString(x - 3.5, text_y, label)
    else:
        pdf.drawString(x + 3.5, text_y, label)


def draw_ecdf(pdf: canvas.Canvas, panel_x: float, data: dict) -> None:
    draw_panel_heading(pdf, panel_x, "B", "Cumulative distribution")
    left = panel_x + PLOT_LEFT_INSET
    right = panel_x + PANEL_WIDTH - PLOT_RIGHT_INSET
    bottom = PLOT_BOTTOM
    top = PLOT_TOP

    draw_grid_and_axes(
        pdf,
        left,
        bottom,
        right,
        top,
        x_ticks=(0, 10, 20, 30, 40, 50),
        y_ticks=(0, 25, 50, 75, 100),
        x_max=50,
        y_max=100,
        y_label="Cumulative supported vertices (%)",
    )

    distances = data["ecdf"]["distance_m"]
    cumulative = data["ecdf"]["cumulative_share_pct"]
    fill_path = pdf.beginPath()
    fill_path.moveTo(left, bottom)
    for distance, share in zip(distances, cumulative):
        x = left + distance / 50.0 * (right - left)
        y = bottom + share / 100.0 * (top - bottom)
        fill_path.lineTo(x, y)
    fill_path.lineTo(right, bottom)
    fill_path.close()
    pdf.setFillColor(CURVE_LIGHT)
    pdf.drawPath(fill_path, stroke=0, fill=1)

    curve_path = pdf.beginPath()
    curve_path.moveTo(left, bottom)
    for distance, share in zip(distances, cumulative):
        x = left + distance / 50.0 * (right - left)
        y = bottom + share / 100.0 * (top - bottom)
        curve_path.lineTo(x, y)
    pdf.setStrokeColor(CURVE)
    pdf.setLineWidth(1.6)
    pdf.drawPath(curve_path, stroke=1, fill=0)

    stats = data["nearest_distance_m"]
    draw_percentile_marker(
        pdf, left, bottom, right, top, stats["median"], 50, "Median 10.14 m", "right"
    )
    draw_percentile_marker(
        pdf, left, bottom, right, top, stats["p90"], 90, "P90 19.97 m", "left"
    )
    draw_percentile_marker(
        pdf, left, bottom, right, top, stats["p99"], 99, "P99 36.52 m", "left"
    )

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 7.0)
    pdf.drawCentredString(
        (left + right) / 2,
        8,
        "Distance to nearest contributing elevation observation (m)",
    )
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 5.8)
    pdf.drawRightString(right, top + 6, "Conditional on support within 50 m")


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(OUTPUT_PATH), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf.setTitle("Distance from source vertices to contributing elevation observations")
    pdf.setAuthor("Ariel Noyman")
    pdf.setSubject("Distribution of nearest contributing-observation distance")
    pdf.setFillColor(white)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)

    draw_histogram(pdf, OUTER_MARGIN, data)
    draw_ecdf(pdf, OUTER_MARGIN + PANEL_WIDTH + GUTTER, data)
    pdf.save()
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
