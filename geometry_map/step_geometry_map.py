# ============================================================
# FILE: step_geometry_map.py
# ASME CIE 2026 STUDENT HACKATHON
#
# COMPONENT:
#     Proposed Deterministic Geometry Map Pipeline
#
# PURPOSE:
#     Convert a STEP CAD model into a structured B-Rep
#     Geometry Map suitable for deterministic feature
#     recognition and CAD editing.
#
# PIPELINE:
#
#     STEP
#       ↓
#     B-Rep geometry extraction
#       ↓
#     Faces + Edges
#       ↓
#     Face ↔ Edge ↔ Face topology
#       ↓
#     Exact geometric parameters
#       ↓
#     Cylinder INTERNAL / EXTERNAL classification
#       ↓
#     geometry_map.json
#
# OUTPUT INFORMATION:
#     - model validity
#     - volume
#     - bounding box
#     - faces
#     - edges
#     - surface types
#     - exact radii / diameters
#     - axes
#     - centers
#     - face-edge topology
#     - face adjacency
#     - INTERNAL / EXTERNAL cylinders
#
# NEXT PIPELINE STAGE:
#     feature_recognition.py
# ============================================================


import os
import json

import numpy as np
import cadquery as cq


# ============================================================
# BASIC HELPERS
# ============================================================

def vec_to_list(v):
    """
    Convert CadQuery Vector to JSON-compatible list.
    """

    return [
        float(v.x),
        float(v.y),
        float(v.z)
    ]


def bbox_to_dict(bbox):
    """
    Convert CadQuery BoundingBox to dictionary.
    """

    return {

        "xmin": float(bbox.xmin),
        "xmax": float(bbox.xmax),

        "ymin": float(bbox.ymin),
        "ymax": float(bbox.ymax),

        "zmin": float(bbox.zmin),
        "zmax": float(bbox.zmax),

        "xlen": float(bbox.xlen),
        "ylen": float(bbox.ylen),
        "zlen": float(bbox.zlen)
    }


# ============================================================
# CYLINDER INTERNAL / EXTERNAL CLASSIFICATION
# ============================================================

def classify_cylinder_orientation(
    face,
    cylinder,
    internal_threshold=-0.2,
    external_threshold=0.2
):
    """
    Determine whether a cylindrical face is INTERNAL
    or EXTERNAL.

    Principle
    ---------
    1. Determine the radial direction from cylinder axis
       toward a point on the cylindrical face.

    2. Obtain the actual B-Rep face normal.

    3. Compare them using dot product.

       dot ≈ +1
           surface normal points away from cylinder axis
           -> EXTERNAL CYLINDER

       dot ≈ -1
           surface normal points toward cylinder axis
           -> INTERNAL CYLINDER

    This is deterministic geometric classification.
    """

    try:

        # ----------------------------------------------------
        # Cylinder axis
        # ----------------------------------------------------

        axis = cylinder.Axis().Direction()

        axis_vector = np.array(
            [
                axis.X(),
                axis.Y(),
                axis.Z()
            ],
            dtype=float
        )

        axis_norm = np.linalg.norm(
            axis_vector
        )

        if axis_norm < 1e-12:
            return "UNKNOWN", None

        axis_vector /= axis_norm

        # ----------------------------------------------------
        # Point on cylinder axis
        # ----------------------------------------------------

        location = cylinder.Location()

        axis_location = np.array(
            [
                location.X(),
                location.Y(),
                location.Z()
            ],
            dtype=float
        )

        # ----------------------------------------------------
        # Representative point on face
        # ----------------------------------------------------

        center = face.Center()

        face_point = np.array(
            [
                center.x,
                center.y,
                center.z
            ],
            dtype=float
        )

        # ----------------------------------------------------
        # Actual B-Rep face normal
        # ----------------------------------------------------

        normal = face.normalAt()

        normal_vector = np.array(
            [
                normal.x,
                normal.y,
                normal.z
            ],
            dtype=float
        )

        normal_norm = np.linalg.norm(
            normal_vector
        )

        if normal_norm < 1e-12:
            return "UNKNOWN", None

        normal_vector /= normal_norm

        # ----------------------------------------------------
        # Axis → face vector
        # ----------------------------------------------------

        delta = (
            face_point
            - axis_location
        )

        # Remove component parallel to cylinder axis
        axial_component = (
            np.dot(
                delta,
                axis_vector
            )
            * axis_vector
        )

        radial_vector = (
            delta
            - axial_component
        )

        radial_norm = np.linalg.norm(
            radial_vector
        )

        if radial_norm < 1e-12:
            return "UNKNOWN", None

        radial_unit = (
            radial_vector
            / radial_norm
        )

        # ----------------------------------------------------
        # Orientation
        # ----------------------------------------------------

        orientation_dot = float(
            np.dot(
                normal_vector,
                radial_unit
            )
        )

        if orientation_dot <= internal_threshold:

            classification = "INTERNAL"

        elif orientation_dot >= external_threshold:

            classification = "EXTERNAL"

        else:

            classification = "AMBIGUOUS"

        return (
            classification,
            orientation_dot
        )

    except Exception:

        return "UNKNOWN", None


# ============================================================
# FACE GEOMETRY EXTRACTION
# ============================================================

def get_surface_info(face):
    """
    Extract geometric information from one B-Rep face.
    """

    info = {}

    # --------------------------------------------------------
    # Surface type
    # --------------------------------------------------------

    try:

        geom_type = face.geomType()

    except Exception:

        geom_type = "UNKNOWN"

    info["surface_type"] = geom_type

    # --------------------------------------------------------
    # Area
    # --------------------------------------------------------

    try:

        info["area"] = float(
            face.Area()
        )

    except Exception:

        info["area"] = None

    # --------------------------------------------------------
    # Representative center
    # --------------------------------------------------------

    try:

        info["center"] = vec_to_list(
            face.Center()
        )

    except Exception:

        info["center"] = None

    # --------------------------------------------------------
    # Bounding box
    # --------------------------------------------------------

    try:

        info["bbox"] = bbox_to_dict(
            face.BoundingBox()
        )

    except Exception:

        info["bbox"] = None


    # ========================================================
    # CYLINDER
    # ========================================================

    if geom_type == "CYLINDER":

        try:

            adaptor = face._geomAdaptor()

            cylinder = adaptor.Cylinder()

            radius = float(
                cylinder.Radius()
            )

            axis = (
                cylinder
                .Axis()
                .Direction()
            )

            location = (
                cylinder
                .Location()
            )

            info["radius"] = radius

            info["diameter"] = (
                2.0 * radius
            )

            info["axis"] = [
                float(axis.X()),
                float(axis.Y()),
                float(axis.Z())
            ]

            info["axis_location"] = [
                float(location.X()),
                float(location.Y()),
                float(location.Z())
            ]

            # ------------------------------------------------
            # INTERNAL / EXTERNAL
            # ------------------------------------------------

            orientation, orientation_dot = (
                classify_cylinder_orientation(
                    face,
                    cylinder
                )
            )

            info[
                "cylinder_orientation"
            ] = orientation

            info[
                "orientation_dot"
            ] = orientation_dot

        except Exception as e:

            info[
                "cylinder_error"
            ] = str(e)


    # ========================================================
    # PLANE
    # ========================================================

    elif geom_type == "PLANE":

        try:

            adaptor = face._geomAdaptor()

            plane = adaptor.Plane()

            normal = (
                plane
                .Axis()
                .Direction()
            )

            location = plane.Location()

            info["normal"] = [
                float(normal.X()),
                float(normal.Y()),
                float(normal.Z())
            ]

            info["plane_location"] = [
                float(location.X()),
                float(location.Y()),
                float(location.Z())
            ]

        except Exception as e:

            info[
                "plane_error"
            ] = str(e)


    # ========================================================
    # CONE
    # ========================================================

    elif geom_type == "CONE":

        try:

            adaptor = face._geomAdaptor()

            cone = adaptor.Cone()

            axis = (
                cone
                .Axis()
                .Direction()
            )

            location = (
                cone
                .Location()
            )

            info["semi_angle"] = float(
                cone.SemiAngle()
            )

            info["axis"] = [
                float(axis.X()),
                float(axis.Y()),
                float(axis.Z())
            ]

            info["axis_location"] = [
                float(location.X()),
                float(location.Y()),
                float(location.Z())
            ]

        except Exception as e:

            info[
                "cone_error"
            ] = str(e)


    # ========================================================
    # SPHERE
    # ========================================================

    elif geom_type == "SPHERE":

        try:

            adaptor = face._geomAdaptor()

            sphere = adaptor.Sphere()

            info["radius"] = float(
                sphere.Radius()
            )

            location = (
                sphere.Location()
            )

            info[
                "sphere_center"
            ] = [

                float(location.X()),
                float(location.Y()),
                float(location.Z())
            ]

        except Exception as e:

            info[
                "sphere_error"
            ] = str(e)


    # ========================================================
    # TORUS
    # ========================================================

    elif geom_type == "TORUS":

        try:

            adaptor = face._geomAdaptor()

            torus = adaptor.Torus()

            info[
                "major_radius"
            ] = float(
                torus.MajorRadius()
            )

            info[
                "minor_radius"
            ] = float(
                torus.MinorRadius()
            )

            axis = (
                torus
                .Axis()
                .Direction()
            )

            location = (
                torus
                .Location()
            )

            info["axis"] = [
                float(axis.X()),
                float(axis.Y()),
                float(axis.Z())
            ]

            info["axis_location"] = [
                float(location.X()),
                float(location.Y()),
                float(location.Z())
            ]

        except Exception as e:

            info[
                "torus_error"
            ] = str(e)

    return info


# ============================================================
# EDGE GEOMETRY EXTRACTION
# ============================================================

def get_edge_info(edge):
    """
    Extract geometric information from one B-Rep edge.
    """

    info = {}

    # --------------------------------------------------------
    # Edge curve type
    # --------------------------------------------------------

    try:

        geom_type = edge.geomType()

    except Exception:

        geom_type = "UNKNOWN"

    info["geom_type"] = geom_type


    # --------------------------------------------------------
    # Edge length
    # --------------------------------------------------------

    try:

        info["length"] = float(
            edge.Length()
        )

    except Exception:

        info["length"] = None


    # --------------------------------------------------------
    # Edge center
    # --------------------------------------------------------

    try:

        info["center"] = vec_to_list(
            edge.Center()
        )

    except Exception:

        info["center"] = None


    # --------------------------------------------------------
    # Bounding box
    # --------------------------------------------------------

    try:

        info["bbox"] = bbox_to_dict(
            edge.BoundingBox()
        )

    except Exception:

        info["bbox"] = None


    # ========================================================
    # CIRCLE
    # ========================================================

    if geom_type == "CIRCLE":

        try:

            adaptor = edge._geomAdaptor()

            circle = adaptor.Circle()

            radius = float(
                circle.Radius()
            )

            center = circle.Location()

            axis = (
                circle
                .Axis()
                .Direction()
            )

            info["radius"] = radius

            info["diameter"] = (
                radius * 2.0
            )

            info["circle_center"] = [

                float(center.X()),
                float(center.Y()),
                float(center.Z())
            ]

            info["axis"] = [

                float(axis.X()),
                float(axis.Y()),
                float(axis.Z())
            ]

        except Exception as e:

            info[
                "circle_error"
            ] = str(e)


    # ========================================================
    # LINE
    # ========================================================

    elif geom_type == "LINE":

        try:

            adaptor = edge._geomAdaptor()

            line = adaptor.Line()

            direction = (
                line.Direction()
            )

            location = (
                line.Location()
            )

            info["direction"] = [

                float(direction.X()),
                float(direction.Y()),
                float(direction.Z())
            ]

            info["line_location"] = [

                float(location.X()),
                float(location.Y()),
                float(location.Z())
            ]

        except Exception as e:

            info[
                "line_error"
            ] = str(e)

    return info


# ============================================================
# TOPOLOGICAL EDGE COMPARISON
# ============================================================

def same_edge(
    edge_a,
    edge_b
):
    """
    Compare CadQuery Edge wrappers using underlying
    OpenCascade topology.

    Python object id() must NOT be used because the same
    TopoDS_Edge may be represented by different Python objects.
    """

    try:

        return bool(
            edge_a.isSame(
                edge_b
            )
        )

    except Exception:

        pass

    try:

        return bool(

            edge_a
            .wrapped
            .IsSame(
                edge_b.wrapped
            )
        )

    except Exception:

        return False


def find_same_edge_id(
    local_edge,
    global_edges,
    edge_ids
):
    """
    Find the logical global edge ID corresponding to an edge
    returned through face.Edges().
    """

    for index, global_edge in enumerate(
        global_edges
    ):

        if same_edge(
            local_edge,
            global_edge
        ):

            return edge_ids[index]

    return None


# ============================================================
# GEOMETRY MAP BUILDER
# ============================================================

def build_geometry_map(
    step_file
):
    """
    Build complete B-Rep Geometry Map from STEP.

    Includes:

        model
        ├── faces
        ├── edges
        ├── face -> edge topology
        ├── edge -> face topology
        ├── face adjacency
        └── exact geometric parameters
    """

    step_file = os.path.abspath(
        step_file
    )

    if not os.path.exists(
        step_file
    ):

        raise FileNotFoundError(
            step_file
        )

    print(
        "Loading STEP:"
    )

    print(
        step_file
    )


    # ========================================================
    # LOAD STEP
    # ========================================================

    model = cq.importers.importStep(
        step_file
    )

    shape = model.val()

    print(
        "STEP loaded."
    )


    # ========================================================
    # GET B-REP ENTITIES
    # ========================================================

    faces = shape.Faces()

    edges = shape.Edges()

    print(
        "Faces found:",
        len(faces)
    )

    print(
        "Edges found:",
        len(edges)
    )


    # ========================================================
    # ROOT GEOMETRY MAP
    # ========================================================

    geometry_map = {

        "source_step":
            step_file,

        "is_valid":
            bool(
                shape.isValid()
            ),

        "volume":
            float(
                shape.Volume()
            ),

        "bbox":
            bbox_to_dict(
                shape.BoundingBox()
            ),

        "faces":
            [],

        "edges":
            [],

        "statistics":
            {},

        "topology_statistics":
            {}
    }


    # ========================================================
    # LOGICAL IDs
    # ========================================================

    face_ids = [

        f"F{i + 1:04d}"

        for i in range(
            len(faces)
        )
    ]

    edge_ids = [

        f"E{i + 1:04d}"

        for i in range(
            len(edges)
        )
    ]


    # ========================================================
    # TOPOLOGY MAP STRUCTURES
    # ========================================================

    edge_face_map = {

        edge_id: []

        for edge_id
        in edge_ids
    }

    face_edge_map = {

        face_id: []

        for face_id
        in face_ids
    }


    # ========================================================
    # BUILD FACE ↔ EDGE TOPOLOGY
    # ========================================================

    print(
        "Building topology..."
    )

    unmatched_local_edges = 0


    for face_index, face in enumerate(
        faces
    ):

        face_id = face_ids[
            face_index
        ]

        local_edges = (
            face.Edges()
        )


        for local_edge in local_edges:


            edge_id = find_same_edge_id(

                local_edge,

                edges,

                edge_ids
            )


            if edge_id is None:

                unmatched_local_edges += 1

                continue


            # ------------------------------------------------
            # FACE -> EDGE
            # ------------------------------------------------

            if edge_id not in face_edge_map[
                face_id
            ]:

                face_edge_map[
                    face_id
                ].append(
                    edge_id
                )


            # ------------------------------------------------
            # EDGE -> FACE
            # ------------------------------------------------

            if face_id not in edge_face_map[
                edge_id
            ]:

                edge_face_map[
                    edge_id
                ].append(
                    face_id
                )


    # ========================================================
    # CREATE EDGE RECORDS
    # ========================================================

    for edge_index, edge in enumerate(
        edges
    ):

        edge_id = edge_ids[
            edge_index
        ]

        edge_info = {

            "id":
                edge_id
        }


        try:

            edge_info.update(

                get_edge_info(
                    edge
                )
            )

        except Exception as e:

            edge_info[
                "error"
            ] = str(e)


        edge_info[
            "adjacent_faces"
        ] = sorted(

            edge_face_map[
                edge_id
            ]
        )


        geometry_map[
            "edges"
        ].append(
            edge_info
        )


    # ========================================================
    # CREATE FACE RECORDS
    # ========================================================

    for face_index, face in enumerate(
        faces
    ):

        face_id = face_ids[
            face_index
        ]

        face_info = {

            "id":
                face_id
        }


        try:

            face_info.update(

                get_surface_info(
                    face
                )
            )

        except Exception as e:

            face_info[
                "error"
            ] = str(e)


        # ----------------------------------------------------
        # FACE EDGES
        # ----------------------------------------------------

        face_info[
            "edges"
        ] = sorted(

            face_edge_map[
                face_id
            ]
        )


        # ----------------------------------------------------
        # ADJACENT FACES
        # ----------------------------------------------------

        adjacent_faces = set()


        for edge_id in face_info[
            "edges"
        ]:


            for other_face_id in edge_face_map[
                edge_id
            ]:


                if (
                    other_face_id
                    != face_id
                ):

                    adjacent_faces.add(
                        other_face_id
                    )


        face_info[
            "adjacent_faces"
        ] = sorted(
            adjacent_faces
        )


        geometry_map[
            "faces"
        ].append(
            face_info
        )


    # ========================================================
    # TOPOLOGY STATISTICS
    # ========================================================

    connected_edges = sum(

        1

        for edge_id
        in edge_ids

        if len(
            edge_face_map[
                edge_id
            ]
        ) > 0
    )


    shared_edges = sum(

        1

        for edge_id
        in edge_ids

        if len(
            edge_face_map[
                edge_id
            ]
        ) >= 2
    )


    boundary_edges = sum(

        1

        for edge_id
        in edge_ids

        if len(
            edge_face_map[
                edge_id
            ]
        ) == 1
    )


    geometry_map[
        "topology_statistics"
    ] = {

        "total_faces":
            len(faces),

        "total_edges":
            len(edges),

        "connected_edges":
            connected_edges,

        "shared_edges":
            shared_edges,

        "boundary_edges":
            boundary_edges,

        "unmatched_local_edges":
            unmatched_local_edges
    }


    # ========================================================
    # GEOMETRY STATISTICS
    # ========================================================

    cylindrical_faces = [

        face

        for face
        in geometry_map["faces"]

        if face.get(
            "surface_type"
        ) == "CYLINDER"
    ]


    internal_cylinders = [

        face

        for face
        in cylindrical_faces

        if face.get(
            "cylinder_orientation"
        ) == "INTERNAL"
    ]


    external_cylinders = [

        face

        for face
        in cylindrical_faces

        if face.get(
            "cylinder_orientation"
        ) == "EXTERNAL"
    ]


    ambiguous_cylinders = [

        face

        for face
        in cylindrical_faces

        if face.get(
            "cylinder_orientation"
        ) not in [
            "INTERNAL",
            "EXTERNAL"
        ]
    ]


    circular_edges = [

        edge

        for edge
        in geometry_map["edges"]

        if edge.get(
            "geom_type"
        ) == "CIRCLE"
    ]


    geometry_map[
        "statistics"
    ] = {

        "total_faces":
            len(faces),

        "total_edges":
            len(edges),

        "cylindrical_faces":
            len(
                cylindrical_faces
            ),

        "internal_cylinders":
            len(
                internal_cylinders
            ),

        "external_cylinders":
            len(
                external_cylinders
            ),

        "ambiguous_cylinders":
            len(
                ambiguous_cylinders
            ),

        "circular_edges":
            len(
                circular_edges
            )
    }


    # ========================================================
    # CONSOLE REPORT
    # ========================================================

    print(
        "Topology built."
    )

    print(
        "Connected edges:",
        connected_edges
    )

    print(
        "Shared edges:",
        shared_edges
    )

    print(
        "Boundary edges:",
        boundary_edges
    )

    print(
        "Unmatched local edges:",
        unmatched_local_edges
    )

    print()

    print(
        "Cylindrical faces:",
        len(
            cylindrical_faces
        )
    )

    print(
        "Internal cylinders:",
        len(
            internal_cylinders
        )
    )

    print(
        "External cylinders:",
        len(
            external_cylinders
        )
    )

    print(
        "Ambiguous cylinders:",
        len(
            ambiguous_cylinders
        )
    )

    print(
        "Circular edges:",
        len(
            circular_edges
        )
    )


    return geometry_map


# ============================================================
# SAVE GEOMETRY MAP
# ============================================================

def save_geometry_map(
    geometry_map,
    output_json
):
    """
    Save Geometry Map as formatted JSON.
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

            geometry_map,

            f,

            indent=4,

            ensure_ascii=False
        )


    print()

    print(
        "Geometry map saved:"
    )

    print(
        output_json
    )


# ============================================================
# PUBLIC PIPELINE FUNCTION
# ============================================================

def step_to_geometry_map(
    step_file,
    output_json
):
    """
    Public entry point.

    INPUT
        STEP CAD model

    OUTPUT
        Structured deterministic Geometry Map JSON
    """

    geometry_map = (
        build_geometry_map(
            step_file
        )
    )


    save_geometry_map(

        geometry_map,

        output_json
    )


    return geometry_map