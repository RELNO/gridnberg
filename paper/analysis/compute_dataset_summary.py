#!/usr/bin/env python3
"""Compute reproducible descriptive and route-comparison statistics for Gridnberg.

The script deliberately uses only the Python standard library so that the paper's
reported summary can be regenerated without adding another analysis dependency.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
NETWORK_CSV = ROOT / "outputs" / "nyc_ped_net_radius50m_routing_network.csv"
NODES_CSV = ROOT / "outputs" / "nyc_ped_net_radius50m_routing_nodes.csv"
ROUTING_JSON = ROOT / "app" / "data" / "routing-data.json"


ROUTE_CASES = {
    "south_slope": {
        "label": "South Slope, Brooklyn",
        "origin": (-73.989501, 40.665623),
        "destination": (-73.97337292730204, 40.66892073171586),
    },
    "morningside": {
        "label": "Morningside Heights--Harlem, Manhattan",
        "origin": (-73.9637, 40.8084),
        "destination": (-73.9494, 40.8111),
    },
    "washington_heights": {
        "label": "Washington Heights, Manhattan",
        "origin": (-73.9418, 40.8501),
        "destination": (-73.9280, 40.8468),
    },
    "riverdale": {
        "label": "Riverdale, Bronx",
        "origin": (-73.9107, 40.8940),
        "destination": (-73.8970, 40.8950),
    },
    "st_george": {
        "label": "St. George--Tompkinsville, Staten Island",
        "origin": (-74.0772, 40.6434),
        "destination": (-74.0876, 40.6350),
    },
}


def quantile(sorted_values: list[float], probability: float) -> float:
    """Return a linearly interpolated sample quantile."""
    if not sorted_values:
        return math.nan
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def distribution(values: Iterable[float]) -> dict[str, float]:
    data = sorted(values)
    return {
        "min": data[0],
        "p25": quantile(data, 0.25),
        "median": quantile(data, 0.50),
        "p75": quantile(data, 0.75),
        "p90": quantile(data, 0.90),
        "p95": quantile(data, 0.95),
        "p99": quantile(data, 0.99),
        "max": data[-1],
        "mean": sum(data) / len(data),
    }


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.component_size = [1] * size

    def find(self, item: int) -> int:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            parent = self.parent[item]
            self.parent[item] = root
            item = parent
        return root

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.component_size[left_root] < self.component_size[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        self.component_size[left_root] += self.component_size[right_root]


def summarize_tables() -> dict[str, Any]:
    with NODES_CSV.open(newline="", encoding="utf-8") as file:
        node_rows = list(csv.DictReader(file))

    node_count = len(node_rows)
    elevations = [float(row["z_m"]) for row in node_rows]
    union_find = UnionFind(node_count)
    degrees = [0] * node_count

    lengths: list[float] = []
    average_abs_grades: list[float] = []
    maximum_abs_grades: list[float] = []
    comfort_ratios: list[float] = []
    accessible_ratios: list[float] = []
    point_counts: Counter[int] = Counter()
    endpoint_pairs: Counter[tuple[int, int]] = Counter()
    self_loops = 0
    asymmetric_comfort = 0
    asymmetric_accessible = 0

    with NETWORK_CSV.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            node_a = int(row["node_a"])
            node_b = int(row["node_b"])
            length = float(row["length_m"])
            average_abs_grade = abs(float(row["avg_grade_a_to_b_pct"]))
            maximum_abs_grade = float(row["max_abs_grade_pct"])
            distance_cost = float(row["cost_distance"])
            comfort_forward = float(row["cost_slope_a_to_b"])
            comfort_reverse = float(row["cost_slope_b_to_a"])
            accessible_forward = float(row["cost_accessible_a_to_b"])
            accessible_reverse = float(row["cost_accessible_b_to_a"])

            lengths.append(length)
            average_abs_grades.append(average_abs_grade)
            maximum_abs_grades.append(maximum_abs_grade)
            comfort_ratios.extend((comfort_forward / distance_cost, comfort_reverse / distance_cost))
            accessible_ratios.extend((accessible_forward / distance_cost, accessible_reverse / distance_cost))
            point_counts[int(row["point_count"])] += 1

            union_find.union(node_a, node_b)
            degrees[node_a] += 1
            degrees[node_b] += 1
            endpoint_pairs[tuple(sorted((node_a, node_b)))] += 1
            self_loops += node_a == node_b
            asymmetric_comfort += not math.isclose(comfort_forward, comfort_reverse, abs_tol=1e-6)
            asymmetric_accessible += not math.isclose(accessible_forward, accessible_reverse, abs_tol=1e-6)

    segment_count = len(lengths)
    component_nodes: Counter[int] = Counter(union_find.find(node) for node in range(node_count))
    component_edges: Counter[int] = Counter()
    with NETWORK_CSV.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            component_edges[union_find.find(int(row["node_a"]))] += 1

    largest_root, largest_node_count = component_nodes.most_common(1)[0]
    grade_thresholds = (2.0, 5.0, 8.333333333, 15.0, 25.0, 50.0, 100.0)

    return {
        "node_count": node_count,
        "segment_count": segment_count,
        "directed_edge_count": segment_count * 2,
        "total_horizontal_length_km": sum(lengths) / 1000,
        "segment_length_m": distribution(lengths),
        "node_elevation_m": distribution(elevations),
        "average_absolute_grade_pct": distribution(average_abs_grades),
        "maximum_local_absolute_grade_pct": distribution(maximum_abs_grades),
        "segments_at_or_above_max_grade_threshold": {
            f"{threshold:g}": {
                "count": sum(value >= threshold for value in maximum_abs_grades),
                "percent": 100 * sum(value >= threshold for value in maximum_abs_grades) / segment_count,
            }
            for threshold in grade_thresholds
        },
        "segments_at_or_above_average_grade_threshold": {
            f"{threshold:g}": {
                "count": sum(value >= threshold for value in average_abs_grades),
                "percent": 100 * sum(value >= threshold for value in average_abs_grades) / segment_count,
            }
            for threshold in grade_thresholds
        },
        "cost_multiplier": {
            "comfort": distribution(comfort_ratios),
            "accessible": distribution(accessible_ratios),
        },
        "direction_asymmetry": {
            "comfort_segment_count": asymmetric_comfort,
            "comfort_percent": 100 * asymmetric_comfort / segment_count,
            "accessible_segment_count": asymmetric_accessible,
            "accessible_percent": 100 * asymmetric_accessible / segment_count,
        },
        "graph": {
            "connected_component_count": len(component_nodes),
            "largest_component_nodes": largest_node_count,
            "largest_component_node_percent": 100 * largest_node_count / node_count,
            "largest_component_edges": component_edges[largest_root],
            "self_loops": self_loops,
            "endpoint_pairs_with_parallel_segments": sum(count > 1 for count in endpoint_pairs.values()),
            "segments_in_parallel_pairs": sum(count for count in endpoint_pairs.values() if count > 1),
            "degree": distribution([float(value) for value in degrees]),
        },
        "geometry": {
            "two_vertex_segment_count": point_counts[2],
            "two_vertex_segment_percent": 100 * point_counts[2] / segment_count,
            "segments_shorter_than_1_m": sum(length < 1 for length in lengths),
            "segments_shorter_than_1_m_percent": 100 * sum(length < 1 for length in lengths) / segment_count,
            "maximum_point_count": max(point_counts),
        },
    }


def nearest_node(nodes: list[list[float]], lng_lat: tuple[float, float]) -> int:
    lng, lat = lng_lat
    longitude_scale = math.cos(math.radians(lat))
    return min(
        range(len(nodes)),
        key=lambda index: ((nodes[index][0] - lng) * longitude_scale) ** 2
        + (nodes[index][1] - lat) ** 2,
    )


def build_adjacency(data: dict[str, Any]) -> list[list[tuple[int, int, bool, list[float], float]]]:
    adjacency: list[list[tuple[int, int, bool, list[float], float]]] = [
        [] for _ in data["nodes"]
    ]
    for segment_index, segment in enumerate(data["segments"]):
        adjacency[segment["a"]].append(
            (segment["b"], segment_index, False, segment["c"], segment.get("dz", 0.0))
        )
        adjacency[segment["b"]].append(
            (segment["a"], segment_index, True, segment["c"], -segment.get("dz", 0.0))
        )
    return adjacency


def shortest_path(
    adjacency: list[list[tuple[int, int, bool, list[float], float]]],
    start: int,
    end: int,
    cost_index_forward: int,
    cost_index_reverse: int,
) -> tuple[float, list[tuple[int, bool]]]:
    distances = [math.inf] * len(adjacency)
    previous: list[tuple[int, int, bool] | None] = [None] * len(adjacency)
    distances[start] = 0.0
    queue = [(0.0, start)]

    while queue:
        current_cost, current_node = heapq.heappop(queue)
        if current_cost != distances[current_node]:
            continue
        if current_node == end:
            break
        for next_node, segment_index, reverse, costs, _dz in adjacency[current_node]:
            edge_cost = costs[cost_index_reverse if reverse else cost_index_forward]
            proposed_cost = current_cost + edge_cost
            if proposed_cost < distances[next_node]:
                distances[next_node] = proposed_cost
                previous[next_node] = (current_node, segment_index, reverse)
                heapq.heappush(queue, (proposed_cost, next_node))

    if not math.isfinite(distances[end]):
        return math.inf, []

    steps: list[tuple[int, bool]] = []
    cursor = end
    while cursor != start:
        prior = previous[cursor]
        if prior is None:
            return math.inf, []
        cursor, segment_index, reverse = prior
        steps.append((segment_index, reverse))
    steps.reverse()
    return distances[end], steps


def summarize_route(
    data: dict[str, Any], cost: float, steps: list[tuple[int, bool]]
) -> dict[str, Any]:
    length = 0.0
    gain = 0.0
    loss = 0.0
    maximum_grade = 0.0
    segment_ids: list[int] = []
    coordinates: list[list[float]] = []
    for segment_index, reverse in steps:
        segment = data["segments"][segment_index]
        length += segment.get("l", 0.0)
        change = -segment.get("dz", 0.0) if reverse else segment.get("dz", 0.0)
        gain += max(0.0, change)
        loss += max(0.0, -change)
        maximum_grade = max(maximum_grade, segment.get("st", 0.0))
        segment_ids.append(int(segment["id"]))
        next_line = list(reversed(segment["g"])) if reverse else segment["g"]
        if not coordinates:
            coordinates.extend(next_line)
        elif next_line:
            if coordinates[-1] == next_line[0]:
                coordinates.extend(next_line[1:])
            elif coordinates[-1] == next_line[-1]:
                coordinates.extend(list(reversed(next_line))[1:])
            else:
                coordinates.extend(next_line)
    return {
        "routing_cost": cost,
        "length_m": length,
        "net_segment_gain_m": gain,
        "net_segment_loss_m": loss,
        "maximum_reported_local_grade_pct": maximum_grade,
        "segment_count": len(steps),
        "segment_ids": segment_ids,
        "coordinates": coordinates,
    }


def summarize_route_cases() -> dict[str, Any]:
    with ROUTING_JSON.open(encoding="utf-8") as file:
        data = json.load(file)
    adjacency = build_adjacency(data)
    profiles = {
        "distance": (0, 0),
        "comfort": (1, 2),
        "accessible": (3, 4),
    }

    results: dict[str, Any] = {}
    for key, case in ROUTE_CASES.items():
        start = nearest_node(data["nodes"], case["origin"])
        end = nearest_node(data["nodes"], case["destination"])
        route_results: dict[str, Any] = {}
        for profile, (forward_index, reverse_index) in profiles.items():
            cost, steps = shortest_path(
                adjacency, start, end, forward_index, reverse_index
            )
            route_results[profile] = summarize_route(data, cost, steps)

        distance_ids = set(route_results["distance"]["segment_ids"])
        for profile in ("comfort", "accessible"):
            profile_ids = set(route_results[profile]["segment_ids"])
            union = distance_ids | profile_ids
            route_results[profile]["jaccard_segment_overlap_with_distance"] = (
                len(distance_ids & profile_ids) / len(union) if union else 1.0
            )
            route_results[profile]["length_change_from_distance_pct"] = (
                100
                * (
                    route_results[profile]["length_m"]
                    - route_results["distance"]["length_m"]
                )
                / route_results["distance"]["length_m"]
            )

        results[key] = {
            "label": case["label"],
            "requested_origin": case["origin"],
            "requested_destination": case["destination"],
            "snapped_origin_node": start,
            "snapped_destination_node": end,
            "snapped_origin": data["nodes"][start][:2],
            "snapped_destination": data["nodes"][end][:2],
            "profiles": route_results,
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("dataset_summary.json"),
    )
    parser.add_argument(
        "--skip-routes",
        action="store_true",
        help="Skip loading the browser JSON and computing example routes.",
    )
    args = parser.parse_args()

    results: dict[str, Any] = {"tables": summarize_tables()}
    if not args.skip_routes:
        results["route_cases"] = summarize_route_cases()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
