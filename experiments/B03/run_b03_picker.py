
import os
import sys
import traceback

PROJECT_ROOT = r"C:\PROGRAMING_PYTHON\2026-08-14_ASME_Hackathon_2026"
REPO_ROOT = os.path.join(PROJECT_ROOT, "neuralCAD-Edit")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    import pyvista as pv

    try:
        pv.set_jupyter_backend("none")
    except Exception:
        pass

    from src.harnesses.geometry_map.geometry_picker import run_geometry_picker

    STEP = r"C:\PROGRAMING_PYTHON\2026-08-14_ASME_Hackathon_2026\experiments\B03\input\B03_start.step"
    REQUEST = r"C:\PROGRAMING_PYTHON\2026-08-14_ASME_Hackathon_2026\experiments\B03\input\edit_request.json"

    print("=" * 78)
    print("B03 — STANDALONE GEOMETRY PICKER")
    print("=" * 78)

    print("\nSTEP:")
    print(STEP)
    print("STEP exists:", os.path.exists(STEP))

    print("\nREQUEST:")
    print(REQUEST)
    print("Request exists:", os.path.exists(REQUEST))

    print("\nStarting desktop viewer...")
    print("Select TWO circular edges of the SAME hole.")
    print("One edge from each side.")

    result = run_geometry_picker(
        step_file=STEP,
        edit_request_json=REQUEST,
        mode="MULTI_EDGE"
    )

    print("\n" + "=" * 78)
    print("B03 PICKER FINISHED")
    print("=" * 78)

    print("Saved:", result.get("finished"))

    selected = result.get("selected_edges", [])

    print(
        "Selected edge IDs:",
        [item.get("edge_id") for item in selected]
    )

except Exception:

    print("\n" + "=" * 78)
    print("ERROR")
    print("=" * 78)

    traceback.print_exc()

finally:

    input("\nPress ENTER to close this console...")
