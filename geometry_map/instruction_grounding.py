# ============================================================
# FILE: instruction_grounding.py
# ASME CIE 2026 STUDENT HACKATHON
#
# COMPONENT:
#     Proposed Deterministic Geometry Map Pipeline
#
# PURPOSE:
#     Convert natural-language CAD instruction + user
#     geometric selection into:
#
#         1. Structured engineering intent
#         2. Exact STEP B-Rep target face
#         3. Target point in STEP coordinates
#
# CURRENT B01 EXAMPLE:
#
#     Instruction:
#         "Please add a hole of 2 mm here for reset button."
#
#     Output:
#
#         operation      = ADD_HOLE
#         diameter_mm    = 2.0
#         target_face_id = F0040
#         target_point   = [X, Y, Z]
#
# PIPELINE:
#
#     Natural-language instruction
#              ↓
#     parse_instruction()
#              ↓
#     Structured Intent
#              ↓
#     Fusion request_events
#              ↓
#     selected BRepFace
#              ↓
#     automatic coordinate-scale detection
#              ↓
#     Geometry Map face matching
#              ↓
#     exact STEP face + target point
#              ↓
#     deterministic_edit.py
#
# IMPORTANT:
#
#     This module does NOT use Ground Truth geometry.
#
#     The selected BRepFace comes from the original user
#     interaction contained in the benchmark request.
#
#     Ground Truth is used only later for evaluation.
# ============================================================


import os
import json
import re

import numpy as np


# ============================================================
# NUMERICAL CONSTANTS
# ============================================================

FACE_MATCH_SCORE_TOL = 1e-5

DEFAULT_SCALE_CANDIDATES = [
    0.1,
    1.0,
    10.0,
    100.0
]


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_vector(vector):
    """
    Normalize a 3D vector.
    """

    if vector is None:
        return None

    vector = np.array(
        vector,
        dtype=float
    )

    norm = np.linalg.norm(
        vector
    )

    if norm < 1e-12:
        return None

    return vector / norm


def bbox_center(
    bbox_min,
    bbox_max
):
    """
    Return center of a bounding box.
    """

    bbox_min = np.array(
        bbox_min,
        dtype=float
    )

    bbox_max = np.array(
        bbox_max,
        dtype=float
    )

    return (
        bbox_min + bbox_max
    ) / 2.0


def bbox_size(
    bbox_min,
    bbox_max
):
    """
    Return XYZ extents of a bounding box.
    """

    bbox_min = np.array(
        bbox_min,
        dtype=float
    )

    bbox_max = np.array(
        bbox_max,
        dtype=float
    )

    return (
        bbox_max - bbox_min
    )


def geometry_bbox_to_arrays(
    bbox
):
    """
    Convert Geometry Map bbox dictionary to numpy arrays.
    """

    bbox_min = np.array(
        [
            bbox["xmin"],
            bbox["ymin"],
            bbox["zmin"]
        ],
        dtype=float
    )

    bbox_max = np.array(
        [
            bbox["xmax"],
            bbox["ymax"],
            bbox["zmax"]
        ],
        dtype=float
    )

    return (
        bbox_min,
        bbox_max
    )


# ============================================================
# STRUCTURED INSTRUCTION PARSER
# ============================================================

def parse_instruction(
    instruction_text
):
    """
    Convert CAD instruction into structured engineering intent.

    Current operations:
        ADD_HOLE
        FILLET
        CHAMFER

    This deterministic parser is sufficient for the current
    B01/B02/B03 benchmark tasks.

    It can later be replaced by LLM structured output while
    keeping the downstream geometric pipeline unchanged.
    """

    original = str(
        instruction_text
    ).strip()

    text = original.lower()

    result = {
        "original_instruction":
            original,

        "operation":
            "UNKNOWN",

        "size_mm":
            None,

        "diameter_mm":
            None,

        "radius_mm":
            None,

        "target_reference":
            None
    }

    # --------------------------------------------------------
    # OPERATION
    # --------------------------------------------------------

    if (
        "hole" in text
        and (
            "add" in text
            or "create" in text
            or "make" in text
        )
    ):
        result[
            "operation"
        ] = "ADD_HOLE"

    elif "fillet" in text:

        result[
            "operation"
        ] = "FILLET"

    elif "chamfer" in text:

        result[
            "operation"
        ] = "CHAMFER"

    # --------------------------------------------------------
    # NUMERICAL VALUE
    # --------------------------------------------------------

    number_match = re.search(
        r"(\d+(?:\.\d+)?)\s*"
        r"(?:mm|millimeter|millimeters)",
        text
    )

    if number_match:

        value = float(
            number_match.group(1)
        )

        result[
            "size_mm"
        ] = value

        if result[
            "operation"
        ] == "ADD_HOLE":

            result[
                "diameter_mm"
            ] = value

        elif result[
            "operation"
        ] in {
            "FILLET",
            "CHAMFER"
        }:

            result[
                "radius_mm"
            ] = value

    # --------------------------------------------------------
    # TARGET LANGUAGE
    # --------------------------------------------------------

    if "here" in text:

        result[
            "target_reference"
        ] = "HERE"

    elif "this hole" in text:

        result[
            "target_reference"
        ] = "THIS_HOLE"

    elif "this face" in text:

        result[
            "target_reference"
        ] = "THIS_FACE"

    elif "these edges" in text:

        result[
            "target_reference"
        ] = "THESE_EDGES"

    elif "sharp edges" in text:

        result[
            "target_reference"
        ] = "SHARP_EDGES"

    return result


# ============================================================
# REQUEST EVENT PARSING
# ============================================================

def extract_geometric_selection_events(
    request_events
):
    """
    Extract activeSelectionChanged events containing
    geometric entities.
    """

    selections = []

    for index, event in enumerate(
        request_events
    ):

        if event.get(
            "event"
        ) != "activeSelectionChanged":

            continue

        entity_type = event.get(
            "entityType"
        )

        if entity_type is None:
            continue

        selection = {
            "event_index":
                index,

            "entity_type":
                entity_type,

            "bbox_min":
                event.get(
                    "bboxMin"
                ),

            "bbox_max":
                event.get(
                    "bboxMax"
                ),

            "centroid":
                event.get(
                    "centroid"
                ),

            "area":
                event.get(
                    "area"
                ),

            "timestamp":
                event.get(
                    "timestamp"
                ),

            "timestamp_relative":
                event.get(
                    "timestamp_relative_to_vid_start"
                )
        }

        selections.append(
            selection
        )

    return selections


def get_selected_faces(
    request_events
):
    """
    Return Fusion BRepFace selection events.
    """

    selections = (
        extract_geometric_selection_events(
            request_events
        )
    )

    return [
        selection
        for selection in selections
        if (
            selection[
                "entity_type"
            ]
            == "adsk::fusion::BRepFace"
        )
    ]


def get_selected_edges(
    request_events
):
    """
    Return Fusion BRepEdge selection events.
    """

    selections = (
        extract_geometric_selection_events(
            request_events
        )
    )

    return [
        selection
        for selection in selections
        if (
            selection[
                "entity_type"
            ]
            == "adsk::fusion::BRepEdge"
        )
    ]


# ============================================================
# FACE MATCH SCORE
# ============================================================

def calculate_face_match_score(
    event_centroid,
    event_bbox_min,
    event_bbox_max,
    event_area,
    geometry_face
):
    """
    Compare selected Fusion BRepFace with STEP Geometry Map face.

    Lower score = better match.

    Uses:
        centroid
        bbox min
        bbox max
        area
    """

    face_center = geometry_face.get(
        "center"
    )

    face_bbox = geometry_face.get(
        "bbox"
    )

    face_area = geometry_face.get(
        "area"
    )

    if (
        face_center is None
        or face_bbox is None
    ):
        return None

    face_center = np.array(
        face_center,
        dtype=float
    )

    (
        face_bbox_min,
        face_bbox_max
    ) = geometry_bbox_to_arrays(
        face_bbox
    )

    # --------------------------------------------------------
    # GEOMETRIC ERRORS
    # --------------------------------------------------------

    centroid_error = float(
        np.linalg.norm(
            event_centroid
            - face_center
        )
    )

    bbox_min_error = float(
        np.linalg.norm(
            event_bbox_min
            - face_bbox_min
        )
    )

    bbox_max_error = float(
        np.linalg.norm(
            event_bbox_max
            - face_bbox_max
        )
    )

    # --------------------------------------------------------
    # AREA ERROR
    # --------------------------------------------------------

    if (
        event_area is not None
        and face_area is not None
        and abs(
            float(face_area)
        ) > 1e-12
    ):

        area_relative_error = abs(
            float(event_area)
            - float(face_area)
        ) / abs(
            float(face_area)
        )

    else:

        area_relative_error = 0.0

    # --------------------------------------------------------
    # TOTAL SCORE
    # --------------------------------------------------------

    total_score = (
        centroid_error
        + bbox_min_error
        + bbox_max_error
        + area_relative_error
    )

    return {
        "face_id":
            geometry_face["id"],

        "surface_type":
            geometry_face.get(
                "surface_type"
            ),

        "score":
            float(
                total_score
            ),

        "centroid_error":
            centroid_error,

        "bbox_min_error":
            bbox_min_error,

        "bbox_max_error":
            bbox_max_error,

        "area_relative_error":
            float(
                area_relative_error
            ),

        "face_center":
            geometry_face.get(
                "center"
            ),

        "face_area":
            face_area,

        "normal":
            geometry_face.get(
                "normal"
            ),

        "plane_location":
            geometry_face.get(
                "plane_location"
            )
    }


# ============================================================
# SCALE TRANSFORMATION
# ============================================================

def scale_face_selection(
    selection,
    scale
):
    """
    Convert Fusion coordinates to STEP coordinate system.

    Coordinate dimensions scale by:
        scale

    Area scales by:
        scale²
    """

    bbox_min = selection.get(
        "bbox_min"
    )

    bbox_max = selection.get(
        "bbox_max"
    )

    centroid = selection.get(
        "centroid"
    )

    area = selection.get(
        "area"
    )

    if (
        bbox_min is None
        or bbox_max is None
    ):

        raise ValueError(
            "Selected face does not contain bbox coordinates."
        )

    bbox_min_scaled = (
        np.array(
            bbox_min,
            dtype=float
        )
        * float(scale)
    )

    bbox_max_scaled = (
        np.array(
            bbox_max,
            dtype=float
        )
        * float(scale)
    )

    if centroid is not None:

        centroid_scaled = (
            np.array(
                centroid,
                dtype=float
            )
            * float(scale)
        )

    else:

        centroid_scaled = bbox_center(
            bbox_min_scaled,
            bbox_max_scaled
        )

    if area is not None:

        area_scaled = (
            float(area)
            * float(scale) ** 2
        )

    else:

        area_scaled = None

    return {
        "bbox_min":
            bbox_min_scaled,

        "bbox_max":
            bbox_max_scaled,

        "centroid":
            centroid_scaled,

        "area":
            area_scaled
    }


# ============================================================
# MATCH ONE SELECTED FUSION FACE TO STEP
# ============================================================

def match_selected_face_to_geometry_map(
    selection,
    geometry_map,
    scale_candidates=None,
    planar_only=False
):
    """
    Find exact STEP Geometry Map face corresponding to
    a selected Fusion 360 BRepFace.

    Automatically evaluates several possible unit scales.
    """

    if scale_candidates is None:

        scale_candidates = (
            DEFAULT_SCALE_CANDIDATES
        )

    all_scale_results = []

    # --------------------------------------------------------
    # TEST EACH SCALE
    # --------------------------------------------------------

    for scale in scale_candidates:

        scaled = scale_face_selection(
            selection,
            scale
        )

        matches = []

        for face in geometry_map[
            "faces"
        ]:

            if (
                planar_only
                and
                face.get(
                    "surface_type"
                ) != "PLANE"
            ):

                continue

            result = (
                calculate_face_match_score(

                    scaled[
                        "centroid"
                    ],

                    scaled[
                        "bbox_min"
                    ],

                    scaled[
                        "bbox_max"
                    ],

                    scaled[
                        "area"
                    ],

                    face
                )
            )

            if result is not None:

                matches.append(
                    result
                )

        if not matches:
            continue

        matches.sort(
            key=lambda x: x[
                "score"
            ]
        )

        all_scale_results.append({
            "scale":
                float(scale),

            "best_match":
                matches[0],

            "top_matches":
                matches[:10],

            "scaled_selection": {
                "centroid":
                    scaled[
                        "centroid"
                    ].tolist(),

                "bbox_min":
                    scaled[
                        "bbox_min"
                    ].tolist(),

                "bbox_max":
                    scaled[
                        "bbox_max"
                    ].tolist(),

                "area":
                    scaled[
                        "area"
                    ]
            }
        })

    if not all_scale_results:

        return None

    all_scale_results.sort(
        key=lambda x:
            x[
                "best_match"
            ][
                "score"
            ]
    )

    best = all_scale_results[0]

    return {
        "coordinate_scale":
            best[
                "scale"
            ],

        "face_id":
            best[
                "best_match"
            ][
                "face_id"
            ],

        "surface_type":
            best[
                "best_match"
            ][
                "surface_type"
            ],

        "match_score":
            best[
                "best_match"
            ][
                "score"
            ],

        "centroid_error":
            best[
                "best_match"
            ][
                "centroid_error"
            ],

        "bbox_min_error":
            best[
                "best_match"
            ][
                "bbox_min_error"
            ],

        "bbox_max_error":
            best[
                "best_match"
            ][
                "bbox_max_error"
            ],

        "area_relative_error":
            best[
                "best_match"
            ][
                "area_relative_error"
            ],

        "step_face_center":
            best[
                "best_match"
            ][
                "face_center"
            ],

        "step_face_normal":
            best[
                "best_match"
            ][
                "normal"
            ],

        "step_plane_location":
            best[
                "best_match"
            ][
                "plane_location"
            ],

        "scaled_selection":
            best[
                "scaled_selection"
            ],

        "all_scale_results":
            all_scale_results
    }


# ============================================================
# BUILD TARGET POINT
# ============================================================

def determine_target_point_from_face_selection(
    matched_face
):
    """
    Initial deterministic point grounding.

    Current rule:
        use scaled Fusion selection centroid.

    For B01 the user selected a BRepFace rather than an exact
    BRepPoint, so the face-selection centroid is the available
    structured geometric reference.

    IMPORTANT:
        This does not claim that every future "HERE" request
        should use the face centroid.

        Later versions can replace this with:
            screen-space cursor grounding
            video pointing
            VLM point localization
            explicit CAD pick point
    """

    selection = matched_face.get(
        "scaled_selection"
    )

    if selection is None:

        raise ValueError(
            "Matched face lacks scaled_selection."
        )

    centroid = selection.get(
        "centroid"
    )

    if centroid is None:

        raise ValueError(
            "Selected BRepFace has no centroid."
        )

    return [
        float(
            centroid[0]
        ),
        float(
            centroid[1]
        ),
        float(
            centroid[2]
        )
    ]


# ============================================================
# BUILD B01-STYLE FACE GROUNDING
# ============================================================

def ground_add_hole_request(
    intent,
    request_events,
    geometry_map
):
    """
    Ground an ADD_HOLE request to an exact STEP planar face.

    Current B01 case:
        one selected Fusion BRepFace.
    """

    selected_faces = get_selected_faces(
        request_events
    )

    if not selected_faces:

        raise RuntimeError(
            "ADD_HOLE grounding requires a selected BRepFace "
            "for the current implementation."
        )

    # Current benchmark B01 contains one face selection.
    # If multiple are present later, they can be ranked.

    selection = selected_faces[0]

    matched_face = (
        match_selected_face_to_geometry_map(

            selection=

                selection,

            geometry_map=

                geometry_map,

            planar_only=True
        )
    )

    if matched_face is None:

        raise RuntimeError(
            "Could not match selected Fusion BRepFace "
            "to STEP Geometry Map."
        )

    target_point = (
        determine_target_point_from_face_selection(
            matched_face
        )
    )

    exact_match = (
        matched_face[
            "match_score"
        ]
        <= FACE_MATCH_SCORE_TOL
    )

    return {
        "target_entity_type":
            "BRepFace",

        "target_face_id":
            matched_face[
                "face_id"
            ],

        "target_surface_type":
            matched_face[
                "surface_type"
            ],

        "target_point":
            target_point,

        "coordinate_scale":
            matched_face[
                "coordinate_scale"
            ],

        "match_score":
            matched_face[
                "match_score"
            ],

        "exact_face_match":
            bool(
                exact_match
            ),

        "centroid_error":
            matched_face[
                "centroid_error"
            ],

        "bbox_min_error":
            matched_face[
                "bbox_min_error"
            ],

        "bbox_max_error":
            matched_face[
                "bbox_max_error"
            ],

        "area_relative_error":
            matched_face[
                "area_relative_error"
            ],

        "source":
            "USER_BREP_FACE_SELECTION",

        "point_source":
            "SCALED_SELECTED_FACE_CENTROID",

        "matched_face_details":
            matched_face
    }


# ============================================================
# GENERIC GROUNDING PIPELINE
# ============================================================

def build_grounding_result(
    instruction_text,
    request_events,
    geometry_map
):
    """
    Full instruction grounding entry point.

    Returns:
        intent
        grounding
    """

    intent = parse_instruction(
        instruction_text
    )

    operation = intent.get(
        "operation"
    )

    # --------------------------------------------------------
    # ADD HOLE
    # --------------------------------------------------------

    if operation == "ADD_HOLE":

        grounding = (
            ground_add_hole_request(

                intent=

                    intent,

                request_events=

                    request_events,

                geometry_map=

                    geometry_map
            )
        )

    # --------------------------------------------------------
    # Future B02 / B03
    # --------------------------------------------------------

    elif operation in {
        "FILLET",
        "CHAMFER"
    }:

        grounding = {
            "status":
                "NOT_IMPLEMENTED",

            "operation":
                operation,

            "selected_edge_events":
                len(
                    get_selected_edges(
                        request_events
                    )
                )
        }

    else:

        grounding = {
            "status":
                "UNKNOWN_OPERATION"
        }

    return {
        "intent":
            intent,

        "grounding":
            grounding
    }


# ============================================================
# SAVE RESULT
# ============================================================

def save_grounding_result(
    grounding_result,
    output_json
):
    """
    Save grounding.json.
    """

    output_json = os.path.abspath(
        output_json
    )

    output_directory = os.path.dirname(
        output_json
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
            grounding_result,
            f,
            indent=4,
            ensure_ascii=False
        )