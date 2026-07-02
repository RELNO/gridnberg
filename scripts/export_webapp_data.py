#!/usr/bin/env python3
"""Export the routing GeoPackage into a compact browser routing JSON file."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import struct
import time
from pathlib import Path
from typing import Iterable

from pyproj import Transformer
from shapely import from_wkb


GPKG_ENVELOPE_BYTES = {
    0: 0,
    1: 32,
    2: 48,
    3: 48,
    4: 64,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export routing_network and routing_nodes for the web app."
    )
    parser.add_argument(
        "--gpkg",
        default="qgis/nyc_ped_net_radius50m_routing.gpkg",
        help="Input GeoPackage produced by the notebook.",
    )
    parser.add_argument(
        "--out",
        default="app/data/routing-data.json",
        help="Output JSON file used by app/app.js.",
    )
    parser.add_argument(
        "--display-out",
        default="app/data/network-display.geojson",
        help="Grouped GeoJSON used by MapLibre for drawing the network.",
    )
    parser.add_argument(
        "--coord-precision",
        type=int,
        default=6,
        help="Decimal places for WGS84 lon/lat coordinates.",
    )
    parser.add_argument(
        "--metric-precision",
        type=int,
        default=3,
        help="Decimal places for metric attributes and costs.",
    )
    return parser.parse_args()


def gpkg_geometry_to_shape(blob: bytes):
    """Return a Shapely geometry from a GeoPackage geometry blob."""
    if blob[:2] != b"GP":
        return from_wkb(blob)

    flags = blob[3]
    endian = "<" if flags & 1 else ">"
    # Read the SRS id to validate the byte order and header, even though the
    # transformer is configured from the GeoPackage metadata below.
    struct.unpack(endian + "i", blob[4:8])[0]
    envelope_indicator = (flags >> 1) & 0b111
    offset = 8 + GPKG_ENVELOPE_BYTES.get(envelope_indicator, 0)
    return from_wkb(blob[offset:])


def round_number(value: float | None, precision: int) -> float | None:
    if value is None:
        return None
    return round(float(value), precision)


def transform_xy(
    transformer: Transformer,
    coords: Iterable[tuple[float, float]],
    precision: int,
) -> list[list[float]]:
    xs, ys = zip(*coords)
    lon, lat = transformer.transform(xs, ys)
    return [[round(x, precision), round(y, precision)] for x, y in zip(lon, lat)]


def read_srs_id(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT srs_id
        FROM gpkg_geometry_columns
        WHERE table_name = 'routing_network'
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("Could not find routing_network in gpkg_geometry_columns.")
    return int(row[0])


def export_nodes(
    connection: sqlite3.Connection,
    transformer: Transformer,
    coord_precision: int,
    metric_precision: int,
) -> list[list[float]]:
    rows = connection.execute(
        "SELECT node_id, x, y, z_m FROM routing_nodes ORDER BY node_id"
    ).fetchall()
    if not rows:
        raise RuntimeError("routing_nodes is empty.")

    node_ids = [int(row[0]) for row in rows]
    expected = list(range(len(rows)))
    if node_ids != expected:
        raise RuntimeError(
            "routing_nodes.node_id must be contiguous from 0 for browser indexing."
        )

    lon_lat = transform_xy(
        transformer,
        ((float(row[1]), float(row[2])) for row in rows),
        coord_precision,
    )
    nodes = []
    for xy, row in zip(lon_lat, rows):
        nodes.append([xy[0], xy[1], round_number(row[3], metric_precision)])
    return nodes


def export_segments(
    connection: sqlite3.Connection,
    transformer: Transformer,
    coord_precision: int,
    metric_precision: int,
) -> tuple[list[dict], list[dict]]:
    rows = connection.execute(
        """
        SELECT
            segment_id,
            node_a,
            node_b,
            length_m,
            net_change_a_to_b_m,
            avg_grade_a_to_b_pct,
            max_abs_grade_pct,
            cost_distance,
            cost_slope_a_to_b,
            cost_slope_b_to_a,
            cost_accessible_a_to_b,
            cost_accessible_b_to_a,
            geom
        FROM routing_network
        ORDER BY segment_id
        """
    )

    segments = []
    display_bins = [
        {"label": "0-2", "steep": 1.0, "lines": []},
        {"label": "2-5", "steep": 3.5, "lines": []},
        {"label": "5-8.33", "steep": 6.5, "lines": []},
        {"label": "8.33-15", "steep": 11.5, "lines": []},
        {"label": "15-25", "steep": 20.0, "lines": []},
        {"label": "25+", "steep": 35.0, "lines": []},
    ]

    def display_bin_index(steepness: float | None) -> int:
        value = 0.0 if steepness is None else float(steepness)
        if value < 2:
            return 0
        if value < 5:
            return 1
        if value < 8.33:
            return 2
        if value < 15:
            return 3
        if value < 25:
            return 4
        return 5

    for row in rows:
        geom = gpkg_geometry_to_shape(row[12])
        coords = [(float(x), float(y)) for x, y, *_ in geom.coords]
        lon_lat = transform_xy(transformer, coords, coord_precision)

        cost_distance = round_number(row[7], metric_precision)
        steepness = round_number(row[6], metric_precision)
        display_bins[display_bin_index(steepness)]["lines"].append(lon_lat)
        segments.append(
            {
                "id": int(row[0]),
                "a": int(row[1]),
                "b": int(row[2]),
                "l": round_number(row[3], metric_precision),
                "dz": round_number(row[4], metric_precision),
                "gr": round_number(row[5], metric_precision),
                "st": steepness,
                "c": [
                    cost_distance,
                    round_number(row[8], metric_precision),
                    round_number(row[9], metric_precision),
                    round_number(row[10], metric_precision),
                    round_number(row[11], metric_precision),
                ],
                "g": lon_lat,
            }
        )

    display_features = []
    for display_bin in display_bins:
        if not display_bin["lines"]:
            continue
        display_features.append(
            {
                "type": "Feature",
                "properties": {
                    "bin": display_bin["label"],
                    "steep": display_bin["steep"],
                },
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": display_bin["lines"],
                },
            }
        )

    return segments, display_features


def main() -> None:
    args = parse_args()
    gpkg_path = Path(args.gpkg)
    out_path = Path(args.out)
    display_out_path = Path(args.display_out)

    start = time.time()
    if not gpkg_path.exists():
        raise FileNotFoundError(gpkg_path)

    connection = sqlite3.connect(gpkg_path)
    srs_id = read_srs_id(connection)
    transformer = Transformer.from_crs(f"EPSG:{srs_id}", "EPSG:4326", always_xy=True)

    print(f"Reading nodes from {gpkg_path}...")
    nodes = export_nodes(
        connection, transformer, args.coord_precision, args.metric_precision
    )
    print(f"Exported {len(nodes):,} nodes.")

    print("Reading segments and transforming geometry...")
    segments, display_features = export_segments(
        connection, transformer, args.coord_precision, args.metric_precision
    )
    print(f"Exported {len(segments):,} segments.")

    payload = {
        "meta": {
            "source": str(gpkg_path),
            "source_srs": f"EPSG:{srs_id}",
            "target_srs": "EPSG:4326",
            "node_schema": ["lon", "lat", "z_m"],
            "segment_schema": {
                "id": "segment_id",
                "a": "node_a",
                "b": "node_b",
                "l": "length_m",
                "dz": "net_change_a_to_b_m",
                "gr": "avg_grade_a_to_b_pct",
                "st": "max_abs_grade_pct",
                "c": [
                    "cost_distance",
                    "cost_slope_a_to_b",
                    "cost_slope_b_to_a",
                    "cost_accessible_a_to_b",
                    "cost_accessible_b_to_a",
                ],
                "g": "WGS84 line coordinates",
            },
        },
        "nodes": nodes,
        "segments": segments,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))

    display_payload = {
        "type": "FeatureCollection",
        "features": display_features,
    }
    display_out_path.parent.mkdir(parents=True, exist_ok=True)
    with display_out_path.open("w", encoding="utf-8") as f:
        json.dump(display_payload, f, separators=(",", ":"))

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    display_size_mb = os.path.getsize(display_out_path) / (1024 * 1024)
    elapsed = time.time() - start
    print(f"Wrote {out_path} ({size_mb:.1f} MB) in {elapsed:.1f} seconds.")
    print(f"Wrote {display_out_path} ({display_size_mb:.1f} MB).")


if __name__ == "__main__":
    main()
