# ============================================================
# FILE: feature_recognition.py
# ASME CIE 2026 STUDENT HACKATHON
#
# COMPONENT:
#     Proposed Deterministic Geometry Map Pipeline
#
# PURPOSE:
#     Recognize engineering cylindrical features from
#     geometry_map.json using exact B-Rep geometry/topology.
#
# INPUT:
#     geometry_map.json
#
# OUTPUT:
#     features.json
#
# PIPELINE:
#
#     STEP
#       ↓
#     step_geometry_map.py
#       ↓
#     Exact B-Rep Geometry Map
#       ↓
#     INTERNAL / EXTERNAL cylinder classification
#       ↓
#     feature_recognition.py
#       ↓
#     THROUGH_HOLE
#     BLIND_HOLE_LIKE
#     CYLINDRICAL_HOLE_CANDIDATE
#     INTERNAL_CYLINDRICAL_CAVITY
#     LARGE_INTERNAL_CAVITY
#
# NOTE:
#     Classification is conservative.
#     No VLM/LLM is used here.
# ============================================================

import os
import json
import numpy as np


# ============================================================
# TOLERANCES
# ============================================================

DIAMETER_TOL = 1e-4
AXIS_PARALLEL_TOL = 1e-5
AXIS_DISTANCE_TOL = 1e-4
AXIAL_POSITION_TOL = 1e-3
BOUNDARY_DIAMETER_REL_TOL = 0.01


# ============================================================
# VECTOR HELPERS
# ============================================================

def normalize_vector(v):

    if v is None:
        return None

    arr = np.array(v, dtype=float)

    norm = np.linalg.norm(arr)

    if norm < 1e-12:
        return None

    return arr / norm


def axes_parallel(axis_a, axis_b, tolerance=AXIS_PARALLEL_TOL):

    a = normalize_vector(axis_a)
    b = normalize_vector(axis_b)

    if a is None or b is None:
        return False

    dot = abs(float(np.dot(a, b)))

    return abs(dot - 1.0) <= tolerance


def diameter_close(d1, d2, tolerance=DIAMETER_TOL):

    if d1 is None or d2 is None:
        return False

    return abs(d1 - d2) <= tolerance


# ============================================================
# AXIS GEOMETRY
# ============================================================

def axis_line_distance(point_a, point_b, axis_direction):

    if (
        point_a is None
        or point_b is None
        or axis_direction is None
    ):
        return float("inf")

    p1 = np.array(point_a, dtype=float)
    p2 = np.array(point_b, dtype=float)

    axis = normalize_vector(axis_direction)

    if axis is None:
        return float("inf")

    delta = p2 - p1

    axial_component = np.dot(delta, axis) * axis

    radial_component = delta - axial_component

    return float(np.linalg.norm(radial_component))


def axial_coordinate(point, axis_origin, axis_direction):

    if (
        point is None
        or axis_origin is None
        or axis_direction is None
    ):
        return None

    p = np.array(point, dtype=float)
    origin = np.array(axis_origin, dtype=float)

    axis = normalize_vector(axis_direction)

    if axis is None:
        return None

    return float(
        np.dot(
            p - origin,
            axis
        )
    )


# ============================================================
# LOOKUPS
# ============================================================

def create_lookup(records):

    return {
        item["id"]: item
        for item in records
    }


# ============================================================
# MODEL SIZE
# ============================================================

def get_model_max_extent(geometry_map):

    bbox = geometry_map.get("bbox", {})

    return max(
        float(bbox.get("xlen", 0)),
        float(bbox.get("ylen", 0)),
        float(bbox.get("zlen", 0))
    )


# ============================================================
# CIRCULAR BOUNDARY
# ============================================================

def circular_boundary_matches_cylinder(edge, cylinder_diameter):

    edge_diameter = edge.get("diameter")

    if (
        edge_diameter is None
        or cylinder_diameter is None
        or cylinder_diameter <= 0
    ):
        return False

    rel_error = abs(
        edge_diameter - cylinder_diameter
    ) / cylinder_diameter

    return rel_error <= BOUNDARY_DIAMETER_REL_TOL


def collect_matching_circular_boundaries(
    face,
    edge_lookup
):

    cylinder_diameter = face.get("diameter")

    boundaries = []

    for edge_id in face.get("edges", []):

        edge = edge_lookup.get(edge_id)

        if edge is None:
            continue

        if edge.get("geom_type") != "CIRCLE":
            continue

        if not circular_boundary_matches_cylinder(
            edge,
            cylinder_diameter
        ):
            continue

        boundaries.append({
            "edge_id": edge_id,
            "diameter": edge.get("diameter"),
            "center": edge.get("circle_center"),
            "axis": edge.get("axis"),
            "adjacent_faces": edge.get(
                "adjacent_faces",
                []
            )
        })

    return boundaries


# ============================================================
# ANALYZE ONE INTERNAL CYLINDER
# ============================================================

def analyze_internal_cylinder(
    face,
    face_lookup,
    edge_lookup,
    model_max_extent
):

    diameter = face.get("diameter")

    if (
        diameter is not None
        and model_max_extent > 0
    ):
        diameter_ratio = diameter / model_max_extent
    else:
        diameter_ratio = None

    # --------------------------------------------------------
    # SIZE CLASS
    # --------------------------------------------------------

    if diameter_ratio is None:
        size_class = "UNKNOWN"

    elif diameter_ratio <= 0.05:
        size_class = "SMALL"

    elif diameter_ratio <= 0.20:
        size_class = "MEDIUM"

    elif diameter_ratio <= 0.50:
        size_class = "LARGE"

    else:
        size_class = "VERY_LARGE"

    # --------------------------------------------------------
    # MATCHING CIRCULAR BOUNDARIES
    # --------------------------------------------------------

    boundaries = collect_matching_circular_boundaries(
        face,
        edge_lookup
    )

    # --------------------------------------------------------
    # NEIGHBOR TYPES
    # --------------------------------------------------------

    planar_neighbors = []
    cylindrical_neighbors = []
    conical_neighbors = []
    other_neighbors = []

    for neighbor_id in face.get(
        "adjacent_faces",
        []
    ):

        neighbor = face_lookup.get(
            neighbor_id
        )

        if neighbor is None:
            continue

        surface_type = neighbor.get(
            "surface_type"
        )

        if surface_type == "PLANE":
            planar_neighbors.append(neighbor_id)

        elif surface_type == "CYLINDER":
            cylindrical_neighbors.append(
                neighbor_id
            )

        elif surface_type == "CONE":
            conical_neighbors.append(
                neighbor_id
            )

        else:
            other_neighbors.append(
                neighbor_id
            )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    score = 0

    if (
        face.get("cylinder_orientation")
        == "INTERNAL"
    ):
        score += 4

    if len(boundaries) >= 1:
        score += 1

    if len(boundaries) >= 2:
        score += 2

    if len(planar_neighbors) >= 1:
        score += 1

    if len(planar_neighbors) >= 2:
        score += 1

    if size_class == "LARGE":
        score -= 2

    elif size_class == "VERY_LARGE":
        score -= 5

    return {
        "face_id": face["id"],
        "diameter": diameter,
        "radius": face.get("radius"),
        "axis": face.get("axis"),
        "axis_location": face.get(
            "axis_location"
        ),
        "center": face.get("center"),

        "diameter_ratio_to_model":
            diameter_ratio,

        "size_class":
            size_class,

        "matching_circular_boundaries":
            boundaries,

        "planar_neighbors":
            planar_neighbors,

        "cylindrical_neighbors":
            cylindrical_neighbors,

        "conical_neighbors":
            conical_neighbors,

        "other_neighbors":
            other_neighbors,

        "hole_score":
            score
    }


# ============================================================
# GROUP COAXIAL INTERNAL CYLINDERS
# ============================================================

def group_coaxial_features(candidates):

    groups = []

    used = set()

    for i, first in enumerate(candidates):

        if i in used:
            continue

        group = [first]
        used.add(i)

        for j in range(i + 1, len(candidates)):

            if j in used:
                continue

            second = candidates[j]

            if not diameter_close(
                first.get("diameter"),
                second.get("diameter")
            ):
                continue

            if not axes_parallel(
                first.get("axis"),
                second.get("axis")
            ):
                continue

            distance = axis_line_distance(
                first.get("axis_location"),
                second.get("axis_location"),
                first.get("axis")
            )

            if distance > AXIS_DISTANCE_TOL:
                continue

            group.append(second)
            used.add(j)

        groups.append(group)

    return groups


# ============================================================
# GROUP BOUNDARIES BY AXIAL POSITION
# ============================================================

def collect_group_boundary_data(
    group,
    edge_lookup,
    face_lookup
):

    if not group:
        return []

    axis = group[0].get("axis")
    axis_origin = group[0].get(
        "axis_location"
    )

    raw = []

    for member in group:

        for boundary in member.get(
            "matching_circular_boundaries",
            []
        ):

            center = boundary.get("center")

            position = axial_coordinate(
                center,
                axis_origin,
                axis
            )

            if position is None:
                continue

            adjacent_face_ids = boundary.get(
                "adjacent_faces",
                []
            )

            adjacent_types = []

            for face_id in adjacent_face_ids:

                face = face_lookup.get(
                    face_id
                )

                if face is None:
                    continue

                adjacent_types.append({
                    "face_id": face_id,
                    "surface_type": face.get(
                        "surface_type"
                    )
                })

            raw.append({
                "edge_id": boundary["edge_id"],
                "center": center,
                "axial_position": position,
                "adjacent_faces":
                    adjacent_types
            })

    # --------------------------------------------------------
    # Merge boundaries at almost same axial position
    # --------------------------------------------------------

    clusters = []

    for item in raw:

        matched_cluster = None

        for cluster in clusters:

            if abs(
                item["axial_position"]
                - cluster[
                    "axial_position"
                ]
            ) <= AXIAL_POSITION_TOL:

                matched_cluster = cluster
                break

        if matched_cluster is None:

            clusters.append({
                "axial_position":
                    item[
                        "axial_position"
                    ],

                "edge_ids": [
                    item["edge_id"]
                ],

                "adjacent_faces":
                    item[
                        "adjacent_faces"
                    ]
            })

        else:

            matched_cluster[
                "edge_ids"
            ].append(
                item["edge_id"]
            )

            existing = {
                x["face_id"]
                for x in matched_cluster[
                    "adjacent_faces"
                ]
            }

            for face_info in item[
                "adjacent_faces"
            ]:

                if (
                    face_info["face_id"]
                    not in existing
                ):

                    matched_cluster[
                        "adjacent_faces"
                    ].append(
                        face_info
                    )

    clusters.sort(
        key=lambda x: x["axial_position"]
    )

    return clusters


# ============================================================
# ANALYZE END CONDITIONS
# ============================================================

def analyze_boundary_end_conditions(
    boundary_clusters,
    group_face_ids
):

    results = []

    group_face_ids = set(
        group_face_ids
    )

    for cluster in boundary_clusters:

        outside_faces = [

            face_info

            for face_info in cluster[
                "adjacent_faces"
            ]

            if face_info[
                "face_id"
            ] not in group_face_ids
        ]

        planar_faces = [

            x

            for x in outside_faces

            if x["surface_type"]
            == "PLANE"
        ]

        conical_faces = [

            x

            for x in outside_faces

            if x["surface_type"]
            == "CONE"
        ]

        results.append({
            "axial_position":
                cluster[
                    "axial_position"
                ],

            "edge_ids":
                cluster["edge_ids"],

            "outside_faces":
                outside_faces,

            "planar_face_count":
                len(planar_faces),

            "conical_face_count":
                len(conical_faces),

            "has_planar_boundary":
                len(planar_faces) > 0
        })

    return results


# ============================================================
# FINAL CLASSIFICATION
# ============================================================

def classify_group(
    group,
    boundary_end_conditions
):

    representative = group[0]

    diameter = representative.get(
        "diameter"
    )

    size_class = representative.get(
        "size_class"
    )

    max_score = max(
        item.get(
            "hole_score",
            0
        )
        for item in group
    )

    # --------------------------------------------------------
    # VERY LARGE
    # --------------------------------------------------------

    if size_class == "VERY_LARGE":

        return (
            "LARGE_INTERNAL_CAVITY",
            1.0,
            "diameter_is_very_large_relative_to_model"
        )

    # --------------------------------------------------------
    # TWO OR MORE DISTINCT OPENINGS
    # --------------------------------------------------------

    if len(boundary_end_conditions) >= 2:

        first = boundary_end_conditions[0]
        last = boundary_end_conditions[-1]

        if (
            first[
                "has_planar_boundary"
            ]
            and
            last[
                "has_planar_boundary"
            ]
            and
            max_score >= 7
        ):

            return (
                "THROUGH_HOLE",
                0.95,
                "two_distinct_axial_boundaries_with_planar_neighbors"
            )

    # --------------------------------------------------------
    # ONE OPEN END
    # --------------------------------------------------------

    planar_end_count = sum(
        1
        for end in boundary_end_conditions
        if end[
            "has_planar_boundary"
        ]
    )

    if (
        len(boundary_end_conditions) >= 1
        and planar_end_count == 1
        and max_score >= 6
    ):

        return (
            "BLIND_HOLE_LIKE",
            0.75,
            "single_detected_planar_opening"
        )

    # --------------------------------------------------------
    # GENERIC LOCAL CYLINDRICAL HOLE CANDIDATE
    # --------------------------------------------------------

    if (
        max_score >= 6
        and size_class in [
            "SMALL",
            "MEDIUM"
        ]
    ):

        return (
            "CYLINDRICAL_HOLE_CANDIDATE",
            0.65,
            "internal_local_cylinder_with_hole_like_topology"
        )

    # --------------------------------------------------------
    # OTHERWISE CAVITY
    # --------------------------------------------------------

    return (
        "INTERNAL_CYLINDRICAL_CAVITY",
        0.60,
        "insufficient_topological_evidence_for_hole"
    )


# ============================================================
# BUILD FINAL FEATURE
# ============================================================

def build_feature(
    group,
    feature_index,
    edge_lookup,
    face_lookup
):

    representative = group[0]

    face_ids = [
        item["face_id"]
        for item in group
    ]

    boundaries = (
        collect_group_boundary_data(
            group,
            edge_lookup,
            face_lookup
        )
    )

    end_conditions = (
        analyze_boundary_end_conditions(
            boundaries,
            face_ids
        )
    )

    feature_type, confidence, reason = (
        classify_group(
            group,
            end_conditions
        )
    )

    max_score = max(
        item.get(
            "hole_score",
            0
        )
        for item in group
    )

    if len(boundaries) >= 2:

        axial_span = (
            boundaries[-1][
                "axial_position"
            ]
            -
            boundaries[0][
                "axial_position"
            ]
        )

        axial_span = abs(
            float(axial_span)
        )

    else:
        axial_span = None

    return {
        "id":
            f"FEATURE_{feature_index:03d}",

        "feature_type":
            feature_type,

        "classification_reason":
            reason,

        "confidence":
            confidence,

        "diameter":
            representative.get(
                "diameter"
            ),

        "radius":
            representative.get(
                "radius"
            ),

        "axis":
            representative.get(
                "axis"
            ),

        "axis_location":
            representative.get(
                "axis_location"
            ),

        "size_class":
            representative.get(
                "size_class"
            ),

        "diameter_ratio_to_model":
            representative.get(
                "diameter_ratio_to_model"
            ),

        "faces":
            face_ids,

        "face_count":
            len(face_ids),

        "hole_score":
            max_score,

        "boundary_count":
            len(boundaries),

        "boundary_data":
            boundaries,

        "end_conditions":
            end_conditions,

        "axial_span":
            axial_span
    }


# ============================================================
# MAIN RECOGNITION
# ============================================================

def recognize_features(
    geometry_map
):

    faces = geometry_map["faces"]
    edges = geometry_map["edges"]

    face_lookup = create_lookup(
        faces
    )

    edge_lookup = create_lookup(
        edges
    )

    model_max_extent = (
        get_model_max_extent(
            geometry_map
        )
    )

    # --------------------------------------------------------
    # INTERNAL CYLINDERS ONLY
    # --------------------------------------------------------

    internal_faces = [

        face

        for face in faces

        if (
            face.get(
                "surface_type"
            ) == "CYLINDER"

            and

            face.get(
                "cylinder_orientation"
            ) == "INTERNAL"
        )
    ]

    analyzed = [

        analyze_internal_cylinder(
            face,
            face_lookup,
            edge_lookup,
            model_max_extent
        )

        for face in internal_faces
    ]

    # --------------------------------------------------------
    # GROUP
    # --------------------------------------------------------

    groups = group_coaxial_features(
        analyzed
    )

    features = []

    for index, group in enumerate(
        groups,
        start=1
    ):

        feature = build_feature(
            group,
            index,
            edge_lookup,
            face_lookup
        )

        features.append(
            feature
        )

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    class_counts = {}

    for feature in features:

        feature_type = feature[
            "feature_type"
        ]

        class_counts[
            feature_type
        ] = (
            class_counts.get(
                feature_type,
                0
            )
            + 1
        )

    return {
        "model_max_extent":
            model_max_extent,

        "all_cylindrical_faces":
            sum(
                1
                for face in faces
                if face.get(
                    "surface_type"
                ) == "CYLINDER"
            ),

        "internal_cylindrical_faces":
            len(internal_faces),

        "grouped_internal_features":
            len(groups),

        "recognized_features":
            len(features),

        "feature_class_counts":
            class_counts,

        "features":
            features,

        "internal_cylinder_analysis":
            analyzed
    }


# ============================================================
# JSON API
# ============================================================

def recognize_features_from_json(
    geometry_map_json,
    output_json=None
):

    geometry_map_json = (
        os.path.abspath(
            geometry_map_json
        )
    )

    with open(
        geometry_map_json,
        "r",
        encoding="utf-8"
    ) as f:

        geometry_map = json.load(f)

    result = recognize_features(
        geometry_map
    )

    if output_json is not None:

        output_json = os.path.abspath(
            output_json
        )

        output_directory = (
            os.path.dirname(
                output_json
            )
        )

        if output_directory:

            os.makedirs(
                output_directory,
                exist_ok=True
            )

        with open(
            output_json,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                result,
                f,
                indent=4,
                ensure_ascii=False
            )

        print(
            "Feature recognition saved:"
        )

        print(
            output_json
        )

    return result