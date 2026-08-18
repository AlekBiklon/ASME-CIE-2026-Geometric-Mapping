# ============================================================
# FILE: pipeline/cad_edit.py
# ASME CIE 2026 STUDENT HACKATHON
#
# MODULE 2 — CAD EDIT
#
# PURPOSE:
#     Execute deterministic CAD editing using data that was
#     already prepared and grounded by MODULE 1.
#
# INPUT:
#
#     experiments/Bxx/input/Bxx_start.step
#     experiments/Bxx/input/edit_request.json
#
# OUTPUT:
#
#     experiments/Bxx/our_method_output/Bxx_result.step
#     experiments/Bxx/our_method_output/Bxx_edit_report.json
#     experiments/Bxx/our_method_output/cad_edit_report.json
#
#
# IMPORTANT:
#
#     - Does NOT open Viewer.
#     - Does NOT modify grounding.
#     - Does NOT search Ground Truth.
#     - Does NOT calculate final benchmark metrics.
#
#     This module performs only deterministic CAD editing.
#
#
# SUPPORTED BY deterministic_edit.py:
#
#     ADD_HOLE
#     FILLET
#     CHAMFER
#
# ============================================================


import os
import sys
import json
import time
import traceback


# ============================================================
# CONSOLE
# ============================================================

def header(title):

    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):

    if not os.path.exists(path):

        raise FileNotFoundError(
            f"JSON file not found:\n{path}"
        )

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
# EDIT REQUEST VALIDATION
# ============================================================

def validate_edit_request(
    request
):

    operation = str(
        request.get(
            "operation",
            ""
        )
    ).strip().upper()


    if not operation:

        raise ValueError(
            "operation is missing in edit_request.json"
        )


    parameters = request.get(
        "parameters",
        {}
    )


    target = request.get(
        "target",
        {}
    )


    # ========================================================
    # CHAMFER
    # ========================================================

    if operation == "CHAMFER":

        # Two supported CHAMFER parameter sources:
        #
        # 1) Explicit numeric distance:
        #       parameters.distance_mm
        #       target.edge_ids
        #
        # 2) Reference geometry (B08 and similar):
        #       parameters.distance_source = "REFERENCE_GEOMETRY"
        #       reference.edge_ids
        #       target.edge_ids
        #
        # In reference mode the deterministic CAD engine extracts
        # the chamfer size from the selected existing chamfer.

        distance_source = str(
            parameters.get(
                "distance_source",
                "TEXT"
            )
        ).strip().upper()

        edge_ids = target.get(
            "edge_ids",
            []
        )

        if not edge_ids:

            raise ValueError(
                "CHAMFER requires target.edge_ids"
            )

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
                    "Reference-based CHAMFER requires "
                    "reference.edge_ids"
                )

        else:

            if "distance_mm" not in parameters:

                raise ValueError(
                    "CHAMFER requires parameters.distance_mm "
                    "or parameters.distance_source="
                    "'REFERENCE_GEOMETRY'."
                )

            distance_mm = float(
                parameters[
                    "distance_mm"
                ]
            )

            if distance_mm <= 0:

                raise ValueError(
                    "CHAMFER distance must be > 0."
                )


    # ========================================================
    # FILLET
    # ========================================================

    elif operation == "FILLET":

        # FILLET supports two request formats:
        #
        # 1) Legacy / single-radius:
        #    parameters.radius_mm
        #    target.edge_ids
        #
        # 2) Compound / multi-radius:
        #    target.edge_groups = [
        #        {"radius_mm": 2.0, "edge_ids": [...]},
        #        {"radius_mm": 1.0, "edge_ids": [...]}
        #    ]
        #
        # The legacy format is intentionally preserved so that
        # previous experiments continue to work.

        edge_groups = target.get(
            "edge_groups",
            []
        )

        if edge_groups:

            if not isinstance(
                edge_groups,
                list
            ):

                raise ValueError(
                    "FILLET target.edge_groups must be a list."
                )

            for group_index, group in enumerate(
                edge_groups,
                start=1
            ):

                if not isinstance(
                    group,
                    dict
                ):

                    raise ValueError(
                        f"FILLET edge group {group_index} "
                        "must be an object."
                    )

                if "radius_mm" not in group:

                    raise ValueError(
                        f"FILLET edge group {group_index} "
                        "requires radius_mm."
                    )

                group_radius = float(
                    group[
                        "radius_mm"
                    ]
                )

                if group_radius <= 0:

                    raise ValueError(
                        f"FILLET edge group {group_index} "
                        "radius must be > 0."
                    )

                group_edge_ids = group.get(
                    "edge_ids",
                    []
                )

                if not group_edge_ids:

                    raise ValueError(
                        f"FILLET edge group {group_index} "
                        "requires edge_ids."
                    )

        else:

            if "radius_mm" not in parameters:

                raise ValueError(
                    "FILLET requires parameters.radius_mm "
                    "for a single-radius request, or "
                    "target.edge_groups for a multi-radius request."
                )

            radius_mm = float(
                parameters[
                    "radius_mm"
                ]
            )

            if radius_mm <= 0:

                raise ValueError(
                    "FILLET radius must be > 0."
                )

            edge_ids = target.get(
                "edge_ids",
                []
            )

            if not edge_ids:

                raise ValueError(
                    "FILLET requires target.edge_ids "
                    "or target.edge_groups."
                )


    # ========================================================
    # ADD HOLE
    # ========================================================

    elif operation == "ADD_HOLE":

        # ADD_HOLE supports two request formats:
        #
        # 1) Legacy / explicit-diameter hole:
        #       parameters.diameter_mm
        #       target.face_id
        #       target.point_xyz
        #
        # 2) Reference-hole pair / B09:
        #       parameters.geometry_source = "REFERENCE_HOLES"
        #       parameters.position_rule = "MIDPOINT"
        #       reference.hole_1_edge_ids
        #       reference.hole_2_edge_ids
        #
        # The legacy format is intentionally preserved so that
        # previous experiments continue to work unchanged.

        geometry_source = str(
            parameters.get(
                "geometry_source",
                "TEXT"
            )
        ).strip().upper()

        if geometry_source == "REFERENCE_HOLES":

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

            if not hole_1_edge_ids:

                raise ValueError(
                    "Reference-based ADD_HOLE requires "
                    "reference.hole_1_edge_ids"
                )

            if not hole_2_edge_ids:

                raise ValueError(
                    "Reference-based ADD_HOLE requires "
                    "reference.hole_2_edge_ids"
                )

            if len(
                hole_1_edge_ids
            ) != 1:

                raise ValueError(
                    "Reference-based ADD_HOLE requires exactly "
                    "one edge in reference.hole_1_edge_ids"
                )

            if len(
                hole_2_edge_ids
            ) != 1:

                raise ValueError(
                    "Reference-based ADD_HOLE requires exactly "
                    "one edge in reference.hole_2_edge_ids"
                )

            if (
                hole_1_edge_ids[
                    0
                ]
                ==
                hole_2_edge_ids[
                    0
                ]
            ):

                raise ValueError(
                    "Reference-based ADD_HOLE requires "
                    "two different reference-hole edges."
                )

            position_rule = str(
                parameters.get(
                    "position_rule",
                    ""
                )
            ).strip().upper()

            if position_rule != "MIDPOINT":

                raise ValueError(
                    "Reference-based ADD_HOLE currently requires "
                    "parameters.position_rule = 'MIDPOINT'."
                )

        else:

            if "diameter_mm" not in parameters:

                raise ValueError(
                    "ADD_HOLE requires parameters.diameter_mm "
                    "for an explicit hole, or "
                    "parameters.geometry_source='REFERENCE_HOLES'."
                )

            diameter_mm = float(
                parameters[
                    "diameter_mm"
                ]
            )

            if diameter_mm <= 0:

                raise ValueError(
                    "ADD_HOLE diameter must be > 0."
                )

            face_id = target.get(
                "face_id"
            )

            point_xyz = target.get(
                "point_xyz"
            )

            if not face_id:

                raise ValueError(
                    "ADD_HOLE requires target.face_id"
                )

            if not point_xyz:

                raise ValueError(
                    "ADD_HOLE requires target.point_xyz"
                )


    # ========================================================
    # UNSUPPORTED
    # ========================================================

    else:

        raise NotImplementedError(
            f"Unsupported CAD operation: {operation}"
        )


    return operation


# ============================================================
# MAIN MODULE
# ============================================================

def run_cad_edit(
    config,
    project_root
):

    header(
        "MODULE 2 — CAD EDIT"
    )


    # ========================================================
    # EXPERIMENT
    # ========================================================

    experiment_id = str(
        config.get(
            "experiment_id",
            ""
        )
    ).strip()


    if not experiment_id:

        raise ValueError(
            "experiment_id missing in main.json"
        )


    print(
        "Experiment:"
    )

    print(
        experiment_id
    )


    # ========================================================
    # EXPERIMENT DIRECTORIES
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


    os.makedirs(
        output_dir,
        exist_ok=True
    )


    # ========================================================
    # INPUT FILES
    # ========================================================

    start_step = os.path.join(
        input_dir,
        f"{experiment_id}_start.step"
    )


    edit_request_path = os.path.join(
        input_dir,
        "edit_request.json"
    )


    # ========================================================
    # OUTPUT FILES
    # ========================================================

    output_step = os.path.join(
        output_dir,
        f"{experiment_id}_result.step"
    )


    # Detailed report created by deterministic_edit.py

    engine_report_path = os.path.join(
        output_dir,
        f"{experiment_id}_edit_report.json"
    )


    # Wrapper / module report

    module_report_path = os.path.join(
        output_dir,
        "cad_edit_report.json"
    )


    # ========================================================
    # CHECK INPUT FILES
    # ========================================================

    header(
        "CAD EDIT INPUT"
    )


    print(
        "START STEP:"
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
        "\nEDIT REQUEST:"
    )

    print(
        edit_request_path
    )


    print(
        "Exists:",
        os.path.exists(
            edit_request_path
        )
    )


    if not os.path.exists(
        start_step
    ):

        raise FileNotFoundError(
            start_step
        )


    if not os.path.exists(
        edit_request_path
    ):

        raise FileNotFoundError(
            edit_request_path
        )


    # ========================================================
    # LOAD REQUEST
    # ========================================================

    request = load_json(
        edit_request_path
    )


    operation = validate_edit_request(
        request
    )


    parameters = request.get(
        "parameters",
        {}
    )


    target = request.get(
        "target",
        {}
    )

    reference = request.get(
        "reference",
        {}
    )


    # ========================================================
    # REQUEST REPORT
    # ========================================================

    header(
        "CAD EDIT REQUEST"
    )


    print(
        "Operation:"
    )

    print(
        operation
    )


    print(
        "\nParameters:"
    )

    print(
        json.dumps(
            parameters,
            indent=4,
            ensure_ascii=False
        )
    )


    print(
        "\nTarget:"
    )

    print(
        json.dumps(
            target,
            indent=4,
            ensure_ascii=False
        )
    )

    if reference:

        print(
            "\nReference:"
        )

        print(
            json.dumps(
                reference,
                indent=4,
                ensure_ascii=False
            )
        )


    # ========================================================
    # ADD REPOSITORY TO sys.path
    # ========================================================

    repo_root = os.path.join(
        project_root,
        "neuralCAD-Edit"
    )


    if not os.path.exists(
        repo_root
    ):

        raise FileNotFoundError(
            repo_root
        )


    if repo_root not in sys.path:

        sys.path.insert(
            0,
            repo_root
        )


    # ========================================================
    # IMPORT CAD ENGINE
    # ========================================================

    try:

        from src.harnesses.geometry_map.deterministic_edit import (
            run_deterministic_edit
        )


    except Exception:

        header(
            "CAD ENGINE IMPORT FAILED"
        )

        traceback.print_exc()

        raise


    # ========================================================
    # REMOVE OLD OUTPUT STEP
    # ========================================================

    if os.path.exists(
        output_step
    ):

        print(
            "\nRemoving previous STEP:"
        )

        print(
            output_step
        )


        os.remove(
            output_step
        )


    # Optional: remove old engine report

    if os.path.exists(
        engine_report_path
    ):

        os.remove(
            engine_report_path
        )


    # ========================================================
    # EXECUTE
    # ========================================================

    header(
        "EXECUTE DETERMINISTIC EDIT"
    )


    print(
        "Input STEP:"
    )

    print(
        start_step
    )


    print(
        "\nEdit request:"
    )

    print(
        edit_request_path
    )


    print(
        "\nOutput STEP:"
    )

    print(
        output_step
    )


    print(
        "\nEngine report:"
    )

    print(
        engine_report_path
    )


    start_time = time.perf_counter()


    status = "FAILED"

    error_message = None

    engine_result = None


    try:

        # ====================================================
        # IMPORTANT:
        #
        # These argument names match the REAL function:
        #
        # run_deterministic_edit(
        #     step_path,
        #     edit_request_path,
        #     output_step_path,
        #     report_path=None
        # )
        # ====================================================

        engine_result = run_deterministic_edit(

            step_path=
                start_step,

            edit_request_path=
                edit_request_path,

            output_step_path=
                output_step,

            report_path=
                engine_report_path
        )


        status = "SUCCESS"


    except Exception as exc:

        error_message = (

            f"{type(exc).__name__}: "
            f"{exc}"
        )


        header(
            "CAD EDIT FAILED"
        )


        print(
            error_message
        )


        traceback.print_exc()


    runtime_s = (
        time.perf_counter()
        -
        start_time
    )


    # ========================================================
    # OUTPUT CHECK
    # ========================================================

    output_exists = os.path.exists(
        output_step
    )


    engine_report_exists = os.path.exists(
        engine_report_path
    )


    if (
        status == "SUCCESS"
        and
        not output_exists
    ):

        status = "FAILED"

        error_message = (
            "run_deterministic_edit completed "
            "without exception, but result STEP "
            "was not created."
        )


    # ========================================================
    # EXTRACT ENGINE RESULT
    # ========================================================

    step_success = None
    input_valid = None
    result_valid = None
    reimport_valid = None
    input_solids = None
    output_solids = None
    volume_change = None


    if isinstance(
        engine_result,
        dict
    ):

        step_success = engine_result.get(
            "step_success"
        )

        input_valid = engine_result.get(
            "input_valid"
        )

        result_valid = engine_result.get(
            "result_valid"
        )

        reimport_valid = engine_result.get(
            "reimport_valid"
        )

        input_solids = engine_result.get(
            "input_solids"
        )

        output_solids = engine_result.get(
            "output_solids"
        )

        volume_change = engine_result.get(
            "volume_change"
        )


    # ========================================================
    # MODULE REPORT
    # ========================================================

    module_report = {

        "experiment_id":
            experiment_id,

        "method":
            "GEOMETRIC_MAPPING",

        "module":
            "CAD_EDIT",

        "operation":
            operation,

        "parameters":
            parameters,

        "target":
            target,

        "reference":
            reference,

        "input_step":
            start_step,

        "edit_request":
            edit_request_path,

        "output_step":
            output_step,

        "engine_report":
            engine_report_path,

        "status":
            status,

        "runtime_seconds":
            runtime_s,

        "output_exists":
            output_exists,

        "engine_report_exists":
            engine_report_exists,

        "step_success":
            step_success,

        "input_valid":
            input_valid,

        "result_valid":
            result_valid,

        "reimport_valid":
            reimport_valid,

        "input_solids":
            input_solids,

        "output_solids":
            output_solids,

        "volume_change":
            volume_change,

        "error":
            error_message
    }


    save_json(
        module_report,
        module_report_path
    )


    # ========================================================
    # FINAL CONSOLE REPORT
    # ========================================================

    header(
        "MODULE 2 — RESULT"
    )


    print(
        "Status:"
    )

    print(
        status
    )


    print(
        "\nRuntime:"
    )

    print(
        f"{runtime_s:.6f} s"
    )


    print(
        "\nOutput STEP:"
    )

    print(
        output_step
    )


    print(
        "Exists:",
        output_exists
    )


    print(
        "\nDetailed engine report:"
    )

    print(
        engine_report_path
    )


    print(
        "Exists:",
        engine_report_exists
    )


    print(
        "\nModule report:"
    )

    print(
        module_report_path
    )


    if engine_result is not None:

        print(
            "\nENGINE RESULT"
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
            "Volume change:",
            volume_change
        )


    if error_message:

        print(
            "\nERROR:"
        )

        print(
            error_message
        )


    # ========================================================
    # FAIL MODULE CLEANLY
    # ========================================================

    if status != "SUCCESS":

        raise RuntimeError(
            "CAD editing failed. "
            "See console output and cad_edit_report.json."
        )


    # ========================================================
    # SUCCESS
    # ========================================================

    header(
        "MODULE 2 COMPLETE"
    )


    print(
        experiment_id,
        operation,
        "completed successfully."
    )


    return module_report


# ============================================================
# DIRECT EXECUTION PROTECTION
# ============================================================

if __name__ == "__main__":

    print(
        "pipeline/cad_edit.py"
    )

    print(
        "This module should normally be launched "
        "through 1_MAIN.py."
    )