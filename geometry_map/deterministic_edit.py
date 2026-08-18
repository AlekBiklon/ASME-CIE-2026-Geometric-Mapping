# ============================================================
# FILE: deterministic_edit.py
# ASME CIE 2026 STUDENT HACKATHON
#
# METHOD:
#     Semi-Automatic Geometric Mapping
#     + Robust Deterministic CAD Editing
#
# SUPPORTED OPERATIONS:
#
#     ADD_HOLE
#     FILLET
#     CHAMFER
#
# ROBUST CHAMFER STRATEGY:
#
#     selected B-Rep edges
#           ↓
#     owner-solid mapping
#           ↓
#     connectivity graph
#           ↓
#     connected contours / groups
#           ↓
#     try requested distance
#           ↓
#     if fail:
#         adaptive distance reduction
#           ↓
#     if whole contour still fails:
#         individual-edge fallback
#           ↓
#     impossible edge:
#         SKIPPED
#
# FINAL STATUSES:
#
#     FULL_SUCCESS
#     ADAPTIVE_SUCCESS
#     PARTIAL_SUCCESS
#     FAILED
#
# IMPORTANT:
#     Ground Truth is NOT used to generate geometry.
# ============================================================


import os
import json
import math
import traceback

import numpy as np
import cadquery as cq

from cadquery.occ_impl.shapes import (
    fillet as cq_shape_fillet,
    chamfer as cq_shape_chamfer,
)


# ============================================================
# GLOBAL ROBUSTNESS PARAMETERS
# ============================================================

EDGE_MATCH_TOL = 1e-6

VERTEX_CONNECT_TOL = 1e-5

CHAMFER_ADAPTIVE_STEP_MM = 0.05

CHAMFER_MIN_DISTANCE_MM = 0.05

FILLET_ADAPTIVE_STEP_MM = 0.05
FILLET_MIN_RADIUS_MM = 0.05


# ============================================================
# GENERIC HELPERS
# ============================================================

def normalize(vector):

    vector = np.asarray(
        vector,
        dtype=float
    )

    norm = np.linalg.norm(
        vector
    )

    if norm < 1e-12:

        raise ValueError(
            "Cannot normalize zero-length vector."
        )

    return vector / norm


def edge_id_to_index(edge_id):

    if not isinstance(
        edge_id,
        str
    ):

        raise ValueError(
            f"Invalid edge ID type: {edge_id}"
        )

    if not edge_id.startswith(
        "E"
    ):

        raise ValueError(
            f"Invalid edge ID: {edge_id}"
        )

    return int(
        edge_id[1:]
    ) - 1


def face_id_to_index(face_id):

    if not isinstance(
        face_id,
        str
    ):

        raise ValueError(
            f"Invalid face ID type: {face_id}"
        )

    if not face_id.startswith(
        "F"
    ):

        raise ValueError(
            f"Invalid face ID: {face_id}"
        )

    return int(
        face_id[1:]
    ) - 1


def vertex_xyz(vertex):

    point = vertex.Center()

    return np.array(
        [
            float(point.x),
            float(point.y),
            float(point.z)
        ],
        dtype=float
    )


def points_close(
    p1,
    p2,
    tol=VERTEX_CONNECT_TOL
):

    return (
        np.linalg.norm(
            p1 - p2
        )
        <= tol
    )


# ============================================================
# LOAD / SAVE
# ============================================================

def load_step(step_path):

    if not os.path.exists(
        step_path
    ):

        raise FileNotFoundError(
            step_path
        )

    wp = cq.importers.importStep(
        step_path
    )

    shape = wp.val()

    if shape is None:

        raise RuntimeError(
            "Could not load STEP geometry."
        )

    return shape


def load_request(request_path):

    if not os.path.exists(
        request_path
    ):

        raise FileNotFoundError(
            request_path
        )

    with open(
        request_path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(
            f
        )


def save_json(
    data,
    path
):

    folder = os.path.dirname(
        path
    )

    if folder:

        os.makedirs(
            folder,
            exist_ok=True
        )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )


# ============================================================
# EDGE MATCHING
# ============================================================

def edge_match_score(
    source_edge,
    candidate_edge
):

    try:

        distance = float(
            source_edge.distance(
                candidate_edge
            )
        )

    except Exception:

        distance = float(
            "inf"
        )


    try:

        length_error = abs(
            float(
                source_edge.Length()
            )
            -
            float(
                candidate_edge.Length()
            )
        )

    except Exception:

        length_error = float(
            "inf"
        )


    return (
        distance
        +
        length_error
    )


def find_best_edge_match(
    source_edge,
    target_solid
):

    best = None


    for local_index, candidate in enumerate(
        target_solid.Edges()
    ):

        score = edge_match_score(
            source_edge,
            candidate
        )


        if (
            best is None
            or
            score < best[
                "score"
            ]
        ):

            best = {

                "edge":
                    candidate,

                "local_index":
                    local_index,

                "score":
                    score,

                "length":
                    float(
                        candidate.Length()
                    ),

                "type":
                    candidate.geomType()
            }


    return best


def find_owner_solid_for_edge(
    compound_shape,
    source_edge
):

    solids = compound_shape.Solids()


    best = None


    for solid_index, solid in enumerate(
        solids
    ):

        match = find_best_edge_match(
            source_edge,
            solid
        )


        if match is None:

            continue


        candidate = {

            "solid_index":
                solid_index,

            "solid":
                solid,

            "local_edge_index":
                match[
                    "local_index"
                ],

            "local_edge":
                match[
                    "edge"
                ],

            "match_score":
                match[
                    "score"
                ]
        }


        if (
            best is None
            or
            candidate[
                "match_score"
            ]
            <
            best[
                "match_score"
            ]
        ):

            best = candidate


    if best is None:

        raise RuntimeError(
            "Could not map selected edge "
            "to any owner Solid."
        )


    return best


# ============================================================
# SELECTED EDGE RESOLUTION
# ============================================================

def resolve_selected_edges(
    compound_shape,
    edge_ids
):

    if isinstance(
        edge_ids,
        str
    ):

        edge_ids = [
            edge_ids
        ]


    if not edge_ids:

        raise ValueError(
            "No edge IDs supplied."
        )


    global_edges = (
        compound_shape.Edges()
    )


    selected = []


    for edge_id in edge_ids:

        index = edge_id_to_index(
            edge_id
        )


        if not (
            0
            <= index
            < len(global_edges)
        ):

            raise IndexError(
                f"{edge_id} outside STEP edge range."
            )


        edge = global_edges[
            index
        ]


        selected.append({

            "edge_id":
                edge_id,

            "edge":
                edge
        })


    return selected


# ============================================================
# GROUP SELECTED EDGES BY OWNER SOLID
# ============================================================

def group_selected_edges_by_owner_solid(
    compound_shape,
    selected_edges
):

    grouped = {}


    for item in selected_edges:

        edge_id = item[
            "edge_id"
        ]

        source_edge = item[
            "edge"
        ]


        owner = find_owner_solid_for_edge(
            compound_shape,
            source_edge
        )


        solid_index = owner[
            "solid_index"
        ]


        if solid_index not in grouped:

            grouped[
                solid_index
            ] = {

                "solid":
                    owner[
                        "solid"
                    ],

                "items":
                    []
            }


        grouped[
            solid_index
        ][
            "items"
        ].append({

            "edge_id":
                edge_id,

            "source_edge":
                source_edge,

            "local_edge":
                owner[
                    "local_edge"
                ],

            "local_edge_index":
                owner[
                    "local_edge_index"
                ],

            "match_score":
                float(
                    owner[
                        "match_score"
                    ]
                )
        })


    return grouped


# ============================================================
# CONNECTIVITY GRAPH
# ============================================================

def edges_share_vertex(
    edge_a,
    edge_b
):

    vertices_a = [
        vertex_xyz(
            v
        )
        for v in edge_a.Vertices()
    ]

    vertices_b = [
        vertex_xyz(
            v
        )
        for v in edge_b.Vertices()
    ]


    for point_a in vertices_a:

        for point_b in vertices_b:

            if points_close(
                point_a,
                point_b
            ):

                return True


    return False


def build_connected_edge_groups(
    edge_items
):

    """
    Returns connected components based on shared vertices.

    Each component is a list of edge_items.
    """

    n = len(
        edge_items
    )


    adjacency = {

        i:
            set()

        for i in range(
            n
        )
    }


    for i in range(
        n
    ):

        for j in range(
            i + 1,
            n
        ):

            edge_i = edge_items[
                i
            ][
                "source_edge"
            ]

            edge_j = edge_items[
                j
            ][
                "source_edge"
            ]


            if edges_share_vertex(
                edge_i,
                edge_j
            ):

                adjacency[
                    i
                ].add(
                    j
                )

                adjacency[
                    j
                ].add(
                    i
                )


    visited = set()

    groups = []


    for start in range(
        n
    ):

        if start in visited:

            continue


        stack = [
            start
        ]

        component = []


        while stack:

            index = stack.pop()


            if index in visited:

                continue


            visited.add(
                index
            )

            component.append(
                edge_items[
                    index
                ]
            )


            for neighbour in adjacency[
                index
            ]:

                if neighbour not in visited:

                    stack.append(
                        neighbour
                    )


        groups.append(
            component
        )


    return groups


# ============================================================
# REBUILD MULTI-SOLID MODEL
# ============================================================

def rebuild_compound_with_replacements(
    original_shape,
    replacements
):

    original_solids = (
        original_shape.Solids()
    )


    rebuilt = []


    for index, solid in enumerate(
        original_solids
    ):

        if index in replacements:

            rebuilt.append(
                replacements[
                    index
                ]
            )

        else:

            rebuilt.append(
                solid
            )


    return cq.Compound.makeCompound(
        rebuilt
    )



# ============================================================
# REFERENCE-BASED CHAMFER SIZE EXTRACTION
# ============================================================

def _edge_center_np(edge):
    c = edge.Center()
    return np.array([float(c.x), float(c.y), float(c.z)], dtype=float)


def _face_center_np(face):
    c = face.Center()
    return np.array([float(c.x), float(c.y), float(c.z)], dtype=float)


def _shared_faces_for_edge(solid, edge):
    """Return solid faces that geometrically contain the supplied edge."""
    shared = []
    for face_index, face in enumerate(solid.Faces()):
        best = float("inf")
        for face_edge in face.Edges():
            score = edge_match_score(edge, face_edge)
            if score < best:
                best = score
        if best < 1e-5:
            shared.append({
                "face_index": face_index,
                "face": face,
                "match_score": float(best),
                "geom_type": face.geomType()
            })
    return shared


def _distance_point_to_edge(point_xyz, edge):
    vertex = cq.Vertex.makeVertex(
        float(point_xyz[0]),
        float(point_xyz[1]),
        float(point_xyz[2])
    )
    return float(vertex.distance(edge))


def estimate_existing_chamfer_distance(compound_shape, reference_edge_ids):
    """
    Estimate the linear size of an existing chamfer from user-selected
    reference edge(s).

    Strategy:
      1. Resolve the selected edge and its owner solid.
      2. Find faces incident to that edge.
      3. Search for a nearby planar chamfer face.
      4. On that face, use the minimum distance between the two long/
         boundary edges as the chamfer width.
      5. Fall back to distances between the selected reference edge and
         other edges of the candidate planar face.

    This is intended for standard mechanical chamfers such as B08,
    including annular chamfers between cylindrical sections.
    """
    selected = resolve_selected_edges(
        compound_shape,
        reference_edge_ids
    )

    candidates = []

    for selected_item in selected:
        source_edge = selected_item["edge"]
        owner = find_owner_solid_for_edge(
            compound_shape,
            source_edge
        )
        solid = owner["solid"]
        local_edge = owner["local_edge"]

        incident = _shared_faces_for_edge(
            solid,
            local_edge
        )

        # Prefer planar/conical faces directly incident to the selected edge.
        candidate_faces = []
        for info in incident:
            if info["geom_type"] in ("PLANE", "CONE"):
                candidate_faces.append(info)

        # If the selected edge is one boundary of the chamfer, normally one
        # incident face is the chamfer face itself.
        for info in candidate_faces:
            face = info["face"]
            face_edges = face.Edges()

            if len(face_edges) < 2:
                continue

            # Identify the edge on this face matching the selected reference.
            ref_match = None
            for fe in face_edges:
                score = edge_match_score(local_edge, fe)
                if ref_match is None or score < ref_match["score"]:
                    ref_match = {
                        "edge": fe,
                        "score": float(score)
                    }

            if ref_match is None:
                continue

            ref_edge = ref_match["edge"]

            # Estimate width as minimum geometric separation from the selected
            # boundary edge to another non-identical boundary edge.
            separations = []
            for other in face_edges:
                if edge_match_score(ref_edge, other) < 1e-7:
                    continue
                try:
                    d = float(ref_edge.distance(other))
                except Exception:
                    continue
                if d > 1e-7:
                    separations.append(d)

            if separations:
                width = min(separations)
                candidates.append({
                    "distance_mm": float(width),
                    "reference_edge_id": selected_item["edge_id"],
                    "owner_solid": int(owner["solid_index"]),
                    "face_index": int(info["face_index"]),
                    "face_type": info["geom_type"],
                    "method": "CHAMFER_FACE_BOUNDARY_SEPARATION"
                })

        # Additional fallback: look for a small nearby planar/conical face
        # whose boundary includes the reference edge.
        if not candidate_faces:
            for face_index, face in enumerate(solid.Faces()):
                if face.geomType() not in ("PLANE", "CONE"):
                    continue

                face_edges = face.Edges()
                if len(face_edges) < 2:
                    continue

                best_ref_score = min(
                    edge_match_score(local_edge, fe)
                    for fe in face_edges
                )

                if best_ref_score >= 1e-5:
                    continue

                ref_face_edge = min(
                    face_edges,
                    key=lambda fe: edge_match_score(local_edge, fe)
                )

                separations = []
                for other in face_edges:
                    if edge_match_score(ref_face_edge, other) < 1e-7:
                        continue
                    try:
                        d = float(ref_face_edge.distance(other))
                    except Exception:
                        continue
                    if d > 1e-7:
                        separations.append(d)

                if separations:
                    candidates.append({
                        "distance_mm": float(min(separations)),
                        "reference_edge_id": selected_item["edge_id"],
                        "owner_solid": int(owner["solid_index"]),
                        "face_index": int(face_index),
                        "face_type": face.geomType(),
                        "method": "NEARBY_FACE_BOUNDARY_SEPARATION"
                    })

    # Mechanical chamfers in this pipeline should be positive and finite.
    candidates = [
        c for c in candidates
        if math.isfinite(c["distance_mm"])
        and c["distance_mm"] > 1e-6
    ]

    if not candidates:
        raise RuntimeError(
            "Could not infer chamfer size from selected reference geometry. "
            "Select an edge that directly bounds the existing chamfer face."
        )

    # Prefer the smallest positive width. For a chamfer face this is normally
    # the cross-face chamfer width rather than a circumferential dimension.
    candidates.sort(
        key=lambda c: c["distance_mm"]
    )

    best = candidates[0]

    return float(best["distance_mm"]), {
        "reference_edge_ids": list(reference_edge_ids),
        "estimated_distance_mm": float(best["distance_mm"]),
        "selected_candidate": best,
        "all_candidates": candidates
    }


# ============================================================
# ROBUST CHAMFER HELPERS
# ============================================================

def try_chamfer(
    solid,
    edges,
    distance_mm
):

    if not edges:

        return {
            "success": False,
            "reason": "NO_EDGES"
        }


    try:

        edge_compound = (
            cq.Compound.makeCompound(
                edges
            )
        )


        result = cq_shape_chamfer(
            solid,
            edge_compound,
            distance_mm
        )


        if result is None:

            return {
                "success": False,
                "reason": "RETURNED_NONE"
            }


        if not result.isValid():

            return {
                "success": False,
                "reason": "INVALID_RESULT"
            }


        return {

            "success":
                True,

            "result":
                result,

            "distance_mm":
                float(
                    distance_mm
                ),

            "volume":
                float(
                    result.Volume()
                )
        }


    except Exception as exc:

        return {

            "success":
                False,

            "reason":
                (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )
        }


def adaptive_distance_candidates(
    requested_distance
):

    """
    Generate candidate distances from requested downwards.

    Example:
        1.00
        0.95
        0.90
        ...
        0.05

    Requested value itself is NOT repeated here.
    """

    values = []


    current = (
        requested_distance
        -
        CHAMFER_ADAPTIVE_STEP_MM
    )


    while (
        current
        >=
        CHAMFER_MIN_DISTANCE_MM
        -
        1e-9
    ):

        rounded = round(
            current,
            6
        )

        values.append(
            rounded
        )

        current -= (
            CHAMFER_ADAPTIVE_STEP_MM
        )


    return values


def remap_edge_group(
    group_items,
    current_solid
):

    mapped_edges = []

    mapping_report = []


    for item in group_items:

        edge_id = item[
            "edge_id"
        ]

        source_edge = item[
            "source_edge"
        ]


        match = find_best_edge_match(
            source_edge,
            current_solid
        )


        if match is None:

            return (
                None,
                None
            )


        mapped_edges.append(
            match[
                "edge"
            ]
        )


        mapping_report.append({

            "edge_id":
                edge_id,

            "local_edge_index":
                int(
                    match[
                        "local_index"
                    ]
                ),

            "match_score":
                float(
                    match[
                        "score"
                    ]
                ),

            "type":
                match[
                    "type"
                ],

            "length":
                float(
                    match[
                        "length"
                    ]
                )
        })


    return (
        mapped_edges,
        mapping_report
    )


# ============================================================
# ROBUST CHAMFER GROUP EXECUTION
# ============================================================

def execute_one_chamfer_group(
    current_solid,
    group_items,
    requested_distance_mm
):

    edge_ids = [
        item[
            "edge_id"
        ]
        for item in group_items
    ]


    group_report = {

        "edge_ids":
            edge_ids,

        "requested_distance_mm":
            float(
                requested_distance_mm
            ),

        "applied_distance_mm":
            None,

        "status":
            None,

        "attempts":
            [],

        "skipped_edges":
            []
    }


    # ========================================================
    # REMAP GROUP TO CURRENT TOPOLOGY
    # ========================================================

    mapped_edges, mapping_report = (
        remap_edge_group(
            group_items,
            current_solid
        )
    )


    if mapped_edges is None:

        group_report[
            "status"
        ] = "FAILED"

        group_report[
            "reason"
        ] = "GROUP_REMAP_FAILED"

        return (
            current_solid,
            group_report
        )


    group_report[
        "mapping"
    ] = mapping_report


    # ========================================================
    # TRY REQUESTED DISTANCE
    # ========================================================

    attempt = try_chamfer(
        current_solid,
        mapped_edges,
        requested_distance_mm
    )


    group_report[
        "attempts"
    ].append({

        "distance_mm":
            float(
                requested_distance_mm
            ),

        "success":
            bool(
                attempt[
                    "success"
                ]
            ),

        "reason":
            attempt.get(
                "reason"
            )
    })


    if attempt[
        "success"
    ]:

        group_report[
            "applied_distance_mm"
        ] = float(
            requested_distance_mm
        )

        group_report[
            "status"
        ] = "FULL_SUCCESS"


        return (
            attempt[
                "result"
            ],
            group_report
        )


    # ========================================================
    # ADAPTIVE DISTANCE SEARCH
    # ========================================================

    for candidate_distance in (
        adaptive_distance_candidates(
            requested_distance_mm
        )
    ):

        # topology has not changed yet,
        # so the same mapping can be reused here

        adaptive_attempt = try_chamfer(
            current_solid,
            mapped_edges,
            candidate_distance
        )


        group_report[
            "attempts"
        ].append({

            "distance_mm":
                float(
                    candidate_distance
                ),

            "success":
                bool(
                    adaptive_attempt[
                        "success"
                    ]
                ),

            "reason":
                adaptive_attempt.get(
                    "reason"
                )
        })


        if adaptive_attempt[
            "success"
        ]:

            group_report[
                "applied_distance_mm"
            ] = float(
                candidate_distance
            )

            group_report[
                "status"
            ] = "ADAPTIVE_SUCCESS"


            return (
                adaptive_attempt[
                    "result"
                ],
                group_report
            )


    # ========================================================
    # FALLBACK:
    # TRY EDGES INDIVIDUALLY
    # ========================================================

    group_report[
        "status"
    ] = "PARTIAL_SUCCESS"

    individual_results = []


    working_solid = current_solid


    successful_count = 0


    for item in group_items:

        edge_id = item[
            "edge_id"
        ]


        individual_report = {

            "edge_id":
                edge_id,

            "requested_distance_mm":
                float(
                    requested_distance_mm
                ),

            "applied_distance_mm":
                None,

            "status":
                None,

            "attempts":
                []
        }


        # Remap every edge after every successful modification

        match = find_best_edge_match(
            item[
                "source_edge"
            ],
            working_solid
        )


        if match is None:

            individual_report[
                "status"
            ] = "SKIPPED"

            individual_report[
                "reason"
            ] = "EDGE_REMAP_FAILED"

            individual_results.append(
                individual_report
            )

            group_report[
                "skipped_edges"
            ].append(
                edge_id
            )

            continue


        current_edge = match[
            "edge"
        ]


        # ====================================================
        # TRY REQUESTED DISTANCE
        # ====================================================

        attempt = try_chamfer(
            working_solid,
            [
                current_edge
            ],
            requested_distance_mm
        )


        individual_report[
            "attempts"
        ].append({

            "distance_mm":
                float(
                    requested_distance_mm
                ),

            "success":
                bool(
                    attempt[
                        "success"
                    ]
                ),

            "reason":
                attempt.get(
                    "reason"
                )
        })


        if attempt[
            "success"
        ]:

            working_solid = (
                attempt[
                    "result"
                ]
            )

            individual_report[
                "applied_distance_mm"
            ] = float(
                requested_distance_mm
            )

            individual_report[
                "status"
            ] = "FULL_SUCCESS"

            successful_count += 1

            individual_results.append(
                individual_report
            )

            continue


        # ====================================================
        # ADAPTIVE INDIVIDUAL EDGE
        # ====================================================

        edge_success = False


        for candidate_distance in (
            adaptive_distance_candidates(
                requested_distance_mm
            )
        ):

            # edge must be remapped again because in theory
            # current topology may already differ

            rematch = find_best_edge_match(
                item[
                    "source_edge"
                ],
                working_solid
            )


            if rematch is None:

                break


            adaptive_attempt = try_chamfer(
                working_solid,
                [
                    rematch[
                        "edge"
                    ]
                ],
                candidate_distance
            )


            individual_report[
                "attempts"
            ].append({

                "distance_mm":
                    float(
                        candidate_distance
                    ),

                "success":
                    bool(
                        adaptive_attempt[
                            "success"
                        ]
                    ),

                "reason":
                    adaptive_attempt.get(
                        "reason"
                    )
            })


            if adaptive_attempt[
                "success"
            ]:

                working_solid = (
                    adaptive_attempt[
                        "result"
                    ]
                )

                individual_report[
                    "applied_distance_mm"
                ] = float(
                    candidate_distance
                )

                individual_report[
                    "status"
                ] = "ADAPTIVE_SUCCESS"

                successful_count += 1

                edge_success = True

                break


        if not edge_success:

            individual_report[
                "status"
            ] = "SKIPPED"

            individual_report[
                "reason"
            ] = (
                "NO_VALID_CHAMFER_DISTANCE"
            )

            group_report[
                "skipped_edges"
            ].append(
                edge_id
            )


        individual_results.append(
            individual_report
        )


    group_report[
        "individual_results"
    ] = individual_results


    if successful_count == 0:

        group_report[
            "status"
        ] = "FAILED"


    elif (
        successful_count
        ==
        len(
            group_items
        )
    ):

        # all edges succeeded, but only through edge fallback

        if any(
            item[
                "status"
            ]
            ==
            "ADAPTIVE_SUCCESS"

            for item in individual_results
        ):

            group_report[
                "status"
            ] = "ADAPTIVE_SUCCESS"

        else:

            group_report[
                "status"
            ] = "FULL_SUCCESS"


    else:

        group_report[
            "status"
        ] = "PARTIAL_SUCCESS"


    return (
        working_solid,
        group_report
    )


# ============================================================
# ROBUST CHAMFER
# ============================================================

def execute_chamfer(
    compound_shape,
    request
):

    parameters = request.get(
        "parameters",
        {}
    )

    target = request.get(
        "target",
        {}
    )


    distance_source = str(
        parameters.get(
            "distance_source",
            "TEXT"
        )
    ).strip().upper()

    reference_report = None

    if distance_source == "REFERENCE_GEOMETRY":

        reference = request.get(
            "reference",
            {}
        )

        reference_edge_ids = reference.get(
            "edge_ids",
            []
        )

        if not reference_edge_ids:

            raise ValueError(
                "Reference-based chamfer requires reference.edge_ids."
            )

        requested_distance_mm, reference_report = (
            estimate_existing_chamfer_distance(
                compound_shape,
                reference_edge_ids
            )
        )

        print("=" * 78)
        print("REFERENCE-BASED CHAMFER")
        print("=" * 78)
        print("Reference edges:", reference_edge_ids)
        print(
            "Inferred chamfer distance:",
            requested_distance_mm,
            "mm"
        )
        print(
            "Inference method:",
            reference_report[
                "selected_candidate"
            ][
                "method"
            ]
        )

    else:

        requested_distance_mm = float(
            parameters.get(
                "distance_mm"
            )
        )

    edge_ids = target.get(
        "edge_ids",
        []
    )

    if requested_distance_mm <= 0:

        raise ValueError(
            "Chamfer distance must be > 0."
        )


    selected_edges = resolve_selected_edges(
        compound_shape,
        edge_ids
    )


    print("=" * 78)
    print("ROBUST DETERMINISTIC CHAMFER")
    print("=" * 78)


    print(
        "Requested distance:",
        requested_distance_mm,
        "mm"
    )


    print(
        "Selected edges:",
        edge_ids
    )


    # ========================================================
    # OWNER SOLID GROUPING
    # ========================================================

    owner_groups = (
        group_selected_edges_by_owner_solid(
            compound_shape,
            selected_edges
        )
    )


    replacements = {}

    owner_reports = []


    global_statuses = []


    for solid_index, owner_info in (
        owner_groups.items()
    ):

        original_solid = owner_info[
            "solid"
        ]

        edge_items = owner_info[
            "items"
        ]


        print("\n" + "-" * 78)

        print(
            "Owner Solid:",
            solid_index
        )

        print(
            "Selected edge count:",
            len(
                edge_items
            )
        )


        # ====================================================
        # AUTOMATIC CONNECTED GROUPS
        # ====================================================

        connected_groups = (
            build_connected_edge_groups(
                edge_items
            )
        )


        print(
            "Connected groups:",
            len(
                connected_groups
            )
        )


        for i, group in enumerate(
            connected_groups,
            start=1
        ):

            print(
                f"Group {i}:",
                [
                    item[
                        "edge_id"
                    ]
                    for item in group
                ]
            )


        current_solid = original_solid

        contour_reports = []


        # ====================================================
        # PROCESS GROUPS SEQUENTIALLY
        # ====================================================

        for group_index, group_items in enumerate(
            connected_groups,
            start=1
        ):

            print("\n" + "=" * 60)

            print(
                f"CHAMFER GROUP {group_index}"
            )

            print("=" * 60)


            print(
                "Edges:",
                [
                    item[
                        "edge_id"
                    ]
                    for item in group_items
                ]
            )


            before_volume = float(
                current_solid.Volume()
            )


            new_solid, group_report = (
                execute_one_chamfer_group(
                    current_solid,
                    group_items,
                    requested_distance_mm
                )
            )


            after_volume = float(
                new_solid.Volume()
            )


            group_report[
                "volume_before"
            ] = before_volume

            group_report[
                "volume_after"
            ] = after_volume

            group_report[
                "volume_change"
            ] = (
                after_volume
                -
                before_volume
            )


            contour_reports.append(
                group_report
            )


            global_statuses.append(
                group_report[
                    "status"
                ]
            )


            current_solid = new_solid


            print(
                "Status:",
                group_report[
                    "status"
                ]
            )


            print(
                "Applied distance:",
                group_report.get(
                    "applied_distance_mm"
                )
            )


            print(
                "Volume change:",
                group_report[
                    "volume_change"
                ]
            )


            if group_report[
                "skipped_edges"
            ]:

                print(
                    "Skipped edges:",
                    group_report[
                        "skipped_edges"
                    ]
                )


        replacements[
            solid_index
        ] = current_solid


        owner_reports.append({

            "solid_index":
                solid_index,

            "input_volume":
                float(
                    original_solid.Volume()
                ),

            "output_volume":
                float(
                    current_solid.Volume()
                ),

            "volume_change":
                float(
                    current_solid.Volume()
                )
                -
                float(
                    original_solid.Volume()
                ),

            "input_faces":
                len(
                    original_solid.Faces()
                ),

            "output_faces":
                len(
                    current_solid.Faces()
                ),

            "input_edges":
                len(
                    original_solid.Edges()
                ),

            "output_edges":
                len(
                    current_solid.Edges()
                ),

            "contours":
                contour_reports
        })


    # ========================================================
    # OVERALL OPERATION STATUS
    # ========================================================

    if not global_statuses:

        overall_status = "FAILED"


    elif all(
        status == "FULL_SUCCESS"
        for status in global_statuses
    ):

        overall_status = "FULL_SUCCESS"


    elif any(
        status == "FAILED"
        for status in global_statuses
    ):

        if all(
            status == "FAILED"
            for status in global_statuses
        ):

            overall_status = "FAILED"

        else:

            overall_status = "PARTIAL_SUCCESS"


    elif any(
        status == "PARTIAL_SUCCESS"
        for status in global_statuses
    ):

        overall_status = "PARTIAL_SUCCESS"


    elif any(
        status == "ADAPTIVE_SUCCESS"
        for status in global_statuses
    ):

        overall_status = "ADAPTIVE_SUCCESS"


    else:

        overall_status = "PARTIAL_SUCCESS"


    # ========================================================
    # REBUILD FULL MODEL
    # ========================================================

    result_shape = (
        rebuild_compound_with_replacements(
            compound_shape,
            replacements
        )
    )


    return (
        result_shape,
        {

            "operation":
                "CHAMFER",

            "distance_source":
                distance_source,

            "reference_geometry":
                reference_report,

            "requested_distance_mm":
                requested_distance_mm,

            "edge_ids":
                edge_ids,

            "selected_edge_count":
                len(
                    edge_ids
                ),

            "owner_solid_count":
                len(
                    owner_groups
                ),

            "status":
                overall_status,

            "owner_results":
                owner_reports
        }
    )


# ============================================================
# ROBUST FILLET HELPERS
# ============================================================

def try_fillet(solid, edges, radius_mm):
    if not edges:
        return {"success": False, "reason": "NO_EDGES"}
    try:
        edge_compound = cq.Compound.makeCompound(edges)
        result = cq_shape_fillet(solid, edge_compound, radius_mm)
        if result is None:
            return {"success": False, "reason": "RETURNED_NONE"}
        if not result.isValid():
            return {"success": False, "reason": "INVALID_RESULT"}
        return {
            "success": True,
            "result": result,
            "radius_mm": float(radius_mm),
            "volume": float(result.Volume())
        }
    except Exception as exc:
        return {
            "success": False,
            "reason": f"{type(exc).__name__}: {exc}"
        }


def adaptive_fillet_radius_candidates(requested_radius):
    values = []
    current = requested_radius - FILLET_ADAPTIVE_STEP_MM
    while current >= FILLET_MIN_RADIUS_MM - 1e-9:
        values.append(round(current, 6))
        current -= FILLET_ADAPTIVE_STEP_MM
    return values


def execute_one_fillet_group(current_solid, group_items, requested_radius_mm):
    edge_ids = [item["edge_id"] for item in group_items]
    report = {
        "edge_ids": edge_ids,
        "requested_radius_mm": float(requested_radius_mm),
        "applied_radius_mm": None,
        "status": None,
        "attempts": [],
        "skipped_edges": []
    }

    mapped_edges, mapping_report = remap_edge_group(group_items, current_solid)
    if mapped_edges is None:
        report["status"] = "FAILED"
        report["reason"] = "GROUP_REMAP_FAILED"
        return current_solid, report

    report["mapping"] = mapping_report
    radii = [requested_radius_mm] + adaptive_fillet_radius_candidates(requested_radius_mm)

    for radius in radii:
        attempt = try_fillet(current_solid, mapped_edges, radius)
        report["attempts"].append({
            "radius_mm": float(radius),
            "success": bool(attempt["success"]),
            "reason": attempt.get("reason")
        })
        if attempt["success"]:
            report["applied_radius_mm"] = float(radius)
            report["status"] = (
                "FULL_SUCCESS"
                if abs(radius - requested_radius_mm) < 1e-9
                else "ADAPTIVE_SUCCESS"
            )
            return attempt["result"], report

    working_solid = current_solid
    individual_results = []
    successful_count = 0

    for item in group_items:
        edge_id = item["edge_id"]
        item_report = {
            "edge_id": edge_id,
            "requested_radius_mm": float(requested_radius_mm),
            "applied_radius_mm": None,
            "status": None,
            "attempts": []
        }

        success = False
        for radius in radii:
            match = find_best_edge_match(item["source_edge"], working_solid)
            if match is None:
                item_report["reason"] = "EDGE_REMAP_FAILED"
                break

            attempt = try_fillet(working_solid, [match["edge"]], radius)
            item_report["attempts"].append({
                "radius_mm": float(radius),
                "success": bool(attempt["success"]),
                "reason": attempt.get("reason")
            })

            if attempt["success"]:
                working_solid = attempt["result"]
                item_report["applied_radius_mm"] = float(radius)
                item_report["status"] = (
                    "FULL_SUCCESS"
                    if abs(radius - requested_radius_mm) < 1e-9
                    else "ADAPTIVE_SUCCESS"
                )
                successful_count += 1
                success = True
                break

        if not success:
            item_report["status"] = "SKIPPED"
            item_report.setdefault("reason", "NO_VALID_FILLET_RADIUS")
            report["skipped_edges"].append(edge_id)

        individual_results.append(item_report)

    report["individual_results"] = individual_results

    if successful_count == 0:
        report["status"] = "FAILED"
    elif successful_count < len(group_items):
        report["status"] = "PARTIAL_SUCCESS"
    elif any(x["status"] == "ADAPTIVE_SUCCESS" for x in individual_results):
        report["status"] = "ADAPTIVE_SUCCESS"
    else:
        report["status"] = "FULL_SUCCESS"

    return working_solid, report


# ============================================================
# ROBUST FILLET
# ============================================================

def execute_single_radius_fillet(
    compound_shape,
    edge_ids,
    radius_mm,
    group_label=None
):
    """
    Execute one FILLET selection set on the supplied current topology.
    Used by both legacy single-radius requests and B07 multi-radius groups.
    """

    radius_mm = float(radius_mm)

    if radius_mm <= 0:
        raise ValueError("Fillet radius must be > 0.")

    selected_edges = resolve_selected_edges(
        compound_shape,
        edge_ids
    )

    owner_groups = group_selected_edges_by_owner_solid(
        compound_shape,
        selected_edges
    )

    replacements = {}
    owner_reports = []
    global_statuses = []

    print("=" * 78)
    print("ROBUST DETERMINISTIC FILLET")
    print("=" * 78)

    if group_label is not None:
        print("Selection group:", group_label)

    print("Requested radius:", radius_mm, "mm")
    print("Selected edges:", edge_ids)

    for solid_index, owner_info in owner_groups.items():

        original_solid = owner_info["solid"]
        edge_items = owner_info["items"]

        print("\n" + "-" * 78)
        print("Owner Solid:", solid_index)
        print("Selected edge count:", len(edge_items))

        connected_groups = build_connected_edge_groups(
            edge_items
        )

        print(
            "Connected groups:",
            len(connected_groups)
        )

        current_solid = original_solid
        contour_reports = []

        for group_index, group_items in enumerate(
            connected_groups,
            start=1
        ):

            print("\n" + "=" * 60)
            print(f"FILLET CONNECTED GROUP {group_index}")
            print("=" * 60)

            print(
                "Edges:",
                [
                    item["edge_id"]
                    for item in group_items
                ]
            )

            before_volume = float(
                current_solid.Volume()
            )

            new_solid, group_report = execute_one_fillet_group(
                current_solid,
                group_items,
                radius_mm
            )

            after_volume = float(
                new_solid.Volume()
            )

            group_report["volume_before"] = before_volume
            group_report["volume_after"] = after_volume
            group_report["volume_change"] = (
                after_volume - before_volume
            )

            contour_reports.append(
                group_report
            )

            global_statuses.append(
                group_report["status"]
            )

            current_solid = new_solid

            print(
                "Status:",
                group_report["status"]
            )

            print(
                "Applied radius:",
                group_report.get(
                    "applied_radius_mm"
                )
            )

            print(
                "Volume change:",
                group_report["volume_change"]
            )

            if group_report["skipped_edges"]:
                print(
                    "Skipped edges:",
                    group_report["skipped_edges"]
                )

        replacements[solid_index] = current_solid

        owner_reports.append({
            "solid_index": solid_index,
            "input_volume": float(original_solid.Volume()),
            "output_volume": float(current_solid.Volume()),
            "volume_change": (
                float(current_solid.Volume())
                -
                float(original_solid.Volume())
            ),
            "input_faces": len(original_solid.Faces()),
            "output_faces": len(current_solid.Faces()),
            "input_edges": len(original_solid.Edges()),
            "output_edges": len(current_solid.Edges()),
            "contours": contour_reports
        })

    if not global_statuses:
        overall_status = "FAILED"

    elif all(
        status == "FULL_SUCCESS"
        for status in global_statuses
    ):
        overall_status = "FULL_SUCCESS"

    elif all(
        status == "FAILED"
        for status in global_statuses
    ):
        overall_status = "FAILED"

    elif any(
        status in ("FAILED", "PARTIAL_SUCCESS")
        for status in global_statuses
    ):
        overall_status = "PARTIAL_SUCCESS"

    elif any(
        status == "ADAPTIVE_SUCCESS"
        for status in global_statuses
    ):
        overall_status = "ADAPTIVE_SUCCESS"

    else:
        overall_status = "PARTIAL_SUCCESS"

    result_shape = rebuild_compound_with_replacements(
        compound_shape,
        replacements
    )

    return result_shape, {
        "label": group_label,
        "requested_radius_mm": radius_mm,
        "edge_ids": edge_ids,
        "selected_edge_count": len(edge_ids),
        "owner_solid_count": len(owner_groups),
        "status": overall_status,
        "owner_results": owner_reports
    }


def execute_fillet(compound_shape, request):
    """
    FILLET executor with backward compatibility.

    Supported formats:

    Legacy:
        parameters.radius_mm
        target.edge_ids

    Multi-radius:
        target.edge_groups = [
            {
                "radius_mm": 2.0,
                "edge_ids": [...]
            },
            {
                "radius_mm": 1.0,
                "edge_ids": [...]
            }
        ]

    Multi-radius groups are executed sequentially. After each group,
    the next group's original B-Rep IDs are resolved against the
    current topology by preserving source-edge geometry from the
    original input shape and remapping it to the modified result.
    """

    parameters = request.get(
        "parameters",
        {}
    )

    target = request.get(
        "target",
        {}
    )

    edge_groups = target.get(
        "edge_groups",
        []
    )

    # ========================================================
    # LEGACY SINGLE-RADIUS FILLET
    # ========================================================

    if not edge_groups:

        radius_mm = float(
            parameters.get(
                "radius_mm"
            )
        )

        edge_ids = target.get(
            "edge_ids",
            []
        )

        result_shape, report = execute_single_radius_fillet(
            compound_shape,
            edge_ids,
            radius_mm,
            group_label="SINGLE_RADIUS"
        )

        report["operation"] = "FILLET"
        report["mode"] = "SINGLE_RADIUS"

        return (
            result_shape,
            report
        )

    # ========================================================
    # MULTI-RADIUS FILLET
    # ========================================================

    print("=" * 78)
    print("MULTI-RADIUS DETERMINISTIC FILLET")
    print("=" * 78)
    print("Fillet groups:", len(edge_groups))

    # Resolve every user-selected edge against the ORIGINAL shape
    # before any topology modification. These source edges are then
    # remapped to the evolving geometry after each successful group.
    source_group_data = []

    for group_index, group in enumerate(
        edge_groups,
        start=1
    ):

        radius_mm = float(
            group.get(
                "radius_mm"
            )
        )

        edge_ids = group.get(
            "edge_ids",
            []
        )

        label = str(
            group.get(
                "label",
                f"FILLET_GROUP_{group_index}"
            )
        )

        if radius_mm <= 0:
            raise ValueError(
                f"FILLET group {group_index} radius must be > 0."
            )

        if not edge_ids:
            raise ValueError(
                f"FILLET group {group_index} has no edge IDs."
            )

        selected = resolve_selected_edges(
            compound_shape,
            edge_ids
        )

        source_group_data.append({
            "group_index": group_index,
            "label": label,
            "radius_mm": radius_mm,
            "edge_ids": list(edge_ids),
            "source_edges": [
                {
                    "edge_id": item["edge_id"],
                    "source_edge": item["edge"]
                }
                for item in selected
            ]
        })

    current_shape = compound_shape
    group_reports = []
    statuses = []

    for group_data in source_group_data:

        group_index = group_data[
            "group_index"
        ]

        label = group_data[
            "label"
        ]

        radius_mm = group_data[
            "radius_mm"
        ]

        print("\n" + "#" * 78)
        print(
            f"MULTI-RADIUS FILLET GROUP {group_index}: "
            f"{label}"
        )
        print("#" * 78)
        print("Requested radius:", radius_mm, "mm")
        print("Original edge IDs:", group_data["edge_ids"])

        # Remap each original selected edge to the CURRENT compound.
        # We find its best current owner solid and then collect the
        # corresponding current global edge ID. This lets the existing
        # robust single-radius executor work unchanged.
        current_global_edges = current_shape.Edges()
        remapped_edge_ids = []
        remap_report = []

        for source_item in group_data[
            "source_edges"
        ]:

            source_edge = source_item[
                "source_edge"
            ]

            best = None

            for current_index, candidate_edge in enumerate(
                current_global_edges
            ):

                score = edge_match_score(
                    source_edge,
                    candidate_edge
                )

                if (
                    best is None
                    or
                    score < best["score"]
                ):
                    best = {
                        "index": current_index,
                        "score": float(score),
                        "edge": candidate_edge
                    }

            if best is None:
                raise RuntimeError(
                    "Could not remap FILLET edge "
                    f"{source_item['edge_id']} "
                    f"for group {group_index}."
                )

            current_edge_id = (
                f"E{best['index'] + 1:04d}"
            )

            remapped_edge_ids.append(
                current_edge_id
            )

            remap_report.append({
                "source_edge_id":
                    source_item["edge_id"],

                "current_edge_id":
                    current_edge_id,

                "match_score":
                    float(best["score"])
            })

        print(
            "Remapped current edge IDs:",
            remapped_edge_ids
        )

        before_volume = sum(
            float(solid.Volume())
            for solid in current_shape.Solids()
        )

        new_shape, group_report = execute_single_radius_fillet(
            current_shape,
            remapped_edge_ids,
            radius_mm,
            group_label=label
        )

        after_volume = sum(
            float(solid.Volume())
            for solid in new_shape.Solids()
        )

        group_report[
            "group_index"
        ] = group_index

        group_report[
            "original_edge_ids"
        ] = group_data[
            "edge_ids"
        ]

        group_report[
            "remapped_edge_ids"
        ] = remapped_edge_ids

        group_report[
            "remap"
        ] = remap_report

        group_report[
            "group_input_volume"
        ] = before_volume

        group_report[
            "group_output_volume"
        ] = after_volume

        group_report[
            "group_volume_change"
        ] = (
            after_volume
            -
            before_volume
        )

        group_reports.append(
            group_report
        )

        statuses.append(
            group_report[
                "status"
            ]
        )

        current_shape = new_shape

    # ========================================================
    # OVERALL STATUS
    # ========================================================

    if not statuses:
        overall_status = "FAILED"

    elif all(
        status == "FULL_SUCCESS"
        for status in statuses
    ):
        overall_status = "FULL_SUCCESS"

    elif all(
        status == "FAILED"
        for status in statuses
    ):
        overall_status = "FAILED"

    elif any(
        status in ("FAILED", "PARTIAL_SUCCESS")
        for status in statuses
    ):
        overall_status = "PARTIAL_SUCCESS"

    elif any(
        status == "ADAPTIVE_SUCCESS"
        for status in statuses
    ):
        overall_status = "ADAPTIVE_SUCCESS"

    else:
        overall_status = "PARTIAL_SUCCESS"

    return current_shape, {
        "operation": "FILLET",
        "mode": "MULTI_RADIUS",
        "group_count": len(group_reports),
        "status": overall_status,
        "groups": group_reports
    }


# ============================================================
# ADD HOLE HELPERS
# ============================================================

def get_face_geometry_at_point(
    face,
    point_xyz
):

    """
    Return the closest point on a face and the local surface normal there.

    Works with planar and curved OCC surfaces (PLANE, CYLINDER, CONE,
    SPHERE, TORUS, BSPLINE, etc.).
    """

    point_xyz = np.asarray(
        point_xyz,
        dtype=float
    )

    query_point = cq.Vector(
        float(point_xyz[0]),
        float(point_xyz[1]),
        float(point_xyz[2])
    )

    try:

        u, v = face.paramAt(
            query_point
        )

        surface_point = face.positionAt(
            u,
            v
        )

        normal = face.normalAt(
            surface_point
        )

    except Exception as exc:

        raise RuntimeError(
            "Could not evaluate target face geometry "
            f"at selected point: {type(exc).__name__}: {exc}"
        ) from exc

    projected_point = np.array(
        [
            float(surface_point.x),
            float(surface_point.y),
            float(surface_point.z)
        ],
        dtype=float
    )

    direction = normalize(
        [
            float(normal.x),
            float(normal.y),
            float(normal.z)
        ]
    )

    projection_distance_mm = float(
        np.linalg.norm(
            point_xyz
            -
            projected_point
        )
    )

    return (
        projected_point,
        direction,
        float(u),
        float(v),
        projection_distance_mm
    )


def circular_edge_geometry(edge):

    """
    Extract center and radius from a full circular B-Rep edge.

    Radius is computed from circumference so this does not depend on
    CadQuery exposing a particular OCC circle-radius accessor.
    """

    if edge.geomType() != "CIRCLE":

        raise ValueError(
            "Reference hole edge must be a CIRCLE, "
            f"got {edge.geomType()}."
        )

    length = float(
        edge.Length()
    )

    if length <= 0:

        raise ValueError(
            "Reference circular edge has invalid length."
        )

    radius = (
        length
        /
        (
            2.0
            *
            math.pi
        )
    )

    center_obj = edge.Center()

    center = np.array(
        [
            float(center_obj.x),
            float(center_obj.y),
            float(center_obj.z)
        ],
        dtype=float
    )

    return {
        "center": center,
        "radius_mm": float(radius),
        "diameter_mm": float(
            2.0
            *
            radius
        ),
        "circumference_mm": length
    }


def find_cylindrical_face_for_edge(
    solid,
    source_edge
):

    """
    Find a CYLINDER face of the owner solid that directly contains
    the selected circular edge.
    """

    candidates = []

    for face_index, face in enumerate(
        solid.Faces()
    ):

        if face.geomType() != "CYLINDER":

            continue

        best_score = float(
            "inf"
        )

        for face_edge in face.Edges():

            score = edge_match_score(
                source_edge,
                face_edge
            )

            if score < best_score:

                best_score = score

        if best_score < 1e-5:

            candidates.append({
                "face_index": int(face_index),
                "face": face,
                "score": float(best_score)
            })

    if not candidates:

        return None

    candidates.sort(
        key=lambda item:
            item["score"]
    )

    return candidates[0]


def infer_cylinder_axis_from_face(
    cylinder_face,
    reference_edge
):

    """
    Infer cylinder axis from centers of circular boundary edges of a
    cylindrical face. This is robust for normal through-holes because
    the cylinder usually has one circular boundary on each side.
    """

    circular_edges = [
        edge
        for edge in cylinder_face.Edges()
        if edge.geomType() == "CIRCLE"
    ]

    if len(circular_edges) < 2:

        raise RuntimeError(
            "Could not infer hole axis: the cylindrical reference face "
            "does not expose two circular boundary edges."
        )

    reference_center = circular_edge_geometry(
        reference_edge
    )[
        "center"
    ]

    centers = []

    for edge in circular_edges:

        geometry = circular_edge_geometry(
            edge
        )

        centers.append(
            geometry[
                "center"
            ]
        )

    # Use the boundary center farthest from the selected-edge center.
    farthest_center = max(
        centers,
        key=lambda center:
            float(
                np.linalg.norm(
                    center
                    -
                    reference_center
                )
            )
    )

    axis_vector = (
        farthest_center
        -
        reference_center
    )

    axis = normalize(
        axis_vector
    )

    return axis


def analyze_reference_hole(
    compound_shape,
    edge_id
):

    """
    Analyze one selected circular edge representing an existing hole.

    Returns:
        center
        radius / diameter
        owner solid
        cylindrical face
        hole axis
    """

    selected = resolve_selected_edges(
        compound_shape,
        [
            edge_id
        ]
    )[0]

    source_edge = selected[
        "edge"
    ]

    circle = circular_edge_geometry(
        source_edge
    )

    owner = find_owner_solid_for_edge(
        compound_shape,
        source_edge
    )

    solid = owner[
        "solid"
    ]

    local_edge = owner[
        "local_edge"
    ]

    cylinder_info = find_cylindrical_face_for_edge(
        solid,
        local_edge
    )

    if cylinder_info is None:

        raise RuntimeError(
            f"Could not find cylindrical hole face for {edge_id}. "
            "Select a circular boundary edge of the hole."
        )

    axis = infer_cylinder_axis_from_face(
        cylinder_info[
            "face"
        ],
        local_edge
    )

    return {
        "edge_id":
            edge_id,

        "center":
            circle[
                "center"
            ],

        "radius_mm":
            circle[
                "radius_mm"
            ],

        "diameter_mm":
            circle[
                "diameter_mm"
            ],

        "circumference_mm":
            circle[
                "circumference_mm"
            ],

        "axis":
            axis,

        "owner_solid_index":
            int(
                owner[
                    "solid_index"
                ]
            ),

        "owner_solid":
            solid,

        "cylinder_face_index":
            int(
                cylinder_info[
                    "face_index"
                ]
            )
    }


def execute_reference_hole_pair(
    compound_shape,
    request
):

    """
    B09-style reference-based hole creation.

    The user selects one corresponding circular edge from each of two
    existing holes. The engine:
        - measures their diameters,
        - checks consistency,
        - extracts the hole axis from cylindrical faces,
        - computes the midpoint between hole centers,
        - cuts a new hole with the copied setup.
    """

    parameters = request.get(
        "parameters",
        {}
    )

    reference = request.get(
        "reference",
        {}
    )

    hole_1_edge_ids = reference.get(
        "hole_1_edge_ids",
        []
    )

    hole_2_edge_ids = reference.get(
        "hole_2_edge_ids",
        []
    )

    if len(hole_1_edge_ids) != 1:

        raise ValueError(
            "Reference hole 1 requires exactly one edge ID."
        )

    if len(hole_2_edge_ids) != 1:

        raise ValueError(
            "Reference hole 2 requires exactly one edge ID."
        )

    position_rule = str(
        parameters.get(
            "position_rule",
            ""
        )
    ).strip().upper()

    if position_rule != "MIDPOINT":

        raise ValueError(
            "Reference-hole ADD_HOLE currently supports "
            "position_rule='MIDPOINT'."
        )

    hole_1 = analyze_reference_hole(
        compound_shape,
        hole_1_edge_ids[
            0
        ]
    )

    hole_2 = analyze_reference_hole(
        compound_shape,
        hole_2_edge_ids[
            0
        ]
    )

    diameter_1 = float(
        hole_1[
            "diameter_mm"
        ]
    )

    diameter_2 = float(
        hole_2[
            "diameter_mm"
        ]
    )

    diameter_tolerance = max(
        1e-4,
        0.01
        *
        max(
            diameter_1,
            diameter_2
        )
    )

    if abs(
        diameter_1
        -
        diameter_2
    ) > diameter_tolerance:

        raise RuntimeError(
            "Reference holes do not have the same diameter: "
            f"{diameter_1} mm vs {diameter_2} mm."
        )

    axis_1 = normalize(
        hole_1[
            "axis"
        ]
    )

    axis_2 = normalize(
        hole_2[
            "axis"
        ]
    )

    axis_alignment = abs(
        float(
            np.dot(
                axis_1,
                axis_2
            )
        )
    )

    if axis_alignment < 0.99:

        raise RuntimeError(
            "Reference holes are not parallel enough to copy "
            "their setup safely."
        )

    # Align direction signs.
    if float(
        np.dot(
            axis_1,
            axis_2
        )
    ) < 0:

        axis_2 = (
            -axis_2
        )

    hole_axis = normalize(
        axis_1
        +
        axis_2
    )

    center_1 = hole_1[
        "center"
    ]

    center_2 = hole_2[
        "center"
    ]

    midpoint = (
        center_1
        +
        center_2
    ) / 2.0

    diameter_mm = (
        diameter_1
        +
        diameter_2
    ) / 2.0

    # Both selected reference holes should belong to the same component.
    if (
        hole_1[
            "owner_solid_index"
        ]
        !=
        hole_2[
            "owner_solid_index"
        ]
    ):

        raise RuntimeError(
            "The two reference holes belong to different solids."
        )

    solid_index = hole_1[
        "owner_solid_index"
    ]

    solid = hole_1[
        "owner_solid"
    ]

    bbox = solid.BoundingBox()

    diagonal = math.sqrt(
        bbox.xlen ** 2
        +
        bbox.ylen ** 2
        +
        bbox.zlen ** 2
    )

    tool_length = max(
        diagonal
        *
        4.0,
        100.0
    )

    start_point = (
        midpoint
        -
        hole_axis
        *
        (
            tool_length
            /
            2.0
        )
    )

    tool = cq.Solid.makeCylinder(
        diameter_mm
        /
        2.0,
        tool_length,
        cq.Vector(
            float(start_point[0]),
            float(start_point[1]),
            float(start_point[2])
        ),
        cq.Vector(
            float(hole_axis[0]),
            float(hole_axis[1]),
            float(hole_axis[2])
        )
    )

    input_volume = float(
        solid.Volume()
    )

    result_solid = solid.cut(
        tool
    )

    if result_solid is None:

        raise RuntimeError(
            "Reference-hole cut returned None."
        )

    if not result_solid.isValid():

        raise RuntimeError(
            "Reference-hole operation produced invalid geometry."
        )

    replacements = {
        solid_index:
            result_solid
    }

    result_shape = rebuild_compound_with_replacements(
        compound_shape,
        replacements
    )

    print("=" * 78)
    print("REFERENCE-HOLE ADD_HOLE")
    print("=" * 78)
    print(
        "Reference hole 1:",
        hole_1[
            "edge_id"
        ]
    )
    print(
        "Reference hole 2:",
        hole_2[
            "edge_id"
        ]
    )
    print(
        "Diameter 1:",
        diameter_1,
        "mm"
    )
    print(
        "Diameter 2:",
        diameter_2,
        "mm"
    )
    print(
        "Derived diameter:",
        diameter_mm,
        "mm"
    )
    print(
        "Center 1:",
        center_1.tolist()
    )
    print(
        "Center 2:",
        center_2.tolist()
    )
    print(
        "Derived midpoint:",
        midpoint.tolist()
    )
    print(
        "Derived axis:",
        hole_axis.tolist()
    )

    return (
        result_shape,
        {

            "operation":
                "ADD_HOLE",

            "mode":
                "REFERENCE_HOLES",

            "geometry_source":
                "REFERENCE_HOLES",

            "position_rule":
                "MIDPOINT",

            "setup_rule":
                parameters.get(
                    "setup_rule",
                    "COPY_EXISTING_HOLE_SETUP"
                ),

            "reference_hole_1":
                {
                    "edge_id":
                        hole_1[
                            "edge_id"
                        ],

                    "center":
                        center_1.tolist(),

                    "diameter_mm":
                        diameter_1,

                    "axis":
                        axis_1.tolist()
                },

            "reference_hole_2":
                {
                    "edge_id":
                        hole_2[
                            "edge_id"
                        ],

                    "center":
                        center_2.tolist(),

                    "diameter_mm":
                        diameter_2,

                    "axis":
                        axis_2.tolist()
                },

            "derived_center":
                midpoint.tolist(),

            "derived_axis":
                hole_axis.tolist(),

            "derived_diameter_mm":
                float(
                    diameter_mm
                ),

            "owner_solid":
                int(
                    solid_index
                ),

            "input_volume":
                input_volume,

            "output_volume":
                float(
                    result_solid.Volume()
                ),

            "removed_volume":
                input_volume
                -
                float(
                    result_solid.Volume()
                ),

            "status":
                "FULL_SUCCESS"
        }
    )


# ============================================================
# ADD HOLE
# ============================================================

def execute_add_hole(
    compound_shape,
    request
):

    parameters = request.get(
        "parameters",
        {}
    )

    geometry_source = str(
        parameters.get(
            "geometry_source",
            "TEXT"
        )
    ).strip().upper()

    # ========================================================
    # B09 / REFERENCE-HOLE PAIR MODE
    # ========================================================

    if geometry_source == "REFERENCE_HOLES":

        return execute_reference_hole_pair(
            compound_shape,
            request
        )

    # ========================================================
    # LEGACY EXPLICIT-DIAMETER MODE
    # ========================================================

    target = request.get(
        "target",
        {}
    )

    diameter_mm = float(
        parameters.get(
            "diameter_mm"
        )
    )

    face_id = target.get(
        "face_id"
    )

    point_xyz = target.get(
        "point_xyz"
    )

    if diameter_mm <= 0:

        raise ValueError(
            "Hole diameter must be > 0."
        )

    if face_id is None:

        raise ValueError(
            "face_id missing."
        )

    if point_xyz is None:

        raise ValueError(
            "point_xyz missing."
        )

    point_xyz = np.asarray(
        point_xyz,
        dtype=float
    )

    global_faces = (
        compound_shape.Faces()
    )

    face_index = face_id_to_index(
        face_id
    )

    if not (
        0
        <= face_index
        < len(global_faces)
    ):

        raise IndexError(
            f"{face_id} outside face range."
        )

    target_face = global_faces[
        face_index
    ]

    solids = compound_shape.Solids()

    owner_candidates = []

    for solid_index, solid in enumerate(
        solids
    ):

        for local_face_index, local_face in enumerate(
            solid.Faces()
        ):

            try:

                distance = float(
                    target_face.distance(
                        local_face
                    )
                )

            except Exception:

                continue

            area_error = abs(
                float(
                    target_face.Area()
                )
                -
                float(
                    local_face.Area()
                )
            )

            score = (
                distance
                +
                area_error
            )

            owner_candidates.append({

                "solid_index":
                    solid_index,

                "solid":
                    solid,

                "local_face_index":
                    local_face_index,

                "local_face":
                    local_face,

                "score":
                    score
            })

    if not owner_candidates:

        raise RuntimeError(
            "Could not find owner solid "
            "for target face."
        )

    owner_candidates.sort(
        key=lambda item:
            item[
                "score"
            ]
    )

    owner = owner_candidates[
        0
    ]

    solid_index = owner[
        "solid_index"
    ]

    solid = owner[
        "solid"
    ]

    owner_face = owner[
        "local_face"
    ]

    (
        projected_point,
        face_normal,
        surface_u,
        surface_v,
        projection_distance_mm
    ) = get_face_geometry_at_point(
        owner_face,
        point_xyz
    )

    print(
        "Target surface:",
        owner_face.geomType()
    )

    print(
        "Projected point:",
        projected_point.tolist()
    )

    print(
        "Local normal:",
        face_normal.tolist()
    )

    print(
        "Projection distance:",
        projection_distance_mm,
        "mm"
    )

    bbox = solid.BoundingBox()

    diagonal = math.sqrt(
        bbox.xlen ** 2
        +
        bbox.ylen ** 2
        +
        bbox.zlen ** 2
    )

    tool_length = max(
        diagonal
        *
        4.0,
        100.0
    )

    start_point = (
        projected_point
        -
        face_normal
        *
        (
            tool_length
            /
            2.0
        )
    )

    tool = cq.Solid.makeCylinder(

        diameter_mm
        /
        2.0,

        tool_length,

        cq.Vector(
            float(
                start_point[
                    0
                ]
            ),
            float(
                start_point[
                    1
                ]
            ),
            float(
                start_point[
                    2
                ]
            )
        ),

        cq.Vector(
            float(
                face_normal[
                    0
                ]
            ),
            float(
                face_normal[
                    1
                ]
            ),
            float(
                face_normal[
                    2
                ]
            )
        )
    )

    input_volume = float(
        solid.Volume()
    )

    result_solid = solid.cut(
        tool
    )

    if result_solid is None:

        raise RuntimeError(
            "Hole cut returned None."
        )

    if not result_solid.isValid():

        raise RuntimeError(
            "Hole operation produced "
            "invalid geometry."
        )

    replacements = {

        solid_index:
            result_solid
    }

    result_shape = (
        rebuild_compound_with_replacements(
            compound_shape,
            replacements
        )
    )

    return (
        result_shape,
        {

            "operation":
                "ADD_HOLE",

            "mode":
                "EXPLICIT_DIAMETER",

            "diameter_mm":
                diameter_mm,

            "target_face":
                face_id,

            "target_point":
                point_xyz.tolist(),

            "projected_point":
                projected_point.tolist(),

            "face_normal":
                face_normal.tolist(),

            "surface_type":
                owner_face.geomType(),

            "surface_uv":
                [
                    surface_u,
                    surface_v
                ],

            "projection_distance_mm":
                projection_distance_mm,

            "owner_solid":
                solid_index,

            "input_volume":
                input_volume,

            "output_volume":
                float(
                    result_solid.Volume()
                ),

            "removed_volume":
                input_volume
                -
                float(
                    result_solid.Volume()
                ),

            "status":
                "FULL_SUCCESS"
        }
    )


# ============================================================
# MAIN EXECUTOR
# ============================================================

def run_deterministic_edit(
    step_path,
    edit_request_path,
    output_step_path,
    report_path=None
):

    print("=" * 78)
    print("DETERMINISTIC CAD EDIT")
    print("=" * 78)


    print(
        "\nINPUT STEP"
    )

    print(
        step_path
    )


    print(
        "\nREQUEST"
    )

    print(
        edit_request_path
    )


    shape = load_step(
        step_path
    )


    request = load_request(
        edit_request_path
    )


    operation = str(
        request.get(
            "operation",
            ""
        )
    ).upper()


    print(
        "\nOperation:"
    )

    print(
        operation
    )


    input_valid = bool(
        shape.isValid()
    )


    input_solids = len(
        shape.Solids()
    )


    input_volume = sum(
        float(
            solid.Volume()
        )
        for solid in shape.Solids()
    )


    input_faces = len(
        shape.Faces()
    )


    input_edges = len(
        shape.Edges()
    )


    # ========================================================
    # DISPATCH
    # ========================================================

    if operation == "ADD_HOLE":

        result_shape, operation_report = (
            execute_add_hole(
                shape,
                request
            )
        )


    elif operation == "FILLET":

        result_shape, operation_report = (
            execute_fillet(
                shape,
                request
            )
        )


    elif operation == "CHAMFER":

        result_shape, operation_report = (
            execute_chamfer(
                shape,
                request
            )
        )


    else:

        raise NotImplementedError(
            f"Unsupported operation: {operation}"
        )


    # ========================================================
    # VALIDATE RESULT
    # ========================================================

    if result_shape is None:

        raise RuntimeError(
            "No result geometry returned."
        )


    result_valid = bool(
        result_shape.isValid()
    )


    output_solids = len(
        result_shape.Solids()
    )


    output_volume = sum(
        float(
            solid.Volume()
        )
        for solid in result_shape.Solids()
    )


    output_faces = len(
        result_shape.Faces()
    )


    output_edges = len(
        result_shape.Edges()
    )


    # ========================================================
    # EXPORT
    # ========================================================

    output_dir = os.path.dirname(
        output_step_path
    )


    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True
        )


    cq.exporters.export(
        result_shape,
        output_step_path
    )


    step_success = os.path.exists(
        output_step_path
    )


    # ========================================================
    # REIMPORT
    # ========================================================

    reimport_valid = False

    reimport_solids = None

    reimport_volume = None

    reimport_volume_delta = None


    if step_success:

        try:

            check_shape = load_step(
                output_step_path
            )


            reimport_valid = bool(
                check_shape.isValid()
            )


            reimport_solids = len(
                check_shape.Solids()
            )


            reimport_volume = sum(
                float(
                    solid.Volume()
                )
                for solid in check_shape.Solids()
            )


            reimport_volume_delta = (
                reimport_volume
                -
                output_volume
            )


        except Exception:

            traceback.print_exc()


    # ========================================================
    # FINAL OPERATION STATUS
    # ========================================================

    operation_status = (
        operation_report.get(
            "status",
            "UNKNOWN"
        )
    )


    # ========================================================
    # REPORT
    # ========================================================

    final_report = {

        "method":
            (
                "Semi-Automatic Geometric Mapping "
                "+ Robust Deterministic CAD Editing"
            ),

        "operation":
            operation,

        "operation_status":
            operation_status,

        "input_step":
            step_path,

        "edit_request":
            edit_request_path,

        "output_step":
            output_step_path,

        "input_valid":
            input_valid,

        "result_valid":
            result_valid,

        "step_success":
            step_success,

        "reimport_valid":
            reimport_valid,

        "input_solids":
            input_solids,

        "output_solids":
            output_solids,

        "reimport_solids":
            reimport_solids,

        "input_faces":
            input_faces,

        "output_faces":
            output_faces,

        "input_edges":
            input_edges,

        "output_edges":
            output_edges,

        "input_volume":
            input_volume,

        "output_volume":
            output_volume,

        "volume_change":
            output_volume
            -
            input_volume,

        "reimport_volume":
            reimport_volume,

        "reimport_volume_delta":
            reimport_volume_delta,

        "operation_report":
            operation_report
    }


    if report_path is not None:

        save_json(
            final_report,
            report_path
        )


    # ========================================================
    # CONSOLE
    # ========================================================

    print("\n" + "=" * 78)
    print("DETERMINISTIC EDIT RESULT")
    print("=" * 78)


    print(
        "Operation status:",
        operation_status
    )


    print(
        "STEP success:",
        step_success
    )


    print(
        "Input valid:",
        input_valid
    )


    print(
        "Result valid:",
        result_valid
    )


    print(
        "Reimport valid:",
        reimport_valid
    )


    print(
        "Input solids:",
        input_solids
    )


    print(
        "Output solids:",
        output_solids
    )


    print(
        "Faces:",
        input_faces,
        "->",
        output_faces
    )


    print(
        "Edges:",
        input_edges,
        "->",
        output_edges
    )


    print(
        "Input volume:",
        input_volume
    )


    print(
        "Output volume:",
        output_volume
    )


    print(
        "Volume change:",
        output_volume
        -
        input_volume
    )


    print(
        "Reimport volume:",
        reimport_volume
    )


    print(
        "Reimport volume delta:",
        reimport_volume_delta
    )


    print(
        "\nOutput STEP:"
    )

    print(
        output_step_path
    )


    if report_path is not None:

        print(
            "\nReport:"
        )

        print(
            report_path
        )


    return final_report


# ============================================================
# DIRECT LOAD
# ============================================================

if __name__ == "__main__":

    print(
        "deterministic_edit.py loaded successfully."
    )

    print(
        "Supported operations:"
    )

    print(
        "  ADD_HOLE"
    )

    print(
        "  FILLET"
    )

    print(
        "  CHAMFER — robust adaptive mode"
    )