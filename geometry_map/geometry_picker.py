# ============================================================
# FILE: geometry_picker.py
# ASME CIE 2026 STUDENT HACKATHON
#
# METHOD:
#     Semi-Automatic Geometric Mapping for
#     Deterministic CAD Editing
#
# PURPOSE:
#     Universal interactive spatial-grounding interface.
#
#     The natural-language instruction determines:
#
#         WHAT to do
#         WHAT PARAMETER to use
#
#     The engineer/user determines:
#
#         WHERE to do it
#
#     by clicking directly on the 3D model.
#
# SUPPORTED SELECTION MODES:
#
#     POINT
#         Example B01:
#         "Add a hole of 2 mm here"
#
#         Output:
#             face_id
#             point_xyz
#
#     FACE
#         Output:
#             face_id
#
#     EDGE
#         Output:
#             edge_id
#
#     MULTI_EDGE
#         Example B02:
#         "Add fillet of 0.2 mm along the sharp edges"
#
#         Output:
#             edge_ids = [...]
#
#
# ARCHITECTURE:
#
#     Natural Language Instruction
#                 ↓
#          WHAT + PARAMETER
#                 ↓
#                STEP
#                 ↓
#        geometry_picker.py
#                 ↓
#        User selects WHERE
#                 ↓
#        Exact B-Rep mapping
#                 ↓
#         edit_request.json
#                 ↓
#       deterministic_edit.py
#                 ↓
#          Exact edited STEP
#
#
# IMPORTANT:
#
#     - Fusion 360 is NOT required.
#     - Ground Truth is NOT used.
#     - User does NOT manually model anything.
#     - User only selects geometric targets.
#     - Exact CAD operation is executed later.
#
#
# B02 USER CONTROLS:
#
#     Mouse:
#         Left drag   = rotate
#         Wheel       = zoom
#         Right click = select edge
#
#     Keyboard:
#         ENTER = finish selection and save
#         U     = undo last selection
#         C     = clear selection
#         Q     = close viewer
#
# ============================================================


import os
import json
import tempfile
import math

import numpy as np
import cadquery as cq
import pyvista as pv


# ============================================================
# SETTINGS
# ============================================================

EDGE_PICK_MAX_DISTANCE_MM = 2.0

EDGE_DISPLAY_SAMPLES = 40

VIEWER_STL_TOLERANCE = 0.15

VIEWER_STL_ANGULAR_TOLERANCE = 0.20


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_vector(vector):

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

    return (
        vector / norm
    )


def vector_to_numpy(vector):

    return np.array(
        [
            float(vector.x),
            float(vector.y),
            float(vector.z)
        ],
        dtype=float
    )


# ============================================================
# STEP LOADER
# ============================================================

def load_step_shape(step_file):

    step_file = os.path.abspath(
        step_file
    )

    if not os.path.exists(
        step_file
    ):

        raise FileNotFoundError(
            f"STEP file not found:\n{step_file}"
        )

    model = cq.importers.importStep(
        step_file
    )

    shape = model.val()

    if shape is None:

        raise RuntimeError(
            "CadQuery did not return a shape."
        )

    if not shape.isValid():

        raise RuntimeError(
            "STEP geometry is invalid."
        )

    return shape


# ============================================================
# EDIT REQUEST
# ============================================================

def load_edit_request(
    edit_request_json
):

    edit_request_json = os.path.abspath(
        edit_request_json
    )

    if not os.path.exists(
        edit_request_json
    ):

        raise FileNotFoundError(
            f"edit_request.json not found:\n"
            f"{edit_request_json}"
        )

    with open(
        edit_request_json,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(
            f
        )


def save_edit_request(
    request,
    edit_request_json
):

    edit_request_json = os.path.abspath(
        edit_request_json
    )

    output_dir = os.path.dirname(
        edit_request_json
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True
        )

    with open(
        edit_request_json,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            request,
            f,
            indent=4,
            ensure_ascii=False
        )


# ============================================================
# TEMP STL FOR VIEWER
# ============================================================

def create_viewer_stl(
    shape
):

    temp_dir = tempfile.mkdtemp(
        prefix="asme_geometry_picker_"
    )

    stl_file = os.path.join(
        temp_dir,
        "viewer_model.stl"
    )

    cq.exporters.export(
        shape,
        stl_file,
        tolerance=
            VIEWER_STL_TOLERANCE,
        angularTolerance=
            VIEWER_STL_ANGULAR_TOLERANCE
    )

    if not os.path.exists(
        stl_file
    ):

        raise RuntimeError(
            "Could not create viewer STL."
        )

    return stl_file


# ============================================================
# B-REP IDS
# ============================================================

def face_id_from_index(
    index
):

    return (
        f"F{index + 1:04d}"
    )


def edge_id_from_index(
    index
):

    return (
        f"E{index + 1:04d}"
    )


# ============================================================
# POINT -> FACE
# ============================================================

def find_nearest_face(
    shape,
    point_xyz
):

    point_xyz = np.asarray(
        point_xyz,
        dtype=float
    )

    vertex = cq.Vertex.makeVertex(
        float(point_xyz[0]),
        float(point_xyz[1]),
        float(point_xyz[2])
    )

    results = []

    for index, face in enumerate(
        shape.Faces()
    ):

        try:

            distance = float(
                face.distance(
                    vertex
                )
            )

        except Exception:

            continue

        results.append(
            {
                "face_id":
                    face_id_from_index(
                        index
                    ),

                "face_index":
                    index,

                "distance_mm":
                    distance,

                "surface_type":
                    face.geomType()
            }
        )

    if not results:

        raise RuntimeError(
            "Could not map point to B-Rep face."
        )

    results.sort(
        key=lambda x:
            x[
                "distance_mm"
            ]
    )

    return results[0]


# ============================================================
# POINT -> EDGE
# ============================================================

def find_nearest_edge(
    shape,
    point_xyz
):

    point_xyz = np.asarray(
        point_xyz,
        dtype=float
    )

    vertex = cq.Vertex.makeVertex(
        float(point_xyz[0]),
        float(point_xyz[1]),
        float(point_xyz[2])
    )

    results = []

    for index, edge in enumerate(
        shape.Edges()
    ):

        try:

            distance = float(
                edge.distance(
                    vertex
                )
            )

        except Exception:

            continue

        results.append(
            {
                "edge_id":
                    edge_id_from_index(
                        index
                    ),

                "edge_index":
                    index,

                "distance_mm":
                    distance,

                "curve_type":
                    edge.geomType(),

                "length_mm":
                    float(
                        edge.Length()
                    )
            }
        )

    if not results:

        raise RuntimeError(
            "Could not map point to B-Rep edge."
        )

    results.sort(
        key=lambda x:
            x[
                "distance_mm"
            ]
    )

    return results[0]


# ============================================================
# EDGE DISPLAY GEOMETRY
# ============================================================

def discretize_edge(
    edge,
    number_of_points=EDGE_DISPLAY_SAMPLES
):
    """
    Create points along exact B-Rep edge for highlighting.
    """

    try:

        points = edge.discretize(
            n=number_of_points
        )

    except Exception:

        # fallback using normalized positions

        points = []

        for i in range(
            number_of_points
        ):

            t = (
                i
                / max(
                    number_of_points - 1,
                    1
                )
            )

            try:

                point = edge.positionAt(
                    t
                )

                points.append(
                    point
                )

            except Exception:

                pass


    xyz = []

    for point in points:

        try:

            xyz.append(
                [
                    float(point.x),
                    float(point.y),
                    float(point.z)
                ]
            )

        except Exception:

            pass


    return np.asarray(
        xyz,
        dtype=float
    )


def create_edge_polydata(
    edge
):
    """
    Convert B-Rep edge to PyVista polyline.
    """

    points = discretize_edge(
        edge
    )

    if len(points) < 2:

        return None

    poly = pv.PolyData()

    poly.points = points

    line = np.hstack(
        [
            [
                len(points)
            ],

            np.arange(
                len(points)
            )
        ]
    )

    poly.lines = line

    return poly


# ============================================================
# UPDATE REQUEST — POINT
# ============================================================

def update_point_target(
    request,
    point_xyz,
    face_match
):

    request[
        "target"
    ] = {

        "entity_type":
            "POINT_ON_FACE",

        "face_id":
            face_match[
                "face_id"
            ],

        "point_xyz":
            [
                float(x)
                for x in point_xyz
            ],

        "surface_type":
            face_match[
                "surface_type"
            ],

        "brep_match_distance_mm":
            float(
                face_match[
                    "distance_mm"
                ]
            ),

        "source":
            "USER_3D_SELECTION"
    }

    return request


# ============================================================
# UPDATE REQUEST — FACE
# ============================================================

def update_face_target(
    request,
    face_match
):

    request[
        "target"
    ] = {

        "entity_type":
            "FACE",

        "face_id":
            face_match[
                "face_id"
            ],

        "surface_type":
            face_match[
                "surface_type"
            ],

        "brep_match_distance_mm":
            float(
                face_match[
                    "distance_mm"
                ]
            ),

        "source":
            "USER_3D_SELECTION"
    }

    return request


# ============================================================
# UPDATE REQUEST — EDGES
# ============================================================

def update_edge_target(
    request,
    selected_edges
):

    edge_ids = [
        item[
            "edge_id"
        ]
        for item in selected_edges
    ]

    request[
        "target"
    ] = {

        "entity_type":
            (
                "EDGE"
                if len(edge_ids) == 1
                else "EDGES"
            ),

        "edge_ids":
            edge_ids,

        "selection_count":
            len(
                edge_ids
            ),

        "source":
            "USER_3D_SELECTION"
    }

    return request


# ============================================================
# INSTRUCTION TEXT
# ============================================================

def build_instruction_message(
    request,
    mode
):

    instruction = request.get(
        "instruction",
        ""
    )

    operation = request.get(
        "operation",
        ""
    )

    parameters = request.get(
        "parameters",
        {}
    )


    if mode == "POINT":

        return (
            f"{instruction}\n\n"
            "RIGHT CLICK the exact target point.\n"
            "Press ENTER when finished."
        )


    if mode == "FACE":

        return (
            f"{instruction}\n\n"
            "RIGHT CLICK the required face.\n"
            "Press ENTER when finished."
        )


    if mode == "EDGE":

        return (
            f"{instruction}\n\n"
            "RIGHT CLICK the required edge.\n"
            "Press ENTER when finished."
        )


    if mode == "MULTI_EDGE":

        radius = parameters.get(
            "radius_mm"
        )

        extra = ""

        if radius is not None:

            extra = (
                f"\nFillet radius: {radius} mm"
            )

        return (
            f"{instruction}"
            f"{extra}\n\n"
            "RIGHT CLICK each required edge.\n"
            "Selected edges will be highlighted.\n\n"
            "ENTER = finish\n"
            "U = undo\n"
            "C = clear"
        )


    return instruction


# ============================================================
# MAIN UNIVERSAL PICKER
# ============================================================

def run_geometry_picker(
    step_file,
    edit_request_json,
    mode="MULTI_EDGE"
):
    """
    Universal interactive geometry selector.

    mode:
        POINT
        FACE
        EDGE
        MULTI_EDGE
    """

    mode = str(
        mode
    ).upper()


    valid_modes = {
        "POINT",
        "FACE",
        "EDGE",
        "MULTI_EDGE"
    }


    if mode not in valid_modes:

        raise ValueError(
            f"Unsupported selection mode: {mode}"
        )


    print("=" * 78)
    print("ASME — SEMI-AUTOMATIC GEOMETRY PICKER")
    print("=" * 78)

    print(
        "Selection mode:",
        mode
    )

    print(
        "STEP:",
        step_file
    )

    print(
        "Request:",
        edit_request_json
    )


    # ========================================================
    # LOAD
    # ========================================================

    print("\nLoading STEP...")

    shape = load_step_shape(
        step_file
    )

    print(
        "STEP loaded."
    )

    print(
        "Faces:",
        len(
            shape.Faces()
        )
    )

    print(
        "Edges:",
        len(
            shape.Edges()
        )
    )


    request = load_edit_request(
        edit_request_json
    )


    print("\nINSTRUCTION")

    print(
        request.get(
            "instruction"
        )
    )

    print(
        "Operation:",
        request.get(
            "operation"
        )
    )

    print(
        "Parameters:",
        request.get(
            "parameters"
        )
    )


    # ========================================================
    # VIEWER MESH
    # ========================================================

    print(
        "\nPreparing 3D viewer..."
    )

    viewer_stl = create_viewer_stl(
        shape
    )

    mesh = pv.read(
        viewer_stl
    )

    print(
        "Viewer ready."
    )


    # ========================================================
    # STATE
    # ========================================================

    state = {

        "mode":
            mode,

        "finished":
            False,

        "selected_point":
            None,

        "selected_face":
            None,

        "selected_edges":
            [],

        "highlight_actors":
            []
    }


    # ========================================================
    # PLOTTER
    # ========================================================

    plotter = pv.Plotter(
        title=(
            "ASME Semi-Automatic Geometric Mapping"
        )
    )


    plotter.add_mesh(
        mesh,
        show_edges=True,
        pickable=True,
        opacity=1.0
    )


    instruction_message = (
        build_instruction_message(
            request,
            mode
        )
    )


    plotter.add_text(
        instruction_message,
        position="upper_left",
        font_size=10,
        name="instruction"
    )


    # ========================================================
    # STATUS DISPLAY
    # ========================================================

    def update_status():

        if mode == "MULTI_EDGE":

            selected_ids = [
                item[
                    "edge_id"
                ]
                for item
                in state[
                    "selected_edges"
                ]
            ]

            text = (
                f"Selected edges: "
                f"{len(selected_ids)}\n"
            )

            if selected_ids:

                text += ", ".join(
                    selected_ids[-8:]
                )

            plotter.add_text(
                text,
                position="lower_left",
                font_size=10,
                name="selection_status"
            )


    update_status()


    # ========================================================
    # HIGHLIGHT EDGE
    # ========================================================

    def highlight_edge(
        edge_match
    ):

        edge_index = edge_match[
            "edge_index"
        ]

        edge = shape.Edges()[
            edge_index
        ]

        poly = create_edge_polydata(
            edge
        )

        if poly is None:

            return None


        actor = plotter.add_mesh(
            poly,
            line_width=8,
            render_lines_as_tubes=True
        )

        return actor


    # ========================================================
    # REMOVE HIGHLIGHTS
    # ========================================================

    def rebuild_edge_highlights():

        for actor in state[
            "highlight_actors"
        ]:

            try:

                plotter.remove_actor(
                    actor
                )

            except Exception:

                pass


        state[
            "highlight_actors"
        ] = []


        for edge_match in state[
            "selected_edges"
        ]:

            actor = highlight_edge(
                edge_match
            )

            if actor is not None:

                state[
                    "highlight_actors"
                ].append(
                    actor
                )


        update_status()

        plotter.render()


    # ========================================================
    # PICK CALLBACK
    # ========================================================

    def on_surface_pick(
        point
    ):

        if point is None:

            return


        point_xyz = np.asarray(
            point,
            dtype=float
        )


        print("\n" + "-" * 70)

        print(
            "CLICK XYZ:",
            point_xyz.tolist()
        )


        # ====================================================
        # POINT MODE
        # ====================================================

        if mode == "POINT":

            face_match = find_nearest_face(
                shape,
                point_xyz
            )

            state[
                "selected_point"
            ] = point_xyz.tolist()

            state[
                "selected_face"
            ] = face_match


            print(
                "Face:",
                face_match[
                    "face_id"
                ]
            )

            print(
                "Surface:",
                face_match[
                    "surface_type"
                ]
            )

            print(
                "Distance:",
                face_match[
                    "distance_mm"
                ],
                "mm"
            )

            return


        # ====================================================
        # FACE MODE
        # ====================================================

        if mode == "FACE":

            face_match = find_nearest_face(
                shape,
                point_xyz
            )

            state[
                "selected_face"
            ] = face_match


            print(
                "Selected face:",
                face_match[
                    "face_id"
                ]
            )

            return


        # ====================================================
        # EDGE / MULTI_EDGE
        # ====================================================

        edge_match = find_nearest_edge(
            shape,
            point_xyz
        )


        print(
            "Nearest edge:",
            edge_match[
                "edge_id"
            ]
        )

        print(
            "Curve:",
            edge_match[
                "curve_type"
            ]
        )

        print(
            "Length:",
            edge_match[
                "length_mm"
            ],
            "mm"
        )

        print(
            "Distance from click:",
            edge_match[
                "distance_mm"
            ],
            "mm"
        )


        # ----------------------------------------------------
        # Avoid accidental distant edge picks
        # ----------------------------------------------------

        if (
            edge_match[
                "distance_mm"
            ]
            >
            EDGE_PICK_MAX_DISTANCE_MM
        ):

            print(
                "Selection ignored: "
                "click is too far from an edge."
            )

            return


        # ====================================================
        # SINGLE EDGE
        # ====================================================

        if mode == "EDGE":

            state[
                "selected_edges"
            ] = [
                edge_match
            ]

            rebuild_edge_highlights()

            return


        # ====================================================
        # MULTI EDGE — TOGGLE
        # ====================================================

        existing_ids = [
            item[
                "edge_id"
            ]

            for item in state[
                "selected_edges"
            ]
        ]


        edge_id = edge_match[
            "edge_id"
        ]


        if edge_id in existing_ids:

            # clicking same edge again deselects it

            state[
                "selected_edges"
            ] = [
                item

                for item
                in state[
                    "selected_edges"
                ]

                if item[
                    "edge_id"
                ]
                != edge_id
            ]

            print(
                "Deselected:",
                edge_id
            )

        else:

            state[
                "selected_edges"
            ].append(
                edge_match
            )

            print(
                "Selected:",
                edge_id
            )


        rebuild_edge_highlights()


    # ========================================================
    # UNDO
    # ========================================================

    def undo_selection():

        if not state[
            "selected_edges"
        ]:

            print(
                "Nothing to undo."
            )

            return


        removed = state[
            "selected_edges"
        ].pop()


        print(
            "Undo:",
            removed[
                "edge_id"
            ]
        )


        rebuild_edge_highlights()


    # ========================================================
    # CLEAR
    # ========================================================

    def clear_selection():

        state[
            "selected_edges"
        ] = []


        print(
            "Selection cleared."
        )


        rebuild_edge_highlights()


    # ========================================================
    # FINISH
    # ========================================================

    def finish_selection():

        print("\n" + "=" * 78)
        print("FINISH SELECTION")
        print("=" * 78)


        # ----------------------------------------------------
        # POINT
        # ----------------------------------------------------

        if mode == "POINT":

            if (
                state[
                    "selected_point"
                ]
                is None
            ):

                print(
                    "No target point selected."
                )

                return


            updated = update_point_target(
                request=
                    request,

                point_xyz=
                    state[
                        "selected_point"
                    ],

                face_match=
                    state[
                        "selected_face"
                    ]
            )


        # ----------------------------------------------------
        # FACE
        # ----------------------------------------------------

        elif mode == "FACE":

            if (
                state[
                    "selected_face"
                ]
                is None
            ):

                print(
                    "No face selected."
                )

                return


            updated = update_face_target(
                request=
                    request,

                face_match=
                    state[
                        "selected_face"
                    ]
            )


        # ----------------------------------------------------
        # EDGE / MULTI_EDGE
        # ----------------------------------------------------

        else:

            if not state[
                "selected_edges"
            ]:

                print(
                    "No edges selected."
                )

                return


            updated = update_edge_target(
                request=
                    request,

                selected_edges=
                    state[
                        "selected_edges"
                    ]
            )


        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        save_edit_request(
            updated,
            edit_request_json
        )


        state[
            "finished"
        ] = True


        print(
            "Selection saved:"
        )

        print(
            edit_request_json
        )


        if mode in {
            "EDGE",
            "MULTI_EDGE"
        }:

            print(
                "Selected edge IDs:"
            )

            print(
                [
                    item[
                        "edge_id"
                    ]

                    for item
                    in state[
                        "selected_edges"
                    ]
                ]
            )


        print(
            "\nYou can close the viewer with Q."
        )


    # ========================================================
    # KEY EVENTS
    # ========================================================

    plotter.add_key_event(
        "u",
        undo_selection
    )

    plotter.add_key_event(
        "c",
        clear_selection
    )


    # PyVista/VTK environments can report ENTER differently.
    try:

        plotter.add_key_event(
            "Return",
            finish_selection
        )

    except Exception:

        pass


    try:

        plotter.add_key_event(
            "Enter",
            finish_selection
        )

    except Exception:

        pass


    # Alternative key in case notebook backend
    # does not propagate Enter correctly.
    plotter.add_key_event(
        "s",
        finish_selection
    )


    # ========================================================
    # SURFACE PICKING
    # ========================================================

    plotter.enable_surface_point_picking(

        callback=
            on_surface_pick,

        show_message=False,

        show_point=True,

        point_size=14,

        pickable_window=False,

        left_clicking=False,

        picker="cell"
    )


    # ========================================================
    # VIEW
    # ========================================================

    plotter.show_axes()

    plotter.reset_camera()


    # ========================================================
    # RUN
    # ========================================================

    plotter.show()


    # ========================================================
    # RETURN
    # ========================================================

    print("\n" + "=" * 78)
    print("GEOMETRY PICKER FINISHED")
    print("=" * 78)

    print(
        "Saved:",
        state[
            "finished"
        ]
    )


    return state


# ============================================================
# COMMAND-LINE MESSAGE
# ============================================================

if __name__ == "__main__":

    print(
        "geometry_picker.py loaded."
    )

    print(
        "Use run_geometry_picker("
        "step_file, edit_request_json, mode)"
    )