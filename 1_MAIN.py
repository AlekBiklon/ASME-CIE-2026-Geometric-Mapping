# ============================================================
# FILE: 1_MAIN.py
# ASME CIE 2026 STUDENT HACKATHON
#
# UNIVERSAL PIPELINE ORCHESTRATOR
#
# PURPOSE:
#     Read main.json and launch one of two methods:
#
#         1. AUTODESK
#         2. GEOMETRIC_MAPPING
#
# GEOMETRIC_MAPPING contains 4 independent modules:
#
#     1. INPUT + VIEWER
#     2. CAD EDIT
#     3. GROUND TRUTH
#     4. METRICS
#
# The modules are enabled / disabled in main.json.
#
# IMPORTANT:
#     1_MAIN.py contains no CAD algorithms.
#     It only controls the workflow.
# ============================================================


import os
import sys
import json
import traceback


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = os.path.dirname(
    os.path.abspath(__file__)
)


CONFIG_PATH = os.path.join(
    PROJECT_ROOT,
    "main.json"
)


# ============================================================
# CONSOLE
# ============================================================

def header(title):

    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ============================================================
# CONFIG
# ============================================================

def load_config():

    if not os.path.exists(CONFIG_PATH):

        raise FileNotFoundError(
            f"main.json not found:\n{CONFIG_PATH}"
        )

    with open(
        CONFIG_PATH,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ============================================================
# VALIDATION
# ============================================================

def validate_config(config):

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
            ""
        )
    ).strip().upper()


    if not experiment_id:

        raise ValueError(
            "experiment_id is missing in main.json"
        )


    if not request_id:

        raise ValueError(
            "request_id is missing in main.json"
        )


    if method not in {
        "AUTODESK",
        "GEOMETRIC_MAPPING"
    }:

        raise ValueError(
            "method must be:\n"
            "AUTODESK\n"
            "or\n"
            "GEOMETRIC_MAPPING"
        )


    return (
        experiment_id,
        request_id,
        method
    )


# ============================================================
# AUTODESK PIPELINE
# ============================================================

def run_autodesk_pipeline(
    config
):

    header(
        "AUTODESK PIPELINE"
    )

    print(
        "Autodesk baseline selected."
    )


    # ========================================================
    # IMPORT AUTODESK MODULE
    # ========================================================

    try:

        from pipeline.autodesk import (
            run_autodesk
        )

    except ImportError:

        print(
            "\nAutodesk module is not connected yet."
        )

        print(
            "Expected file:"
        )

        print(
            os.path.join(
                PROJECT_ROOT,
                "pipeline",
                "autodesk.py"
            )
        )

        return


    # ========================================================
    # RUN
    # ========================================================

    result = run_autodesk(

        config=config,

        project_root=PROJECT_ROOT
    )
    
    from pipeline.autodesk_metrics import (
    run_autodesk_metrics)
    
    metrics_result = run_autodesk_metrics(
    config=config,
    project_root=PROJECT_ROOT
)
    
    from pipeline.geometry_benchmark import (
    run_geometry_benchmark
)
    
    geometry_result = run_geometry_benchmark(
        config=config,
        project_root=PROJECT_ROOT,
        method="AUTODESK"
)

    header(
        "AUTODESK PIPELINE RESULT"
    )

    print(
        result
    )


# ============================================================
# GEOMETRIC MAPPING PIPELINE
# ============================================================

def run_geometric_mapping_pipeline(
    config
):

    header(
        "GEOMETRIC MAPPING PIPELINE"
    )


    gm_config = config.get(
        "geometric_mapping",
        {}
    )


    pipeline_config = gm_config.get(
        "pipeline",
        {}
    )


    # ========================================================
    # MODULE SWITCHES
    # ========================================================

    input_viewer_enabled = bool(
        pipeline_config.get(
            "input_viewer",
            False
        )
    )


    cad_edit_enabled = bool(
        pipeline_config.get(
            "cad_edit",
            False
        )
    )


    ground_truth_enabled = bool(
        pipeline_config.get(
            "ground_truth",
            False
        )
    )


    metrics_enabled = bool(
        pipeline_config.get(
            "metrics",
            False
        )
    )


    print(
        "MODULES"
    )

    print(
        "1. Input + Viewer :",
        input_viewer_enabled
    )

    print(
        "2. CAD Edit       :",
        cad_edit_enabled
    )

    print(
        "3. Ground Truth   :",
        ground_truth_enabled
    )

    print(
        "4. Metrics        :",
        metrics_enabled
    )


    module_results = {}


    # ========================================================
    # MODULE 1 — INPUT + VIEWER
    # ========================================================

    if input_viewer_enabled:

        header(
            "MODULE 1 — INPUT + VIEWER"
        )


        from pipeline.input_viewer import (
            run_input_viewer
        )


        result = run_input_viewer(

            config=config,

            project_root=PROJECT_ROOT
        )


        module_results[
            "input_viewer"
        ] = result


        print(
            "\nMODULE 1 COMPLETE"
        )


    # ========================================================
    # MODULE 2 — CAD EDIT
    # ========================================================

    if cad_edit_enabled:

        header(
            "MODULE 2 — CAD EDIT"
        )


        try:

            from pipeline.cad_edit import (
                run_cad_edit
            )

        except ImportError:

            print(
                "CAD Edit module not found."
            )

            print(
                "Expected:"
            )

            print(
                os.path.join(
                    PROJECT_ROOT,
                    "pipeline",
                    "cad_edit.py"
                )
            )

            raise


        result = run_cad_edit(

            config=config,

            project_root=PROJECT_ROOT
        )


        module_results[
            "cad_edit"
        ] = result


        print(
            "\nMODULE 2 COMPLETE"
        )


    # ========================================================
    # MODULE 3 — GROUND TRUTH
    # ========================================================

    if ground_truth_enabled:

        header(
            "MODULE 3 — GROUND TRUTH"
        )


        try:

            from pipeline.ground_truth import (
                run_ground_truth
            )

        except ImportError:

            print(
                "Ground Truth module not found."
            )

            print(
                "Expected:"
            )

            print(
                os.path.join(
                    PROJECT_ROOT,
                    "pipeline",
                    "ground_truth.py"
                )
            )

            raise


        result = run_ground_truth(

            config=config,

            project_root=PROJECT_ROOT
        )


        module_results[
            "ground_truth"
        ] = result


        print(
            "\nMODULE 3 COMPLETE"
        )


    # ========================================================
    # MODULE 4 — METRICS
    # ========================================================

    if metrics_enabled:

        header(
            "MODULE 4 — METRICS"
        )


        try:

            from pipeline.metrics import (
                run_metrics
            )

        except ImportError:

            print(
                "Metrics module not found."
            )

            print(
                "Expected:"
            )

            print(
                os.path.join(
                    PROJECT_ROOT,
                    "pipeline",
                    "metrics.py"
                )
            )

            raise


        result = run_metrics(

            config=config,

            project_root=PROJECT_ROOT
        )


        module_results[
            "metrics"
        ] = result


        print(
            "\nMODULE 4 COMPLETE"
        )


    # ========================================================
    # NOTHING ENABLED
    # ========================================================

    if not any(
        [
            input_viewer_enabled,
            cad_edit_enabled,
            ground_truth_enabled,
            metrics_enabled
        ]
    ):

        print(
            "\nNo GEOMETRIC_MAPPING modules "
            "are enabled in main.json."
        )


    return module_results


# ============================================================
# MAIN
# ============================================================

def main():

    header(
        "ASME CIE 2026 — CAD EDIT EXPERIMENT RUNNER"
    )


    # ========================================================
    # ENVIRONMENT
    # ========================================================

    print(
        "\nPython:"
    )

    print(
        sys.executable
    )


    print(
        "\nProject root:"
    )

    print(
        PROJECT_ROOT
    )


    print(
        "\nConfig:"
    )

    print(
        CONFIG_PATH
    )


    # ========================================================
    # LOAD CONFIG
    # ========================================================

    config = load_config()


    experiment_id, request_id, method = (
        validate_config(
            config
        )
    )


    # ========================================================
    # REPORT
    # ========================================================

    header(
        "EXPERIMENT CONFIGURATION"
    )


    print(
        "Experiment ID:"
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


    # ========================================================
    # METHOD SWITCH
    # ========================================================

    if method == "AUTODESK":

        result = run_autodesk_pipeline(
            config
        )


    elif method == "GEOMETRIC_MAPPING":

        result = (
            run_geometric_mapping_pipeline(
                config
            )
        )


    else:

        raise RuntimeError(
            f"Unknown method: {method}"
        )


    # ========================================================
    # COMPLETE
    # ========================================================

    header(
        "EXPERIMENT PIPELINE COMPLETE"
    )


    print(
        "Experiment:",
        experiment_id
    )


    print(
        "Method:",
        method
    )


    return result


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()


    except KeyboardInterrupt:

        print(
            "\nExecution interrupted by user."
        )


    except Exception:

        header(
            "MAIN ERROR"
        )

        traceback.print_exc()

        sys.exit(
            1
        )