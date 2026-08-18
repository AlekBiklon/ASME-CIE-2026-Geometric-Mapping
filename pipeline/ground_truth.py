# ============================================================
# FILE: pipeline/ground_truth.py
# ASME CIE 2026 STUDENT HACKATHON
#
# MODULE 3 — GROUND TRUTH IDENTIFICATION / VALIDATION
#
# PURPOSE:
#
#     Reconstruct possible Ground Truth from the edit history
#     of the SAME CAD model in neuralCAD-Edit dataset.
#
# IMPORTANT:
#
#     The dataset parquet contains the START B-Rep for each
#     request, but does not contain an explicit GT column.
#
#     Therefore this module:
#
#         1. Finds the current request.
#         2. Finds all requests for the same CAD model.
#         3. Sorts them by B-Rep timestamp.
#         4. Finds later B-Rep states.
#         5. Compares candidate geometry against START.
#         6. Confirms GT only if sufficient evidence exists.
#
#
# OUTPUT:
#
# experiments/Bxx/ground_truth/
#
#     ground_truth_report.json
#
# and, ONLY when GT is confirmed:
#
#     Bxx_gt.step
#
#
# STATUS:
#
#     CONFIRMED
#     NOT_CONFIRMED
#
# Ground Truth is NEVER used to generate our CAD edit.
# ============================================================


import os
import re
import json
import shutil
import traceback

import pandas as pd
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

def save_json(data, path):

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
# PATH HELPERS
# ============================================================

def resolve_project_path(
    project_root,
    path
):

    if os.path.isabs(
        path
    ):

        return os.path.normpath(
            path
        )

    return os.path.normpath(
        os.path.join(
            project_root,
            path
        )
    )


# ============================================================
# TRANSCRIPT
# ============================================================

def transcript_text(value):

    if value is None:

        return ""


    text = str(
        value
    )


    try:

        data = json.loads(
            text
        )

        segments = data.get(
            "segments",
            []
        )

        parts = []


        for segment in segments:

            part = str(
                segment.get(
                    "text",
                    ""
                )
            ).strip()


            if part:

                parts.append(
                    part
                )


        if parts:

            return " ".join(
                parts
            )


    except Exception:

        pass


    return text


# ============================================================
# BREP PATH EXTRACTION
# ============================================================

def extract_step_path(value):

    text = str(
        value
    )


    match = re.search(
        r"(breps[/\\][^'\"\]\)]+\.step)",
        text,
        flags=re.IGNORECASE
    )


    if not match:

        return None


    return match.group(
        1
    ).replace(
        "\\",
        "/"
    )


def extract_step_timestamp(
    step_path
):

    if not step_path:

        return None


    match = re.search(
        r"_(\d+\.\d+)\.step$",
        step_path
    )


    if not match:

        return None


    return float(
        match.group(
            1
        )
    )


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
# GEOMETRY STATISTICS
# ============================================================

def geometry_stats(
    shape
):

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

        "volume":
            float(
                volume
            ),

        "bbox_x":
            float(
                bbox.xlen
            ),

        "bbox_y":
            float(
                bbox.ylen
            ),

        "bbox_z":
            float(
                bbox.zlen
            )
    }


# ============================================================
# GEOMETRY COMPARISON
# ============================================================

def compare_geometry(
    a,
    b,
    volume_tol=1e-9,
    bbox_tol=1e-7
):

    volume_delta = (
        b[
            "volume"
        ]
        -
        a[
            "volume"
        ]
    )


    solids_delta = (
        b[
            "solids"
        ]
        -
        a[
            "solids"
        ]
    )


    faces_delta = (
        b[
            "faces"
        ]
        -
        a[
            "faces"
        ]
    )


    edges_delta = (
        b[
            "edges"
        ]
        -
        a[
            "edges"
        ]
    )


    bbox_delta = {

        "x":
            b[
                "bbox_x"
            ]
            -
            a[
                "bbox_x"
            ],

        "y":
            b[
                "bbox_y"
            ]
            -
            a[
                "bbox_y"
            ],

        "z":
            b[
                "bbox_z"
            ]
            -
            a[
                "bbox_z"
            ]
    }


    same_volume = (
        abs(
            volume_delta
        )
        <=
        volume_tol
    )


    same_solids = (
        solids_delta
        ==
        0
    )


    same_faces = (
        faces_delta
        ==
        0
    )


    same_edges = (
        edges_delta
        ==
        0
    )


    same_bbox = all(

        abs(
            delta
        )
        <=
        bbox_tol

        for delta in bbox_delta.values()
    )


    geometrically_identical_basic = (

        same_volume
        and
        same_solids
        and
        same_faces
        and
        same_edges
        and
        same_bbox
    )


    return {

        "volume_delta":
            float(
                volume_delta
            ),

        "solids_delta":
            int(
                solids_delta
            ),

        "faces_delta":
            int(
                faces_delta
            ),

        "edges_delta":
            int(
                edges_delta
            ),

        "bbox_delta":
            bbox_delta,

        "same_volume":
            same_volume,

        "same_solids":
            same_solids,

        "same_faces":
            same_faces,

        "same_edges":
            same_edges,

        "same_bbox":
            same_bbox,

        "geometrically_identical_basic":
            geometrically_identical_basic
    }


# ============================================================
# MAIN MODULE
# ============================================================

def run_ground_truth(
    config,
    project_root
):

    header(
        "MODULE 3 — GROUND TRUTH"
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


    if not request_id:

        raise ValueError(
            "request_id missing."
        )


    dataset_cfg = config.get(
        "dataset",
        {}
    )


    parquet_cfg = dataset_cfg.get(
        "parquet"
    )


    if not parquet_cfg:

        raise ValueError(
            "dataset.parquet missing."
        )


    parquet_path = resolve_project_path(
        project_root,
        parquet_cfg
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


    gt_dir = os.path.join(
        experiment_dir,
        "ground_truth"
    )


    os.makedirs(
        gt_dir,
        exist_ok=True
    )


    local_start_step = os.path.join(
        input_dir,
        f"{experiment_id}_start.step"
    )


    gt_output_step = os.path.join(
        gt_dir,
        f"{experiment_id}_gt.step"
    )


    report_path = os.path.join(
        gt_dir,
        "ground_truth_report.json"
    )


    # ========================================================
    # REMOVE OLD CONFIRMED GT
    # ========================================================

    if os.path.exists(
        gt_output_step
    ):

        os.remove(
            gt_output_step
        )


    # ========================================================
    # BASIC CHECKS
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
        "\nParquet:"
    )

    print(
        parquet_path
    )


    print(
        "Exists:",
        os.path.exists(
            parquet_path
        )
    )


    print(
        "\nLocal START STEP:"
    )

    print(
        local_start_step
    )


    print(
        "Exists:",
        os.path.exists(
            local_start_step
        )
    )


    if not os.path.exists(
        parquet_path
    ):

        raise FileNotFoundError(
            parquet_path
        )


    if not os.path.exists(
        local_start_step
    ):

        raise FileNotFoundError(
            local_start_step
        )


    # ========================================================
    # LOAD DATASET
    # ========================================================

    df = pd.read_parquet(
        parquet_path
    )


    if "request" not in df.columns:

        raise RuntimeError(
            "Parquet has no request column."
        )


    matches = df[
        df[
            "request"
        ].astype(
            str
        )
        ==
        request_id
    ]


    if len(
        matches
    ) == 0:

        raise RuntimeError(
            "Request not found in dataset."
        )


    if len(
        matches
    ) > 1:

        raise RuntimeError(
            "Request ID is not unique."
        )


    target_index = matches.index[
        0
    ]


    target_row = matches.iloc[
        0
    ]


    file_name = str(
        target_row[
            "file_name"
        ]
    )


    instruction = transcript_text(
        target_row.get(
            "request_transcript"
        )
    )


    dataset_start_relative = (
        extract_step_path(
            target_row.get(
                "brep_start_path"
            )
        )
    )


    dataset_start_timestamp = (
        extract_step_timestamp(
            dataset_start_relative
        )
    )


    # ========================================================
    # DATASET ROOT
    # ========================================================

    parquet_dir = os.path.dirname(
        parquet_path
    )


    dataset_root = os.path.dirname(
        parquet_dir
    )


    # ========================================================
    # LOAD LOCAL START
    # ========================================================

    start_shape = load_step(
        local_start_step
    )


    start_stats = geometry_stats(
        start_shape
    )


    # ========================================================
    # SAME MODEL HISTORY
    # ========================================================

    same_model = df[
        df[
            "file_name"
        ].astype(
            str
        )
        ==
        file_name
    ]


    history = []


    for dataset_index, row in (
        same_model.iterrows()
    ):

        relative_step = (
            extract_step_path(
                row.get(
                    "brep_start_path"
                )
            )
        )


        timestamp = (
            extract_step_timestamp(
                relative_step
            )
        )


        absolute_step = None


        if relative_step:

            absolute_step = os.path.normpath(

                os.path.join(
                    dataset_root,
                    relative_step
                )
            )


        history.append({

            "dataset_index":
                int(
                    dataset_index
                ),

            "request_id":
                str(
                    row.get(
                        "request"
                    )
                ),

            "instruction":
                transcript_text(
                    row.get(
                        "request_transcript"
                    )
                ),

            "step_relative":
                relative_step,

            "step_absolute":
                absolute_step,

            "step_timestamp":
                timestamp,

            "step_exists":
                bool(
                    absolute_step
                    and
                    os.path.exists(
                        absolute_step
                    )
                )
        })


    history.sort(

        key=lambda item:

            float(
                "inf"
            )
            if
            item[
                "step_timestamp"
            ]
            is None
            else
            item[
                "step_timestamp"
            ]
    )


    # ========================================================
    # PRINT HISTORY
    # ========================================================

    header(
        "SAME MODEL HISTORY"
    )


    print(
        "File name:"
    )

    print(
        file_name
    )


    print(
        "\nHistory records:",
        len(
            history
        )
    )


    for item in history:

        print("\n" + "-" * 88)

        print(
            "Dataset index:",
            item[
                "dataset_index"
            ]
        )

        print(
            "Request:",
            item[
                "request_id"
            ]
        )

        print(
            "STEP:",
            item[
                "step_relative"
            ]
        )

        print(
            "Timestamp:",
            item[
                "step_timestamp"
            ]
        )

        print(
            "Instruction:"
        )

        print(
            item[
                "instruction"
            ]
        )


    # ========================================================
    # FIND LATER CANDIDATES
    # ========================================================

    candidates = []


    if dataset_start_timestamp is not None:

        for item in history:

            timestamp = item[
                "step_timestamp"
            ]


            if (
                timestamp
                is not None
                and
                timestamp
                >
                dataset_start_timestamp
                and
                item[
                    "step_exists"
                ]
            ):

                candidates.append(
                    item
                )


    candidates.sort(
        key=lambda item:
            item[
                "step_timestamp"
            ]
    )


    # ========================================================
    # EVALUATE CANDIDATES
    # ========================================================

    candidate_reports = []


    confirmed_candidate = None


    header(
        "GROUND TRUTH CANDIDATES"
    )


    if not candidates:

        print(
            "No later B-Rep states found "
            "for the same CAD model."
        )


    for rank, item in enumerate(
        candidates,
        start=1
    ):

        candidate_shape = load_step(
            item[
                "step_absolute"
            ]
        )


        candidate_stats = geometry_stats(
            candidate_shape
        )


        comparison = compare_geometry(
            start_stats,
            candidate_stats
        )


        time_delta = (

            item[
                "step_timestamp"
            ]
            -
            dataset_start_timestamp
        )


        report_item = {

            "rank":
                rank,

            "dataset_index":
                item[
                    "dataset_index"
                ],

            "request_id":
                item[
                    "request_id"
                ],

            "instruction":
                item[
                    "instruction"
                ],

            "step":
                item[
                    "step_absolute"
                ],

            "step_timestamp":
                item[
                    "step_timestamp"
                ],

            "time_delta_from_start_s":
                float(
                    time_delta
                ),

            "geometry":
                candidate_stats,

            "comparison_to_start":
                comparison
        }


        candidate_reports.append(
            report_item
        )


        print("\n" + "-" * 88)

        print(
            "Candidate:",
            rank
        )

        print(
            "STEP:"
        )

        print(
            item[
                "step_absolute"
            ]
        )

        print(
            "Time delta:",
            time_delta,
            "s"
        )

        print(
            "Valid:",
            candidate_stats[
                "valid"
            ]
        )

        print(
            "Volume delta:",
            comparison[
                "volume_delta"
            ]
        )

        print(
            "Faces delta:",
            comparison[
                "faces_delta"
            ]
        )

        print(
            "Edges delta:",
            comparison[
                "edges_delta"
            ]
        )

        print(
            "Identical to START:",
            comparison[
                "geometrically_identical_basic"
            ]
        )


        # ====================================================
        # CONFIRMATION RULE
        # ====================================================
        #
        # We only confirm the FIRST later model state when:
        #
        #     - candidate is valid
        #     - candidate is not geometrically identical
        #       to START
        #
        # This is a conservative rule.
        #
        # ====================================================

        if (
            confirmed_candidate
            is None
            and
            candidate_stats[
                "valid"
            ]
            and
            not comparison[
                "geometrically_identical_basic"
            ]
        ):

            confirmed_candidate = (
                report_item
            )


    # ========================================================
    # FINAL STATUS
    # ========================================================

    if confirmed_candidate is None:

        status = (
            "NOT_CONFIRMED"
        )


        if candidates:

            first_candidate = (
                candidate_reports[
                    0
                ]
            )


            if first_candidate[
                "comparison_to_start"
            ][
                "geometrically_identical_basic"
            ]:

                reason = (
                    "The next available B-Rep state "
                    "for the same CAD model is "
                    "geometrically identical to "
                    "the experiment START STEP."
                )

            else:

                reason = (
                    "No later B-Rep candidate passed "
                    "the conservative Ground Truth "
                    "confirmation rule."
                )

        else:

            reason = (
                "No later B-Rep state exists "
                "for the same CAD model."
            )


    else:

        status = (
            "CONFIRMED"
        )


        reason = (
            "A later valid B-Rep state for the same CAD model "
            "was found and differs geometrically from START."
        )


        # ====================================================
        # COPY GT
        # ====================================================

        shutil.copy2(
            confirmed_candidate[
                "step"
            ],
            gt_output_step
        )


    # ========================================================
    # REPORT
    # ========================================================

    final_report = {

        "experiment_id":
            experiment_id,

        "request_id":
            request_id,

        "dataset_index":
            int(
                target_index
            ),

        "file_name":
            file_name,

        "instruction":
            instruction,

        "status":
            status,

        "reason":
            reason,

        "start_step":
            local_start_step,

        "dataset_start_step":
            dataset_start_relative,

        "dataset_start_timestamp":
            dataset_start_timestamp,

        "start_geometry":
            start_stats,

        "history":
            history,

        "candidates":
            candidate_reports,

        "confirmed_ground_truth":
            confirmed_candidate,

        "ground_truth_step":
            (
                gt_output_step
                if
                status
                ==
                "CONFIRMED"
                else
                None
            )
    }


    save_json(
        final_report,
        report_path
    )


    # ========================================================
    # RESULT
    # ========================================================

    header(
        "MODULE 3 — RESULT"
    )


    print(
        "Status:"
    )

    print(
        status
    )


    print(
        "\nReason:"
    )

    print(
        reason
    )


    print(
        "\nReport:"
    )

    print(
        report_path
    )


    if status == "CONFIRMED":

        print(
            "\nGround Truth STEP:"
        )

        print(
            gt_output_step
        )

        print(
            "Exists:",
            os.path.exists(
                gt_output_step
            )
        )


    else:

        print(
            "\nGround Truth STEP:"
        )

        print(
            "NOT CREATED"
        )


    return final_report


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    print(
        "pipeline/ground_truth.py"
    )

    print(
        "This module should normally be "
        "launched through 1_MAIN.py."
    )