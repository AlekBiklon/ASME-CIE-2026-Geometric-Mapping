# ============================================================
# FILE: pipeline/metrics.py
# ASME CIE 2026 STUDENT HACKATHON
#
# MODULE 4 — EXPERIMENT METRICS
#
# PURPOSE:
#     Collect quantitative metrics for GEOMETRIC_MAPPING.
#
# INPUT:
#
# experiments/Bxx/
#   input/
#       Bxx_start.step
#
#   our_method_output/
#       Bxx_result.step
#       Bxx_edit_report.json
#       cad_edit_report.json
#
#   ground_truth/
#       ground_truth_report.json
#       Bxx_gt.step          [only if GT confirmed]
#
# OUTPUT:
#
# experiments/Bxx/metrics/
#       metrics_report.json
#
# IMPORTANT:
#
# If GT is NOT_CONFIRMED:
#
#     Chamfer Distance = N/A
#     Voxel IoU        = N/A
#     Difference F1    = N/A
#
# We never invent GT-dependent metrics.
# ============================================================


import os
import json
import math
import time

import cadquery as cq


# ============================================================
# CONSOLE
# ============================================================

def header(title):

    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):

    if not os.path.exists(path):
        return None

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def save_json(data, path):

    folder = os.path.dirname(path)

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
# STEP HELPERS
# ============================================================

def load_step(path):

    if not os.path.exists(path):

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


def geometry_stats(shape):

    solids = shape.Solids()
    faces = shape.Faces()
    edges = shape.Edges()

    volume = sum(
        float(
            solid.Volume()
        )
        for solid in solids
    )

    bbox = shape.BoundingBox()

    bbox_x = float(
        bbox.xlen
    )

    bbox_y = float(
        bbox.ylen
    )

    bbox_z = float(
        bbox.zlen
    )

    bbox_diagonal = math.sqrt(
        bbox_x ** 2
        +
        bbox_y ** 2
        +
        bbox_z ** 2
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
                faces
            ),

        "edges":
            len(
                edges
            ),

        "volume_mm3":
            float(
                volume
            ),

        "bounding_box_mm": {

            "x":
                bbox_x,

            "y":
                bbox_y,

            "z":
                bbox_z,

            "diagonal":
                bbox_diagonal
        }
    }


# ============================================================
# SAFE HELPERS
# ============================================================

def safe_float(value):

    try:

        if value is None:
            return None

        return float(
            value
        )

    except Exception:

        return None


def safe_bool(value):

    if value is None:
        return None

    return bool(
        value
    )


# ============================================================
# RECURSIVE SEARCH
# ============================================================

def recursive_find(
    data,
    key
):

    if isinstance(
        data,
        dict
    ):

        if key in data:

            return data[
                key
            ]

        for value in data.values():

            result = recursive_find(
                value,
                key
            )

            if result is not None:

                return result


    elif isinstance(
        data,
        list
    ):

        for value in data:

            result = recursive_find(
                value,
                key
            )

            if result is not None:

                return result


    return None


# ============================================================
# CHAMFER METRICS
# ============================================================

def collect_chamfer_details(
    engine_report
):

    result = {

        "requested_distance_mm":
            None,

        "contours_total":
            0,

        "full_success_contours":
            0,

        "adaptive_success_contours":
            0,

        "partial_success_contours":
            0,

        "failed_contours":
            0,

        "skipped_edges":
            [],

        "contours":
            [],

        "minimum_applied_distance_mm":
            None,

        "maximum_applied_distance_mm":
            None,

        "mean_applied_distance_mm":
            None,

        "minimum_distance_retention":
            None,

        "mean_distance_retention":
            None
    }


    if not engine_report:

        return result


    operation_report = engine_report.get(
        "operation_report",
        {}
    )


    requested = safe_float(
        operation_report.get(
            "requested_distance_mm"
        )
    )


    result[
        "requested_distance_mm"
    ] = requested


    owner_results = operation_report.get(
        "owner_results",
        []
    )


    for owner in owner_results:

        solid_index = owner.get(
            "solid_index"
        )

        contours = owner.get(
            "contours",
            []
        )


        for contour_index, contour in enumerate(
            contours,
            start=1
        ):

            status = contour.get(
                "status"
            )

            applied = safe_float(
                contour.get(
                    "applied_distance_mm"
                )
            )

            edge_ids = contour.get(
                "edge_ids",
                []
            )

            skipped = contour.get(
                "skipped_edges",
                []
            )


            contour_result = {

                "solid_index":
                    solid_index,

                "contour_index":
                    contour_index,

                "edge_ids":
                    edge_ids,

                "edge_count":
                    len(
                        edge_ids
                    ),

                "requested_distance_mm":
                    safe_float(
                        contour.get(
                            "requested_distance_mm",
                            requested
                        )
                    ),

                "applied_distance_mm":
                    applied,

                "status":
                    status,

                "skipped_edges":
                    skipped,

                "volume_change_mm3":
                    safe_float(
                        contour.get(
                            "volume_change"
                        )
                    )
            }


            result[
                "contours"
            ].append(
                contour_result
            )


            result[
                "contours_total"
            ] += 1


            if status == "FULL_SUCCESS":

                result[
                    "full_success_contours"
                ] += 1


            elif status == "ADAPTIVE_SUCCESS":

                result[
                    "adaptive_success_contours"
                ] += 1


            elif status == "PARTIAL_SUCCESS":

                result[
                    "partial_success_contours"
                ] += 1


            elif status == "FAILED":

                result[
                    "failed_contours"
                ] += 1


            for edge_id in skipped:

                if edge_id not in result[
                    "skipped_edges"
                ]:

                    result[
                        "skipped_edges"
                    ].append(
                        edge_id
                    )


    # ========================================================
    # DISTANCE STATISTICS
    # ========================================================

    applied_distances = [

        contour[
            "applied_distance_mm"
        ]

        for contour in result[
            "contours"
        ]

        if contour[
            "applied_distance_mm"
        ] is not None
    ]


    if applied_distances:

        result[
            "minimum_applied_distance_mm"
        ] = min(
            applied_distances
        )

        result[
            "maximum_applied_distance_mm"
        ] = max(
            applied_distances
        )

        result[
            "mean_applied_distance_mm"
        ] = (
            sum(
                applied_distances
            )
            /
            len(
                applied_distances
            )
        )


    if (
        requested is not None
        and
        requested > 0
        and
        applied_distances
    ):

        result[
            "minimum_distance_retention"
        ] = (
            min(
                applied_distances
            )
            /
            requested
        )

        result[
            "mean_distance_retention"
        ] = (
            (
                sum(
                    applied_distances
                )
                /
                len(
                    applied_distances
                )
            )
            /
            requested
        )


    return result


# ============================================================
# OPERATION-SPECIFIC METRICS
# ============================================================

def collect_operation_details(
    engine_report
):

    if not engine_report:

        return {

            "operation":
                None,

            "operation_status":
                None
        }


    operation = engine_report.get(
        "operation"
    )


    operation_status = engine_report.get(
        "operation_status"
    )


    result = {

        "operation":
            operation,

        "operation_status":
            operation_status
    }


    if operation == "CHAMFER":

        result[
            "chamfer"
        ] = collect_chamfer_details(
            engine_report
        )


    elif operation == "FILLET":

        operation_report = engine_report.get(
            "operation_report",
            {}
        )

        result[
            "fillet"
        ] = {

            "radius_mm":
                safe_float(
                    operation_report.get(
                        "radius_mm"
                    )
                ),

            "edge_ids":
                operation_report.get(
                    "edge_ids",
                    []
                )
        }


    elif operation == "ADD_HOLE":

        operation_report = engine_report.get(
            "operation_report",
            {}
        )

        result[
            "add_hole"
        ] = {

            "diameter_mm":
                safe_float(
                    operation_report.get(
                        "diameter_mm"
                    )
                ),

            "target_face":
                operation_report.get(
                    "target_face"
                ),

            "removed_volume_mm3":
                safe_float(
                    operation_report.get(
                        "removed_volume"
                    )
                )
        }


    return result


# ============================================================
# MAIN MODULE
# ============================================================

def run_metrics(
    config,
    project_root
):

    module_start = time.perf_counter()


    header(
        "MODULE 4 — METRICS"
    )


    # ========================================================
    # CONFIG
    # ========================================================

    experiment_id = str(
        config.get(
            "experiment_id",
            ""
        )
    ).strip()


    request_id = str(
        config.get(
            "request_id",
            ""
        )
    ).strip()


    method = str(
        config.get(
            "method",
            "GEOMETRIC_MAPPING"
        )
    ).strip()


    if not experiment_id:

        raise ValueError(
            "experiment_id missing."
        )


    # ========================================================
    # PATHS
    # ========================================================

    experiment_dir = os.path.join(
        project_root,
        "experiments",
        experiment_id
    )


    input_dir = os.path.join(
        experiment_dir,
        "input"
    )


    output_dir = os.path.join(
        experiment_dir,
        "our_method_output"
    )


    gt_dir = os.path.join(
        experiment_dir,
        "ground_truth"
    )


    metrics_dir = os.path.join(
        experiment_dir,
        "metrics"
    )


    os.makedirs(
        metrics_dir,
        exist_ok=True
    )


    start_step = os.path.join(
        input_dir,
        f"{experiment_id}_start.step"
    )


    result_step = os.path.join(
        output_dir,
        f"{experiment_id}_result.step"
    )


    engine_report_path = os.path.join(
        output_dir,
        f"{experiment_id}_edit_report.json"
    )


    module_report_path = os.path.join(
        output_dir,
        "cad_edit_report.json"
    )


    gt_report_path = os.path.join(
        gt_dir,
        "ground_truth_report.json"
    )


    gt_step = os.path.join(
        gt_dir,
        f"{experiment_id}_gt.step"
    )


    metrics_report_path = os.path.join(
        metrics_dir,
        "metrics_report.json"
    )


    # ========================================================
    # INPUT REPORT
    # ========================================================

    print(
        "Experiment:"
    )

    print(
        experiment_id
    )


    print(
        "\nRequest ID:"
    )

    print(
        request_id
    )


    print(
        "\nMethod:"
    )

    print(
        method
    )


    print(
        "\nSTART STEP:"
    )

    print(
        start_step
    )


    print(
        "Exists:",
        os.path.exists(
            start_step
        )
    )


    print(
        "\nRESULT STEP:"
    )

    print(
        result_step
    )


    print(
        "Exists:",
        os.path.exists(
            result_step
        )
    )


    if not os.path.exists(
        start_step
    ):

        raise FileNotFoundError(
            start_step
        )


    if not os.path.exists(
        result_step
    ):

        raise FileNotFoundError(
            result_step
        )


    # ========================================================
    # LOAD JSON REPORTS
    # ========================================================

    engine_report = load_json(
        engine_report_path
    )


    module_report = load_json(
        module_report_path
    )


    gt_report = load_json(
        gt_report_path
    )


    # ========================================================
    # GEOMETRY METRICS
    # ========================================================

    header(
        "GEOMETRY METRICS"
    )


    start_shape = load_step(
        start_step
    )


    result_shape = load_step(
        result_step
    )


    start_stats = geometry_stats(
        start_shape
    )


    result_stats = geometry_stats(
        result_shape
    )


    volume_delta = (
        result_stats[
            "volume_mm3"
        ]
        -
        start_stats[
            "volume_mm3"
        ]
    )


    absolute_volume_change = abs(
        volume_delta
    )


    if abs(
        start_stats[
            "volume_mm3"
        ]
    ) > 1e-12:

        relative_volume_change = (
            absolute_volume_change
            /
            abs(
                start_stats[
                    "volume_mm3"
                ]
            )
        )

    else:

        relative_volume_change = None


    solids_delta = (
        result_stats[
            "solids"
        ]
        -
        start_stats[
            "solids"
        ]
    )


    faces_delta = (
        result_stats[
            "faces"
        ]
        -
        start_stats[
            "faces"
        ]
    )


    edges_delta = (
        result_stats[
            "edges"
        ]
        -
        start_stats[
            "edges"
        ]
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
        "Solids:",
        start_stats[
            "solids"
        ],
        "->",
        result_stats[
            "solids"
        ]
    )


    print(
        "Faces:",
        start_stats[
            "faces"
        ],
        "->",
        result_stats[
            "faces"
        ]
    )


    print(
        "Edges:",
        start_stats[
            "edges"
        ],
        "->",
        result_stats[
            "edges"
        ]
    )


    print(
        "Volume change:",
        volume_delta,
        "mm^3"
    )


    print(
        "Relative volume change:",
        relative_volume_change
    )


    # ========================================================
    # CAD EDIT METRICS
    # ========================================================

    header(
        "CAD EDIT METRICS"
    )


    operation_details = (
        collect_operation_details(
            engine_report
        )
    )


    operation = operation_details.get(
        "operation"
    )


    operation_status = operation_details.get(
        "operation_status"
    )


    step_success = None
    result_valid_report = None
    reimport_valid = None
    reimport_volume_delta = None


    if engine_report:

        step_success = safe_bool(
            engine_report.get(
                "step_success"
            )
        )


        result_valid_report = safe_bool(
            engine_report.get(
                "result_valid"
            )
        )


        reimport_valid = safe_bool(
            engine_report.get(
                "reimport_valid"
            )
        )


        reimport_volume_delta = safe_float(
            engine_report.get(
                "reimport_volume_delta"
            )
        )


    # ========================================================
    # CAD EDIT RUNTIME
    # ========================================================

    cad_edit_runtime_s = None


    if module_report:

        # Current cad_edit.py key
        cad_edit_runtime_s = recursive_find(
            module_report,
            "runtime_seconds"
        )


        # Compatibility with older versions
        if cad_edit_runtime_s is None:

            cad_edit_runtime_s = recursive_find(
                module_report,
                "runtime_s"
            )


        if cad_edit_runtime_s is None:

            cad_edit_runtime_s = recursive_find(
                module_report,
                "runtime"
            )


        cad_edit_runtime_s = safe_float(
            cad_edit_runtime_s
        )


    print(
        "Operation:",
        operation
    )


    print(
        "Operation status:",
        operation_status
    )


    print(
        "STEP success:",
        step_success
    )


    print(
        "Re-import valid:",
        reimport_valid
    )


    print(
        "CAD edit runtime:",
        cad_edit_runtime_s,
        "s"
    )


    # ========================================================
    # GROUND TRUTH STATUS
    # ========================================================

    header(
        "GROUND TRUTH STATUS"
    )


    if gt_report:

        gt_status = gt_report.get(
            "status",
            "UNKNOWN"
        )


        gt_reason = gt_report.get(
            "reason"
        )


    else:

        gt_status = (
            "NOT_EVALUATED"
        )


        gt_reason = (
            "ground_truth_report.json "
            "was not found."
        )


    print(
        "GT status:",
        gt_status
    )


    print(
        "GT STEP exists:",
        os.path.exists(
            gt_step
        )
    )


    if gt_reason:

        print(
            "Reason:"
        )

        print(
            gt_reason
        )


    # ========================================================
    # GT METRICS
    # ========================================================

    gt_metrics = {

        "available":
            False,

        "chamfer_distance":
            None,

        "voxel_iou":
            None,

        "difference_f1":
            None,

        "note":
            None
    }


    gt_geometry = None


    if (
        gt_status
        ==
        "CONFIRMED"
        and
        os.path.exists(
            gt_step
        )
    ):

        gt_shape = load_step(
            gt_step
        )


        gt_geometry = geometry_stats(
            gt_shape
        )


        gt_metrics[
            "available"
        ] = True


        gt_metrics[
            "note"
        ] = (
            "Ground Truth is confirmed. "
            "GT geometry exists. "
            "Chamfer Distance / Voxel IoU / "
            "Difference F1 require separate "
            "benchmark implementations."
        )


    else:

        gt_metrics[
            "available"
        ] = False


        gt_metrics[
            "note"
        ] = (
            "Ground Truth is not confirmed; "
            "GT-dependent metrics are N/A."
        )


    print(
        "\nChamfer Distance:",
        gt_metrics[
            "chamfer_distance"
        ]
    )


    print(
        "Voxel IoU:",
        gt_metrics[
            "voxel_iou"
        ]
    )


    print(
        "Difference F1:",
        gt_metrics[
            "difference_f1"
        ]
    )


    # ========================================================
    # CHAMFER PERFORMANCE
    # ========================================================

    if operation == "CHAMFER":

        header(
            "CHAMFER PERFORMANCE"
        )


        chamfer = operation_details.get(
            "chamfer",
            {}
        )


        print(
            "Requested distance:",
            chamfer.get(
                "requested_distance_mm"
            ),
            "mm"
        )


        print(
            "Contours:",
            chamfer.get(
                "contours_total"
            )
        )


        for contour in chamfer.get(
            "contours",
            []
        ):

            print(
                "\nContour",
                contour[
                    "contour_index"
                ]
            )


            print(
                "Edges:",
                contour[
                    "edge_ids"
                ]
            )


            print(
                "Requested:",
                contour[
                    "requested_distance_mm"
                ],
                "mm"
            )


            print(
                "Applied:",
                contour[
                    "applied_distance_mm"
                ],
                "mm"
            )


            print(
                "Status:",
                contour[
                    "status"
                ]
            )


        print(
            "\nMinimum applied distance:",
            chamfer.get(
                "minimum_applied_distance_mm"
            )
        )


        print(
            "Maximum applied distance:",
            chamfer.get(
                "maximum_applied_distance_mm"
            )
        )


        print(
            "Mean applied distance:",
            chamfer.get(
                "mean_applied_distance_mm"
            )
        )


        print(
            "Minimum distance retention:",
            chamfer.get(
                "minimum_distance_retention"
            )
        )


        print(
            "Mean distance retention:",
            chamfer.get(
                "mean_distance_retention"
            )
        )


        print(
            "Skipped edges:",
            chamfer.get(
                "skipped_edges"
            )
        )


    # ========================================================
    # SUCCESS STATUS
    # ========================================================

    valid_brep_success = bool(
        result_stats[
            "valid"
        ]
        and
        result_stats[
            "solids"
        ]
        > 0
    )


    solid_count_preserved = (
        solids_delta == 0
    )


    export_reimport_success = bool(
        step_success
        and
        reimport_valid
    )


    operation_success = (
        operation_status
        in [
            "FULL_SUCCESS",
            "ADAPTIVE_SUCCESS",
            "PARTIAL_SUCCESS"
        ]
    )


    strict_operation_success = (
        operation_status
        in [
            "FULL_SUCCESS",
            "ADAPTIVE_SUCCESS"
        ]
    )


    # ========================================================
    # FINAL REPORT
    # ========================================================

    metrics_report = {

        "experiment_id":
            experiment_id,

        "request_id":
            request_id,

        "method":
            method,

        "operation":
            operation,

        "operation_status":
            operation_status,

        "cad_edit": {

            "runtime_s":
                cad_edit_runtime_s,

            "step_success":
                step_success,

            "result_valid_report":
                result_valid_report,

            "valid_brep":
                valid_brep_success,

            "reimport_valid":
                reimport_valid,

            "export_reimport_success":
                export_reimport_success,

            "reimport_volume_delta_mm3":
                reimport_volume_delta
        },

        "geometry": {

            "start":
                start_stats,

            "result":
                result_stats,

            "change": {

                "solids_delta":
                    solids_delta,

                "faces_delta":
                    faces_delta,

                "edges_delta":
                    edges_delta,

                "volume_delta_mm3":
                    volume_delta,

                "absolute_volume_change_mm3":
                    absolute_volume_change,

                "relative_volume_change":
                    relative_volume_change
            }
        },

        "operation_details":
            operation_details,

        "ground_truth": {

            "status":
                gt_status,

            "reason":
                gt_reason,

            "step":
                (
                    gt_step
                    if
                    os.path.exists(
                        gt_step
                    )
                    else
                    None
                ),

            "geometry":
                gt_geometry
        },

        "gt_metrics":
            gt_metrics,

        "success": {

            "operation_success":
                operation_success,

            "strict_operation_success":
                strict_operation_success,

            "valid_brep":
                valid_brep_success,

            "solid_count_preserved":
                solid_count_preserved,

            "export_reimport_success":
                export_reimport_success
        }
    }


    # ========================================================
    # METRICS MODULE RUNTIME
    # ========================================================

    module_runtime = (
        time.perf_counter()
        -
        module_start
    )


    metrics_report[
        "metrics_module_runtime_s"
    ] = module_runtime


    # ========================================================
    # SAVE REPORT
    # ========================================================

    save_json(
        metrics_report,
        metrics_report_path
    )


    # ========================================================
    # FINAL CONSOLE
    # ========================================================

    header(
        "MODULE 4 — RESULT"
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
        "Operation:",
        operation
    )


    print(
        "Operation status:",
        operation_status
    )


    print(
        "\nCAD edit runtime:",
        cad_edit_runtime_s,
        "s"
    )


    print(
        "Valid B-Rep:",
        valid_brep_success
    )


    print(
        "Export / re-import:",
        export_reimport_success
    )


    print(
        "Solid count preserved:",
        solid_count_preserved
    )


    print(
        "\nGT status:",
        gt_status
    )


    if gt_status != "CONFIRMED":

        print(
            "GT-dependent metrics: N/A"
        )


    print(
        "\nMetrics module runtime:",
        module_runtime,
        "s"
    )


    print(
        "\nReport:"
    )

    print(
        metrics_report_path
    )


    return metrics_report


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    print(
        "pipeline/metrics.py"
    )

    print(
        "This module should normally be "
        "launched through 1_MAIN.py."
    )