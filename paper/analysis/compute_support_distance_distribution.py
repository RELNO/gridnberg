#!/usr/bin/env python3
"""Compute source-vertex distances to the nearest selected elevation observation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import shapely
from pyogrio.raw import read


ROOT = Path(__file__).resolve().parents[2]
NETWORK_ARCHIVE = ROOT / "archive" / "data" / "44284_2025_383_MOESM3_ESM.zip"
NETWORK_MEMBER = "NYC_pednetwork_estimates_counts_2018-2019.geojson"
ELEVATION_ARCHIVE = ROOT / "archive" / "data" / "Planimetric_2022.gdb.zip"
OUTPUT_PATH = Path(__file__).with_name("support_distance_distribution.json")

FOOT_TO_METRE = 0.30480060960121924
SEARCH_RADIUS_METRES = 50.0
COARSE_BIN_EDGES = np.arange(0.0, SEARCH_RADIUS_METRES + 5.0, 5.0)


def vsi_zip(path: Path, member: str | None = None) -> str:
    suffix = f"/{member}" if member else ""
    return f"/vsizip/{path}{suffix}"


def rounded_list(values: np.ndarray, digits: int = 6) -> list[float]:
    return [round(float(value), digits) for value in values]


def main() -> None:
    if not NETWORK_ARCHIVE.exists() or not ELEVATION_ARCHIVE.exists():
        raise FileNotFoundError(
            "The archived NYCWalks and Planimetric source files are required."
        )

    _, _, network_wkb, _ = read(
        vsi_zip(NETWORK_ARCHIVE, NETWORK_MEMBER), columns=[]
    )
    network_geometry = shapely.from_wkb(network_wkb)
    source_vertices = np.unique(
        shapely.get_coordinates(network_geometry)[:, :2], axis=0
    )

    _, _, elevation_wkb, _ = read(
        vsi_zip(ELEVATION_ARCHIVE),
        layer="ELEVATION",
        columns=["FEATURE_CODE"],
        where="FEATURE_CODE = 3000",
    )
    elevation_geometry = shapely.from_wkb(elevation_wkb)
    elevation_xy_metres = (
        shapely.get_coordinates(elevation_geometry)[:, :2] * FOOT_TO_METRE
    )

    elevation_tree = shapely.STRtree(shapely.points(elevation_xy_metres))
    _, nearest_distances = elevation_tree.query_nearest(
        shapely.points(source_vertices),
        max_distance=SEARCH_RADIUS_METRES,
        return_distance=True,
        all_matches=False,
    )
    nearest_distances = np.asarray(nearest_distances, dtype=float)
    nearest_distances.sort()

    bin_counts, _ = np.histogram(nearest_distances, bins=COARSE_BIN_EDGES)
    quantile_probabilities = np.linspace(0.0, 1.0, 1001)
    quantile_distances = np.quantile(nearest_distances, quantile_probabilities)
    supported_count = int(nearest_distances.size)
    source_vertex_count = int(source_vertices.shape[0])

    result = {
        "source": {
            "network_archive": str(NETWORK_ARCHIVE.relative_to(ROOT)),
            "network_member": NETWORK_MEMBER,
            "elevation_archive": str(ELEVATION_ARCHIVE.relative_to(ROOT)),
            "elevation_layer": "ELEVATION",
            "elevation_filter": "FEATURE_CODE = 3000",
        },
        "population": {
            "unit": "unique source-network geometry vertex",
            "source_vertices": source_vertex_count,
            "supported_vertices": supported_count,
            "unsupported_vertices": source_vertex_count - supported_count,
            "search_radius_m": SEARCH_RADIUS_METRES,
        },
        "nearest_distance_m": {
            "minimum": round(float(nearest_distances[0]), 6),
            "mean": round(float(np.mean(nearest_distances)), 6),
            "standard_deviation": round(float(np.std(nearest_distances)), 6),
            "median": round(float(np.quantile(nearest_distances, 0.50)), 6),
            "p90": round(float(np.quantile(nearest_distances, 0.90)), 6),
            "p99": round(float(np.quantile(nearest_distances, 0.99)), 6),
            "maximum": round(float(nearest_distances[-1]), 6),
        },
        "histogram": {
            "bin_edges_m": rounded_list(COARSE_BIN_EDGES, 1),
            "counts": [int(value) for value in bin_counts],
            "shares_pct": rounded_list(100.0 * bin_counts / supported_count, 6),
        },
        "ecdf": {
            "cumulative_share_pct": rounded_list(
                100.0 * quantile_probabilities, 1
            ),
            "distance_m": rounded_list(quantile_distances, 6),
        },
    }

    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(
        f"Supported {supported_count:,} of {source_vertex_count:,} unique vertices; "
        f"median {result['nearest_distance_m']['median']:.4f} m; "
        f"p99 {result['nearest_distance_m']['p99']:.4f} m"
    )


if __name__ == "__main__":
    main()
