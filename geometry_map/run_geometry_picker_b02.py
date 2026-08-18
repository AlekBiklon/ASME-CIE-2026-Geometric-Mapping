# ============================================================
# FILE: run_geometry_picker_b02.py
# ASME CIE 2026 STUDENT HACKATHON
#
# EXPERIMENT:
#     B02
#
# METHOD:
#     Semi-Automatic Geometric Mapping
#
# PURPOSE:
#     Launch the B02 interactive geometry picker as a
#     completely independent desktop application.
#
# PIPELINE:
#
#     Jupyter
#        ↓
#     separate Python process
#        ↓
#     desktop 3D viewer
#        ↓
#     user selects sharp edges
#        ↓
#     exact B-Rep edge IDs
#        ↓
#     edit_request.json
#
# USER CONTROLS:
#
#     RIGHT CLICK = select / deselect edge
#     U           = undo
#     C           = clear
#     S           = save selection
#     Q           = close viewer
#
# IMPORTANT:
#     Ground Truth is NOT used.
# ============================================================

import os
import sys
import traceback


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = (
    r"C:\PROGRAMING_PYTHON\2026-08-14_ASME_Hackathon_2026"
)

REPO_ROOT = os.path.join(
    PROJECT_ROOT,
    "neuralCAD-Edit"
)


# ============================================================
# ADD neuralCAD-Edit TO PYTHON PATH
# ============================================================

if REPO_ROOT not in sys.path:

    sys.path.insert(
        0,
        REPO_ROOT
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 78)
    print("B02 — STANDALONE GEOMETRY PICKER")
    print("=" * 78)

    print("\nPython:")
    print(sys.executable)

    print("\nRepository:")
    print(REPO_ROOT)

    print(
        "\nRepository exists:",
        os.path.exists(REPO_ROOT)
    )


    # ========================================================
    # IMPORT AFTER sys.path CONFIGURATION
    # ========================================================

    import pyvista as pv

    from src.harnesses.geometry_map.geometry_picker import (
        run_geometry_picker
    )


    # ========================================================
    # FORCE DESKTOP MODE
    # ========================================================

    try:

        pv.set_jupyter_backend(
            "none"
        )

    except Exception:

        pass


    # ========================================================
    # B02 PATHS
    # ========================================================

    B02_STEP = os.path.join(
        PROJECT_ROOT,
        "neuralCAD-Edit-data",
        "edit_192_external",
        "breps",
        "SUJ2G2UMJQR7PMBX_1762932954.777719.step"
    )


    B02_REQUEST = os.path.join(
        PROJECT_ROOT,
        "experiments",
        "B02",
        "input",
        "edit_request.json"
    )


    print("\nSTEP:")
    print(B02_STEP)

    print(
        "STEP exists:",
        os.path.exists(B02_STEP)
    )


    print("\nREQUEST:")
    print(B02_REQUEST)

    print(
        "Request exists:",
        os.path.exists(B02_REQUEST)
    )


    if not os.path.exists(B02_STEP):

        raise FileNotFoundError(
            B02_STEP
        )


    if not os.path.exists(B02_REQUEST):

        raise FileNotFoundError(
            B02_REQUEST
        )


    # ========================================================
    # START PICKER
    # ========================================================

    print("\nStarting desktop viewer...")


    result = run_geometry_picker(

        step_file=
            B02_STEP,

        edit_request_json=
            B02_REQUEST,

        mode=
            "MULTI_EDGE"
    )


    # ========================================================
    # RESULT
    # ========================================================

    print("\n" + "=" * 78)
    print("B02 PICKER FINISHED")
    print("=" * 78)

    print(
        result
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception:

        print("\n" + "=" * 78)
        print("ERROR")
        print("=" * 78)

        traceback.print_exc()

    finally:

        input(
            "\nPress ENTER to close this console..."
        )