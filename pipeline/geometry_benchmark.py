# ============================================================
# FILE: pipeline/geometry_benchmark.py
# ASME CIE 2026 STUDENT HACKATHON
#
# COMMON GEOMETRY BENCHMARK
#
# PURPOSE:
#
#     Evaluate CAD results using exactly the SAME metric
#     implementation for:
#
#         AUTODESK neuralCAD-Edit
#
#         GEOMETRIC_MAPPING
#
#
# INPUT:
#
#     START STEP
#     RESULT STEP
#     GT STEP
#
#
# METRICS:
#
#     1. Voxel IoU
#
#     2. Volumetric:
#           precision
#           recall
#           F1
#
#     3. Difference:
#           precision
#           recall
#           F1
#
#     4. Added geometry:
#           precision
#           recall
#           F1
#
#     5. Removed geometry:
#           precision
#           recall
#           F1
#
#     6. Surface Chamfer Distance
#
#     7. Chamfer Similarity
#
#
# IMPORTANT:
#
#     This evaluator is method-independent.
#
#     GT is NEVER used for CAD generation.
#
#     If GT does not exist / is not confirmed:
#
#         metrics.status = NOT_AVAILABLE
#
# ============================================================


import os
import json
import math
import time
from pathlib import Path

import numpy as np
import cadquery as cq


# ============================================================
# OPTIONAL DEPENDENCIES
# ============================================================

try:

    import trimesh

except ImportError:

    trimesh = None


try:

    from scipy.spatial import cKDTree

except ImportError:

    cKDTree = None


# ============================================================
# DEFAULT PARAMETERS
# ============================================================

DEFAULT_VOXEL_DIVISOR = 100

DEFAULT_SURFACE_SAMPLES = 50000

DEFAULT_TESSELLATION_TOLERANCE = 0.1

DEFAULT_ANGULAR_TOLERANCE = 0.1

EPS = 1e-12


# ============================================================
# CONSOLE
# ============================================================

def header(title):

    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


# ============================================================
# JSON
# ============================================================

def load_json(path):

    if not path:

        return None

    if not os.path.exists(path):

        return None

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


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
# SAFE VALUES
# ============================================================

def safe_float(value):

    try:

        if value is None:

            return None

        value = float(
            value
        )

        if not math.isfinite(
            value
        ):

            return None

        return value

    except Exception:

        return None


# ============================================================
# STEP LOAD
# ============================================================

def load_step(path):

    if not os.path.exists(
        path
    ):

        raise FileNotFoundError(
            path
        )

    shape = cq.importers.importStep(
        path
    ).val()

    if shape is None:

        raise RuntimeError(
            f"Could not load STEP:\n{path}"
        )

    return shape


# ============================================================
# BASIC GEOMETRY STATISTICS
# ============================================================

def geometry_stats(shape):

    solids = shape.Solids()

    volume = sum(
        float(
            solid.Volume()
        )
        for solid in solids
    )

    bbox = shape.BoundingBox()

    x = float(
        bbox.xlen
    )

    y = float(
        bbox.ylen
    )

    z = float(
        bbox.zlen
    )

    diagonal = math.sqrt(
        x * x
        +
        y * y
        +
        z * z
    )

    return {

        "valid":
            bool(
                shape.isValid()
            ),

        "solids":
            len(
                solids
            ),

        "faces":
            len(
                shape.Faces()
            ),

        "edges":
            len(
                shape.Edges()
            ),

        "volume_mm3":
            float(
                volume
            ),

        "bounding_box_mm": {

            "x":
                x,

            "y":
                y,

            "z":
                z,

            "diagonal":
                diagonal
        }
    }


# ============================================================
# CADQUERY SHAPE -> TRIANGLE MESH
# ============================================================

def shape_to_trimesh(
    shape,
    tolerance=DEFAULT_TESSELLATION_TOLERANCE,
    angular_tolerance=DEFAULT_ANGULAR_TOLERANCE
):

    if trimesh is None:

        raise RuntimeError(
            "trimesh is not installed.\n"
            "Install with:\n"
            "pip install trimesh"
        )

    all_vertices = []

    all_faces = []

    vertex_offset = 0


    # --------------------------------------------------------
    # Tessellate face by face.
    # --------------------------------------------------------

    for face in shape.Faces():

        try:

            vertices, triangles = face.tessellate(
                tolerance,
                angular_tolerance
            )

        except TypeError:

            # Compatibility with CadQuery versions accepting
            # only tolerance.

            vertices, triangles = face.tessellate(
                tolerance
            )


        if not vertices:

            continue


        local_vertices = []

        for vertex in vertices:

            local_vertices.append(
                [
                    float(
                        vertex.x
                    ),
                    float(
                        vertex.y
                    ),
                    float(
                        vertex.z
                    )
                ]
            )


        local_faces = []

        for triangle in triangles:

            try:

                a = int(
                    triangle[0]
                )

                b = int(
                    triangle[1]
                )

                c = int(
                    triangle[2]
                )

            except Exception:

                # Some wrappers expose triangle indices
                # through attributes.

                a = int(
                    triangle.a
                )

                b = int(
                    triangle.b
                )

                c = int(
                    triangle.c
                )


            local_faces.append(
                [
                    a + vertex_offset,
                    b + vertex_offset,
                    c + vertex_offset
                ]
            )


        all_vertices.extend(
            local_vertices
        )

        all_faces.extend(
            local_faces
        )

        vertex_offset += len(
            local_vertices
        )


    if not all_vertices:

        raise RuntimeError(
            "STEP tessellation produced no vertices."
        )


    if not all_faces:

        raise RuntimeError(
            "STEP tessellation produced no triangles."
        )


    mesh = trimesh.Trimesh(

        vertices=np.asarray(
            all_vertices,
            dtype=np.float64
        ),

        faces=np.asarray(
            all_faces,
            dtype=np.int64
        ),

        process=True
    )


    return mesh


# ============================================================
# COMMON VOXEL PITCH
# ============================================================

def determine_voxel_pitch(
    start_stats,
    result_stats,
    gt_stats,
    voxel_divisor
):

    diagonals = [

        start_stats[
            "bounding_box_mm"
        ][
            "diagonal"
        ],

        result_stats[
            "bounding_box_mm"
        ][
            "diagonal"
        ],

        gt_stats[
            "bounding_box_mm"
        ][
            "diagonal"
        ]
    ]


    reference_diagonal = max(
        diagonals
    )


    if reference_diagonal <= EPS:

        raise RuntimeError(
            "Invalid model bounding-box diagonal."
        )


    pitch = (
        reference_diagonal
        /
        float(
            voxel_divisor
        )
    )


    return float(
        pitch
    )


# ============================================================
# VOXELIZATION
# ============================================================

def voxelize_mesh(
    mesh,
    pitch
):

    """
    Convert mesh to occupied solid voxel centers.

    trimesh.voxelized() creates surface voxels.
    fill() converts the closed shell to solid occupancy.
    """

    voxel_grid = mesh.voxelized(
        pitch
    )


    try:

        voxel_grid = voxel_grid.fill()

    except Exception:

        # Keep surface voxelization if fill is unavailable.
        pass


    points = np.asarray(
        voxel_grid.points,
        dtype=np.float64
    )


    return points


# ============================================================
# GLOBAL VOXEL INDEX
# ============================================================

def points_to_voxel_set(
    points,
    origin,
    pitch
):

    if points is None:

        return set()


    if len(
        points
    ) == 0:

        return set()


    indices = np.rint(

        (
            points
            -
            origin
        )
        /
        pitch

    ).astype(
        np.int64
    )


    return set(
        map(
            tuple,
            indices
        )
    )


# ============================================================
# PRECISION / RECALL / F1
# ============================================================

def precision_recall_f1(
    predicted,
    reference
):

    predicted = set(
        predicted
    )

    reference = set(
        reference
    )


    tp = len(
        predicted
        &
        reference
    )


    fp = len(
        predicted
        -
        reference
    )


    fn = len(
        reference
        -
        predicted
    )


    # --------------------------------------------------------
    # Empty-set handling
    # --------------------------------------------------------

    if (
        len(
            predicted
        )
        ==
        0
        and
        len(
            reference
        )
        ==
        0
    ):

        precision = 1.0
        recall = 1.0
        f1 = 1.0


    else:

        precision = (

            tp
            /
            (
                tp
                +
                fp
            )

            if
            (
                tp
                +
                fp
            )
            >
            0

            else
            0.0
        )


        recall = (

            tp
            /
            (
                tp
                +
                fn
            )

            if
            (
                tp
                +
                fn
            )
            >
            0

            else
            0.0
        )


        if (
            precision
            +
            recall
        ) > EPS:

            f1 = (
                2.0
                *
                precision
                *
                recall
                /
                (
                    precision
                    +
                    recall
                )
            )

        else:

            f1 = 0.0


    return {

        "tp":
            int(
                tp
            ),

        "fp":
            int(
                fp
            ),

        "fn":
            int(
                fn
            ),

        "precision":
            float(
                precision
            ),

        "recall":
            float(
                recall
            ),

        "f1":
            float(
                f1
            )
    }


# ============================================================
# VOXEL IoU
# ============================================================

def voxel_iou(
    predicted,
    reference
):

    predicted = set(
        predicted
    )

    reference = set(
        reference
    )


    union = (
        predicted
        |
        reference
    )


    if not union:

        return 1.0


    intersection = (
        predicted
        &
        reference
    )


    return float(
        len(
            intersection
        )
        /
        len(
            union
        )
    )


# ============================================================
# SURFACE SAMPLING
# ============================================================

def sample_surface_points(
    mesh,
    count,
    seed=42
):

    if trimesh is None:

        raise RuntimeError(
            "trimesh is required."
        )


    # Make sampling reproducible.

    state = np.random.get_state()

    np.random.seed(
        seed
    )


    try:

        points, _ = trimesh.sample.sample_surface(
            mesh,
            count
        )

    finally:

        np.random.set_state(
            state
        )


    return np.asarray(
        points,
        dtype=np.float64
    )


# ============================================================
# CHAMFER DISTANCE
# ============================================================

def symmetric_chamfer_distance(
    points_a,
    points_b
):

    if cKDTree is None:

        raise RuntimeError(
            "scipy is not installed.\n"
            "Install with:\n"
            "pip install scipy"
        )


    if len(
        points_a
    ) == 0:

        raise RuntimeError(
            "Surface point cloud A is empty."
        )


    if len(
        points_b
    ) == 0:

        raise RuntimeError(
            "Surface point cloud B is empty."
        )


    tree_a = cKDTree(
        points_a
    )


    tree_b = cKDTree(
        points_b
    )


    dist_a_to_b, _ = tree_b.query(
        points_a,
        k=1
    )


    dist_b_to_a, _ = tree_a.query(
        points_b,
        k=1
    )


    mean_a_to_b = float(
        np.mean(
            dist_a_to_b
        )
    )


    mean_b_to_a = float(
        np.mean(
            dist_b_to_a
        )
    )


    chamfer = (
        mean_a_to_b
        +
        mean_b_to_a
    ) / 2.0


    rms = math.sqrt(

        (
            float(
                np.mean(
                    dist_a_to_b ** 2
                )
            )
            +
            float(
                np.mean(
                    dist_b_to_a ** 2
                )
            )
        )
        /
        2.0
    )


    return {

        "mean_a_to_b_mm":
            mean_a_to_b,

        "mean_b_to_a_mm":
            mean_b_to_a,

        "symmetric_mean_mm":
            float(
                chamfer
            ),

        "symmetric_rms_mm":
            float(
                rms
            ),

        "max_a_to_b_mm":
            float(
                np.max(
                    dist_a_to_b
                )
            ),

        "max_b_to_a_mm":
            float(
                np.max(
                    dist_b_to_a
                )
            )
    }


# ============================================================
# CHAMFER SIMILARITY
# ============================================================

def chamfer_similarity(
    chamfer_distance_mm,
    reference_diagonal_mm
):

    """
    Normalized similarity in [0, 1].

    1.0 = identical surface.

    This is OUR common benchmark similarity definition.
    It must not be confused with any Autodesk/neuralCAD-Edit
    metric that happens to use the same name but another
    formula.
    """

    if reference_diagonal_mm <= EPS:

        return None


    normalized_distance = (
        chamfer_distance_mm
        /
        reference_diagonal_mm
    )


    similarity = math.exp(
        -
        normalized_distance
    )


    return float(
        similarity
    )


# ============================================================
# BUILD DIFFERENCE SETS
# ============================================================

def build_difference_sets(
    start_set,
    result_set,
    gt_set
):

    predicted_added = (
        result_set
        -
        start_set
    )


    reference_added = (
        gt_set
        -
        start_set
    )


    predicted_removed = (
        start_set
        -
        result_set
    )


    reference_removed = (
        start_set
        -
        gt_set
    )


    predicted_difference = (
        predicted_added
        |
        predicted_removed
    )


    reference_difference = (
        reference_added
        |
        reference_removed
    )


    return {

        "predicted_added":
            predicted_added,

        "reference_added":
            reference_added,

        "predicted_removed":
            predicted_removed,

        "reference_removed":
            reference_removed,

        "predicted_difference":
            predicted_difference,

        "reference_difference":
            reference_difference
    }


# ============================================================
# CORE BENCHMARK
# ============================================================

def benchmark_geometry(
    start_step,
    result_step,
    gt_step,
    voxel_divisor=DEFAULT_VOXEL_DIVISOR,
    surface_samples=DEFAULT_SURFACE_SAMPLES
):

    benchmark_start = time.perf_counter()


    header(
        "COMMON GEOMETRY BENCHMARK"
    )


    # ========================================================
    # CHECK INPUT
    # ========================================================

    for label, path in [

        (
            "START",
            start_step
        ),

        (
            "RESULT",
            result_step
        ),

        (
            "GROUND TRUTH",
            gt_step
        )
    ]:

        print(
            f"{label}:"
        )

        print(
            path
        )

        print(
            "Exists:",
            os.path.exists(
                path
            )
        )

        print()


        if not os.path.exists(
            path
        ):

            raise FileNotFoundError(
                path
            )


    # ========================================================
    # LOAD CAD
    # ========================================================

    header(
        "LOAD STEP GEOMETRY"
    )


    start_shape = load_step(
        start_step
    )


    result_shape = load_step(
        result_step
    )


    gt_shape = load_step(
        gt_step
    )


    start_stats = geometry_stats(
        start_shape
    )


    result_stats = geometry_stats(
        result_shape
    )


    gt_stats = geometry_stats(
        gt_shape
    )


    print(
        "START valid:",
        start_stats[
            "valid"
        ]
    )

    print(
        "RESULT valid:",
        result_stats[
            "valid"
        ]
    )

    print(
        "GT valid:",
        gt_stats[
            "valid"
        ]
    )


    # ========================================================
    # TESSELLATION
    # ========================================================

    header(
        "TESSELLATION"
    )


    start_mesh = shape_to_trimesh(
        start_shape
    )


    result_mesh = shape_to_trimesh(
        result_shape
    )


    gt_mesh = shape_to_trimesh(
        gt_shape
    )


    print(
        "START triangles:",
        len(
            start_mesh.faces
        )
    )


    print(
        "RESULT triangles:",
        len(
            result_mesh.faces
        )
    )


    print(
        "GT triangles:",
        len(
            gt_mesh.faces
        )
    )


    # ========================================================
    # VOXEL SIZE
    # ========================================================

    pitch = determine_voxel_pitch(

        start_stats,
        result_stats,
        gt_stats,

        voxel_divisor
    )


    print(
        "\nVoxel divisor:",
        voxel_divisor
    )


    print(
        "Voxel pitch:",
        pitch,
        "mm"
    )


    # ========================================================
    # VOXELIZE
    # ========================================================

    header(
        "VOXELIZATION"
    )


    start_points = voxelize_mesh(
        start_mesh,
        pitch
    )


    result_points = voxelize_mesh(
        result_mesh,
        pitch
    )


    gt_points = voxelize_mesh(
        gt_mesh,
        pitch
    )


    # Common coordinate system.

    all_min = np.min(

        np.vstack(
            [
                start_points,
                result_points,
                gt_points
            ]
        ),

        axis=0
    )


    origin = (
        all_min
        -
        pitch
        *
        2.0
    )


    start_set = points_to_voxel_set(
        start_points,
        origin,
        pitch
    )


    result_set = points_to_voxel_set(
        result_points,
        origin,
        pitch
    )


    gt_set = points_to_voxel_set(
        gt_points,
        origin,
        pitch
    )


    print(
        "START occupied voxels:",
        len(
            start_set
        )
    )


    print(
        "RESULT occupied voxels:",
        len(
            result_set
        )
    )


    print(
        "GT occupied voxels:",
        len(
            gt_set
        )
    )


    # ========================================================
    # VOLUMETRIC METRICS
    # ========================================================

    header(
        "VOLUMETRIC METRICS"
    )


    volumetric = precision_recall_f1(
        result_set,
        gt_set
    )


    iou = voxel_iou(
        result_set,
        gt_set
    )


    print(
        "Precision:",
        volumetric[
            "precision"
        ]
    )


    print(
        "Recall:",
        volumetric[
            "recall"
        ]
    )


    print(
        "F1:",
        volumetric[
            "f1"
        ]
    )


    print(
        "Voxel IoU:",
        iou
    )


    # ========================================================
    # DIFFERENCE METRICS
    # ========================================================

    differences = build_difference_sets(
        start_set,
        result_set,
        gt_set
    )


    header(
        "DIFFERENCE METRICS"
    )


    difference_metrics = precision_recall_f1(

        differences[
            "predicted_difference"
        ],

        differences[
            "reference_difference"
        ]
    )


    added_metrics = precision_recall_f1(

        differences[
            "predicted_added"
        ],

        differences[
            "reference_added"
        ]
    )


    removed_metrics = precision_recall_f1(

        differences[
            "predicted_removed"
        ],

        differences[
            "reference_removed"
        ]
    )


    print(
        "Difference F1:",
        difference_metrics[
            "f1"
        ]
    )


    print(
        "Added F1:",
        added_metrics[
            "f1"
        ]
    )


    print(
        "Removed F1:",
        removed_metrics[
            "f1"
        ]
    )


    # ========================================================
    # SURFACE CHAMFER
    # ========================================================

    header(
        "SURFACE CHAMFER"
    )


    print(
        "Surface samples:",
        surface_samples
    )


    result_surface = sample_surface_points(
        result_mesh,
        surface_samples,
        seed=42
    )


    gt_surface = sample_surface_points(
        gt_mesh,
        surface_samples,
        seed=43
    )


    chamfer = symmetric_chamfer_distance(
        result_surface,
        gt_surface
    )


    reference_diagonal = max(

        result_stats[
            "bounding_box_mm"
        ][
            "diagonal"
        ],

        gt_stats[
            "bounding_box_mm"
        ][
            "diagonal"
        ]
    )


    similarity = chamfer_similarity(

        chamfer[
            "symmetric_mean_mm"
        ],

        reference_diagonal
    )


    print(
        "Symmetric Chamfer:",
        chamfer[
            "symmetric_mean_mm"
        ],
        "mm"
    )


    print(
        "RMS Chamfer:",
        chamfer[
            "symmetric_rms_mm"
        ],
        "mm"
    )


    print(
        "Chamfer similarity:",
        similarity
    )


    # ========================================================
    # REPORT
    # ========================================================

    runtime = (
        time.perf_counter()
        -
        benchmark_start
    )


    report = {

        "status":
            "SUCCESS",

        "voxel": {

            "divisor":
                int(
                    voxel_divisor
                ),

            "pitch_mm":
                float(
                    pitch
                ),

            "start_occupied":
                len(
                    start_set
                ),

            "result_occupied":
                len(
                    result_set
                ),

            "gt_occupied":
                len(
                    gt_set
                )
        },

        "volumetric": {

            "precision":
                volumetric[
                    "precision"
                ],

            "recall":
                volumetric[
                    "recall"
                ],

            "f1":
                volumetric[
                    "f1"
                ],

            "voxel_iou":
                iou
        },

        "difference": {

            "precision":
                difference_metrics[
                    "precision"
                ],

            "recall":
                difference_metrics[
                    "recall"
                ],

            "f1":
                difference_metrics[
                    "f1"
                ]
        },

        "added": {

            "precision":
                added_metrics[
                    "precision"
                ],

            "recall":
                added_metrics[
                    "recall"
                ],

            "f1":
                added_metrics[
                    "f1"
                ]
        },

        "removed": {

            "precision":
                removed_metrics[
                    "precision"
                ],

            "recall":
                removed_metrics[
                    "recall"
                ],

            "f1":
                removed_metrics[
                    "f1"
                ]
        },

        "surface": {

            "samples":
                int(
                    surface_samples
                ),

            "chamfer_distance_mm":
                chamfer[
                    "symmetric_mean_mm"
                ],

            "chamfer_rms_mm":
                chamfer[
                    "symmetric_rms_mm"
                ],

            "chamfer_a_to_b_mm":
                chamfer[
                    "mean_a_to_b_mm"
                ],

            "chamfer_b_to_a_mm":
                chamfer[
                    "mean_b_to_a_mm"
                ],

            "chamfer_similarity":
                similarity
        },

        "geometry": {

            "start":
                start_stats,

            "result":
                result_stats,

            "ground_truth":
                gt_stats
        },

        "runtime_s":
            runtime
    }


    return report


# ============================================================
# METHOD-SPECIFIC RESULT RESOLUTION
# ============================================================

def find_autodesk_result_step(
    experiment_dir
):

    report_path = os.path.join(
        experiment_dir,
        "autodesk_output",
        "autodesk_report.json"
    )


    report = load_json(
        report_path
    )


    if not report:

        return None


    step_files = report.get(
        "step_files",
        []
    )


    for path in step_files:

        if os.path.basename(
            path
        ).lower() == "tmp.step":

            if os.path.exists(
                path
            ):

                return path


    for path in step_files:

        if os.path.exists(
            path
        ):

            return path


    return None


def find_geometric_mapping_result_step(
    experiment_dir,
    experiment_id
):

    path = os.path.join(
        experiment_dir,
        "our_method_output",
        f"{experiment_id}_result.step"
    )


    if os.path.exists(
        path
    ):

        return path


    return None


# ============================================================
# PUBLIC PIPELINE ENTRY
# ============================================================

def run_geometry_benchmark(
    config,
    project_root,
    method=None
):

    header(
        "MODULE — COMMON GEOMETRY BENCHMARK"
    )


    experiment_id = str(
        config.get(
            "experiment_id",
            ""
        )
    ).strip()


    if not experiment_id:

        raise ValueError(
            "experiment_id missing."
        )


    if method is None:

        method = str(
            config.get(
                "method",
                ""
            )
        ).strip().upper()


    experiment_dir = os.path.join(
        project_root,
        "experiments",
        experiment_id
    )


    start_step = os.path.join(
        experiment_dir,
        "input",
        f"{experiment_id}_start.step"
    )


    gt_dir = os.path.join(
        experiment_dir,
        "ground_truth"
    )


    gt_report_path = os.path.join(
        gt_dir,
        "ground_truth_report.json"
    )


    gt_step = os.path.join(
        gt_dir,
        f"{experiment_id}_gt.step"
    )


    # ========================================================
    # RESULT STEP
    # ========================================================

    if method == "AUTODESK":

        result_step = find_autodesk_result_step(
            experiment_dir
        )


    elif method == "GEOMETRIC_MAPPING":

        result_step = find_geometric_mapping_result_step(
            experiment_dir,
            experiment_id
        )


    else:

        raise ValueError(
            f"Unsupported method: {method}"
        )


    # ========================================================
    # OUTPUT
    # ========================================================

    benchmark_dir = os.path.join(
        experiment_dir,
        "geometry_benchmark"
    )


    os.makedirs(
        benchmark_dir,
        exist_ok=True
    )


    report_path = os.path.join(
        benchmark_dir,
        f"{method.lower()}_geometry_benchmark.json"
    )


    # ========================================================
    # GT STATUS
    # ========================================================

    gt_report = load_json(
        gt_report_path
    )


    gt_status = None


    if gt_report:

        gt_status = gt_report.get(
            "status"
        )


    print(
        "Experiment:",
        experiment_id
    )


    print(
        "Method:",
        method
    )


    print(
        "START:"
    )

    print(
        start_step
    )


    print(
        "\nRESULT:"
    )

    print(
        result_step
    )


    print(
        "\nGT status:",
        gt_status
    )


    print(
        "GT STEP:"
    )

    print(
        gt_step
    )


    # ========================================================
    # NO RESULT
    # ========================================================

    if (
        result_step is None
        or
        not os.path.exists(
            result_step
        )
    ):

        report = {

            "experiment_id":
                experiment_id,

            "method":
                method,

            "status":
                "NO_RESULT_STEP",

            "result_step":
                result_step
        }


        save_json(
            report,
            report_path
        )


        return report


    # ========================================================
    # NO CONFIRMED GT
    # ========================================================

    if (
        gt_status != "CONFIRMED"
        or
        not os.path.exists(
            gt_step
        )
    ):

        report = {

            "experiment_id":
                experiment_id,

            "method":
                method,

            "status":
                "NOT_AVAILABLE",

            "reason":
                (
                    "Ground Truth is not confirmed. "
                    "Benchmark metrics were not calculated."
                ),

            "start_step":
                start_step,

            "result_step":
                result_step,

            "ground_truth_status":
                gt_status,

            "ground_truth_step":
                None,

            "metrics": {

                "volumetric_precision":
                    None,

                "volumetric_recall":
                    None,

                "volumetric_f1":
                    None,

                "voxel_iou":
                    None,

                "difference_precision":
                    None,

                "difference_recall":
                    None,

                "difference_f1":
                    None,

                "added_f1":
                    None,

                "removed_f1":
                    None,

                "chamfer_distance_mm":
                    None,

                "chamfer_similarity":
                    None
            }
        }


        save_json(
            report,
            report_path
        )


        header(
            "GEOMETRY BENCHMARK RESULT"
        )


        print(
            "Status: NOT_AVAILABLE"
        )


        print(
            "Reason: GT is not confirmed."
        )


        print(
            "\nReport:"
        )

        print(
            report_path
        )


        return report


    # ========================================================
    # PARAMETERS FROM main.json
    # ========================================================

    benchmark_cfg = config.get(
        "geometry_benchmark",
        {}
    )


    voxel_divisor = int(
        benchmark_cfg.get(
            "voxel_divisor",
            DEFAULT_VOXEL_DIVISOR
        )
    )


    surface_samples = int(
        benchmark_cfg.get(
            "surface_samples",
            DEFAULT_SURFACE_SAMPLES
        )
    )


    # ========================================================
    # EXECUTE
    # ========================================================

    metrics = benchmark_geometry(

        start_step=
            start_step,

        result_step=
            result_step,

        gt_step=
            gt_step,

        voxel_divisor=
            voxel_divisor,

        surface_samples=
            surface_samples
    )


    report = {

        "experiment_id":
            experiment_id,

        "method":
            method,

        "status":
            "SUCCESS",

        "start_step":
            start_step,

        "result_step":
            result_step,

        "ground_truth_step":
            gt_step,

        "benchmark":
            metrics
    }


    save_json(
        report,
        report_path
    )


    # ========================================================
    # FINAL
    # ========================================================

    header(
        "GEOMETRY BENCHMARK RESULT"
    )


    print(
        "Experiment:",
        experiment_id
    )


    print(
        "Method:",
        method
    )


    print(
        "\nVoxel IoU:",
        metrics[
            "volumetric"
        ][
            "voxel_iou"
        ]
    )


    print(
        "Volumetric F1:",
        metrics[
            "volumetric"
        ][
            "f1"
        ]
    )


    print(
        "Difference F1:",
        metrics[
            "difference"
        ][
            "f1"
        ]
    )


    print(
        "Added F1:",
        metrics[
            "added"
        ][
            "f1"
        ]
    )


    print(
        "Removed F1:",
        metrics[
            "removed"
        ][
            "f1"
        ]
    )


    print(
        "Chamfer distance:",
        metrics[
            "surface"
        ][
            "chamfer_distance_mm"
        ],
        "mm"
    )


    print(
        "Chamfer similarity:",
        metrics[
            "surface"
        ][
            "chamfer_similarity"
        ]
    )


    print(
        "\nReport:"
    )

    print(
        report_path
    )


    return report


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    print(
        "pipeline/geometry_benchmark.py"
    )

    print(
        "Use run_geometry_benchmark() through 1_MAIN.py."
    )