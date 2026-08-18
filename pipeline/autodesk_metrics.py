# ============================================================
# FILE: pipeline/autodesk_metrics.py
# ASME CIE 2026 STUDENT HACKATHON
#
# AUTODESK BASELINE — RESULT METRICS
#
# PURPOSE:
#
#     Evaluate the STEP produced by the real neuralCAD-Edit
#     Autodesk baseline.
#
# INPUT:
#
# experiments/Bxx/
#
#     autodesk_output/
#         autodesk_report.json
#         .../tmp.step
#
#     input/
#         Bxx_start.step
#
#     ground_truth/
#         ground_truth_report.json
#         Bxx_gt.step        [only if confirmed]
#
#
# OUTPUT:
#
# experiments/Bxx/autodesk_metrics/
#     autodesk_metrics_report.json
#
#
# IMPORTANT:
#
#     This module does NOT run neuralCAD-Edit.
#     It only evaluates the result already produced by it.
#
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
# JSON
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
# STEP
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
# FIND FINAL STEP
# ============================================================

def find_final_step(
    autodesk_report
):

    step_files = autodesk_report.get(
        "step_files",
        []
    )

    if not step_files:

        return None

    # Prefer tmp.step because this is what current
    # neuralCAD-Edit baseline produces as final STEP.

    for path in step_files:

        if os.path.basename(
            path
        ).lower() == "tmp.step":

            return path

    return step_files[
        0
    ]


# ============================================================
# ITERATION COUNTS
# ============================================================

def count_iteration_outputs(
    output_files
):

    responses = 0

    renders = 0


    for path in output_files:

        filename = os.path.basename(
            path
        ).lower()

        if filename.endswith(
            "_response.txt"
        ):

            responses += 1

        elif filename.endswith(
            "_output.png"
        ):

            renders += 1


    return (
        responses,
        renders
    )


# ============================================================
# OPTIONAL TOKEN EXTRACTION
# ============================================================

def extract_token_metrics(
    autodesk_report
):

    """
    Current autodesk_report does not necessarily contain
    token counts.

    If later autodesk.py stores them, this function will
    automatically read them.
    """

    input_tokens = None
    output_tokens = None
    total_tokens = None
    cost_estimate_usd = None


    possible_metrics = autodesk_report.get(
        "metrics",
        {}
    )


    if isinstance(
        possible_metrics,
        dict
    ):

        input_tokens = possible_metrics.get(
            "input_tokens"
        )

        output_tokens = possible_metrics.get(
            "output_tokens"
        )

        total_tokens = possible_metrics.get(
            "total_tokens"
        )

        cost_estimate_usd = possible_metrics.get(
            "cost_estimate_usd"
        )


    return {

        "input_tokens":
            input_tokens,

        "output_tokens":
            output_tokens,

        "total_tokens":
            total_tokens,

        "cost_estimate_usd":
            cost_estimate_usd
    }


# ============================================================
# MAIN
# ============================================================

def run_autodesk_metrics(
    config,
    project_root
):

    module_start = time.perf_counter()


    header(
        "AUTODESK — METRICS"
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


    start_step = os.path.join(
        experiment_dir,
        "input",
        f"{experiment_id}_start.step"
    )


    autodesk_output_dir = os.path.join(
        experiment_dir,
        "autodesk_output"
    )


    autodesk_report_path = os.path.join(
        autodesk_output_dir,
        "autodesk_report.json"
    )


    gt_report_path = os.path.join(
        experiment_dir,
        "ground_truth",
        "ground_truth_report.json"
    )


    gt_step = os.path.join(
        experiment_dir,
        "ground_truth",
        f"{experiment_id}_gt.step"
    )


    metrics_dir = os.path.join(
        experiment_dir,
        "autodesk_metrics"
    )


    metrics_report_path = os.path.join(
        metrics_dir,
        "autodesk_metrics_report.json"
    )


    os.makedirs(
        metrics_dir,
        exist_ok=True
    )


    # ========================================================
    # LOAD AUTODESK REPORT
    # ========================================================

    if not os.path.exists(
        autodesk_report_path
    ):

        raise FileNotFoundError(
            autodesk_report_path
        )


    autodesk_report = load_json(
        autodesk_report_path
    )


    final_step = find_final_step(
        autodesk_report
    )


    header(
        "AUTODESK RESULT INPUT"
    )


    print(
        "Experiment:",
        experiment_id
    )


    print(
        "Request:",
        request_id
    )


    print(
        "\nAutodesk report:"
    )

    print(
        autodesk_report_path
    )


    print(
        "\nFinal STEP:"
    )

    print(
        final_step
    )


    print(
        "Exists:",
        bool(
            final_step
            and
            os.path.exists(
                final_step
            )
        )
    )


    # ========================================================
    # AUTODESK RUNTIME
    # ========================================================

    runtime_sec = autodesk_report.get(
        "runtime_sec"
    )


    runtime_min = autodesk_report.get(
        "runtime_min"
    )


    step_success = bool(
        autodesk_report.get(
            "step_success"
        )
    )


    # ========================================================
    # ITERATIONS
    # ========================================================

    output_files = autodesk_report.get(
        "output_files",
        []
    )


    vlm_responses, visual_renders = (
        count_iteration_outputs(
            output_files
        )
    )


    # ========================================================
    # TOKENS / COST
    # ========================================================

    token_metrics = extract_token_metrics(
        autodesk_report
    )


    # ========================================================
    # RESULT GEOMETRY
    # ========================================================

    result_geometry = None


    if (
        final_step
        and
        os.path.exists(
            final_step
        )
    ):

        result_shape = load_step(
            final_step
        )


        result_geometry = geometry_stats(
            result_shape
        )


    # ========================================================
    # START GEOMETRY
    # ========================================================

    start_geometry = None


    if os.path.exists(
        start_step
    ):

        start_shape = load_step(
            start_step
        )


        start_geometry = geometry_stats(
            start_shape
        )


    # ========================================================
    # GEOMETRY CHANGE
    # ========================================================

    geometry_change = None


    if (
        start_geometry
        and
        result_geometry
    ):

        volume_delta = (
            result_geometry[
                "volume_mm3"
            ]
            -
            start_geometry[
                "volume_mm3"
            ]
        )


        geometry_change = {

            "solids_delta":

                result_geometry[
                    "solids"
                ]
                -
                start_geometry[
                    "solids"
                ],

            "faces_delta":

                result_geometry[
                    "faces"
                ]
                -
                start_geometry[
                    "faces"
                ],

            "edges_delta":

                result_geometry[
                    "edges"
                ]
                -
                start_geometry[
                    "edges"
                ],

            "volume_delta_mm3":
                volume_delta,

            "absolute_volume_change_mm3":
                abs(
                    volume_delta
                )
        }


        if abs(
            start_geometry[
                "volume_mm3"
            ]
        ) > 1e-12:

            geometry_change[
                "relative_volume_change"
            ] = (

                abs(
                    volume_delta
                )
                /
                abs(
                    start_geometry[
                        "volume_mm3"
                    ]
                )
            )

        else:

            geometry_change[
                "relative_volume_change"
            ] = None


    # ========================================================
    # GROUND TRUTH
    # ========================================================

    gt_report = load_json(
        gt_report_path
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
            "ground_truth_report.json not found."
        )


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


    # ========================================================
    # GT METRICS
    # ========================================================

    gt_metrics = {

        "chamfer_distance":
            None,

        "voxel_iou":
            None,

        "volumetric_precision":
            None,

        "volumetric_recall":
            None,

        "volumetric_f1":
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

        "note":
            None
    }


    if gt_status != "CONFIRMED":

        gt_metrics[
            "note"
        ] = (
            "Ground Truth is not confirmed; "
            "GT-dependent metrics are N/A."
        )

    else:

        gt_metrics[
            "note"
        ] = (
            "Ground Truth exists, but geometric benchmark "
            "algorithms are not yet executed by this module."
        )


    # ========================================================
    # SUCCESS
    # ========================================================

    valid_brep = bool(

        result_geometry
        and
        result_geometry[
            "valid"
        ]
        and
        result_geometry[
            "solids"
        ]
        > 0
    )


    solid_count_preserved = None


    if (
        start_geometry
        and
        result_geometry
    ):

        solid_count_preserved = (

            start_geometry[
                "solids"
            ]
            ==
            result_geometry[
                "solids"
            ]
        )


    overall_success = bool(
        step_success
        and
        valid_brep
    )


    # ========================================================
    # REPORT
    # ========================================================

    report = {

        "experiment_id":
            experiment_id,

        "request_id":
            request_id,

        "method":
            "AUTODESK",

        "baseline":
            "neuralCAD-Edit",

        "model":
            autodesk_report.get(
                "model"
            ),

        "harness":
            autodesk_report.get(
                "harness"
            ),

        "status":
            autodesk_report.get(
                "status"
            ),

        "runtime": {

            "sec":
                runtime_sec,

            "min":
                runtime_min
        },

        "agent": {

            "vlm_responses":
                vlm_responses,

            "visual_feedback_renders":
                visual_renders,

            "input_tokens":
                token_metrics[
                    "input_tokens"
                ],

            "output_tokens":
                token_metrics[
                    "output_tokens"
                ],

            "total_tokens":
                token_metrics[
                    "total_tokens"
                ],

            "cost_estimate_usd":
                token_metrics[
                    "cost_estimate_usd"
                ]
        },

        "step": {

            "success":
                step_success,

            "path":
                final_step,

            "valid_brep":
                valid_brep,

            "solid_count_preserved":
                solid_count_preserved
        },

        "geometry": {

            "start":
                start_geometry,

            "result":
                result_geometry,

            "change":
                geometry_change
        },

        "ground_truth": {

            "status":
                gt_status,

            "reason":
                gt_reason,

            "geometry":
                gt_geometry
        },

        "gt_metrics":
            gt_metrics,

        "success":
            overall_success
    }


    # ========================================================
    # MODULE RUNTIME
    # ========================================================

    module_runtime = (
        time.perf_counter()
        -
        module_start
    )


    report[
        "metrics_module_runtime_s"
    ] = module_runtime


    # ========================================================
    # SAVE
    # ========================================================

    save_json(
        report,
        metrics_report_path
    )


    # ========================================================
    # CONSOLE RESULT
    # ========================================================

    header(
        "AUTODESK — METRICS RESULT"
    )


    print(
        "Experiment:",
        experiment_id
    )


    print(
        "Runtime:",
        runtime_sec,
        "s"
    )


    print(
        "VLM responses:",
        vlm_responses
    )


    print(
        "Visual renders:",
        visual_renders
    )


    print(
        "STEP success:",
        step_success
    )


    print(
        "Valid B-Rep:",
        valid_brep
    )


    print(
        "Solid count preserved:",
        solid_count_preserved
    )


    if geometry_change:

        print(
            "Volume change:",
            geometry_change[
                "volume_delta_mm3"
            ],
            "mm^3"
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
        "\nReport:"
    )

    print(
        metrics_report_path
    )


    return report


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    print(
        "pipeline/autodesk_metrics.py"
    )

    print(
        "Run through 1_MAIN.py "
        "or import run_autodesk_metrics()."
    )