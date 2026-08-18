# ============================================================
# FILE: pipeline/autodesk.py
# ASME CIE 2026 STUDENT HACKATHON
#
# AUTODESK neuralCAD-Edit BASELINE
#
# REAL BASELINE:
#     GPT-5.2 + CadQuery harness
#
# COMMAND:
#
# python -m src.scripts_benchmark_inference.run_harness
#     --config ...
#     --input ...
#     --userId gpt-5.2_cadquery-script
#     --harness .../cadquery_script.py
#     --output_dir ...
#     --required-extensions step
#     --n-rows 1
#
# INPUT:
#     main.json
#
# OUTPUT:
#
# experiments/Bxx/
#     val_edit_Bxx.parquet
#
#     autodesk_output/
#         stdout.log
#         autodesk_report.json
#         ... original baseline outputs ...
#
# ============================================================


import os
import sys
import json
import time
import subprocess

import pandas as pd


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
# PATH
# ============================================================

def resolve_path(
    project_root,
    value
):

    if os.path.isabs(
        value
    ):

        return os.path.normpath(
            value
        )

    return os.path.normpath(
        os.path.join(
            project_root,
            value
        )
    )


# ============================================================
# PREPARE ONE-ROW PARQUET
# ============================================================

def prepare_experiment_parquet(
    master_parquet,
    request_id,
    output_parquet
):

    header(
        "AUTODESK — PREPARE SINGLE REQUEST"
    )

    print(
        "Master parquet:"
    )

    print(
        master_parquet
    )

    print(
        "\nRequest:"
    )

    print(
        request_id
    )

    # ========================================================
    # CHECK MASTER PARQUET
    # ========================================================

    if not os.path.exists(
        master_parquet
    ):

        raise FileNotFoundError(
            master_parquet
        )

    # ========================================================
    # LOAD MASTER DATASET
    # ========================================================

    df = pd.read_parquet(
        master_parquet
    )

    if "request" not in df.columns:

        raise RuntimeError(
            "Column 'request' not found "
            "in master parquet."
        )

    # ========================================================
    # FIND REQUEST
    # ========================================================

    matches = df[
        df[
            "request"
        ].astype(
            str
        )
        ==
        str(
            request_id
        )
    ].copy()

    if len(
        matches
    ) == 0:

        raise RuntimeError(
            f"Request not found:\n{request_id}"
        )

    if len(
        matches
    ) > 1:

        raise RuntimeError(
            "Request ID is not unique."
        )

    # Save original dataset index BEFORE resetting anything.

    dataset_index = int(
        matches.index[
            0
        ]
    )

    # ========================================================
    # SANITIZE NULL / NaN STRING-LIKE FIELDS
    # ========================================================
    #
    # Some nullable values in parquet are loaded by pandas
    # as float NaN.
    #
    # neuralCAD-Edit expects strings for several fields and
    # internally may call methods such as:
    #
    #     value.endswith(...)
    #
    # A float NaN therefore causes:
    #
    #     'float' object has no attribute 'endswith'
    #
    # We preserve all real values and replace NaN only in
    # fields which should be strings.
    # ========================================================

    string_columns = [

        "request",

        "request_type",

        "file_name",

        "request_video_30fps_720p_audio",

        "request_transcript",

        "request_text",

        "request_events"
    ]

    for column in string_columns:

        if column not in matches.columns:

            continue

        matches[
            column
        ] = matches[
            column
        ].apply(

            lambda value:

                ""

                if pd.isna(
                    value
                )

                else value
        )

    # ========================================================
    # IMPORTANT:
    # DO NOT blindly sanitize array/object CAD fields.
    #
    # In particular:
    #
    #     brep_start_path
    #     views
    #
    # may contain numpy arrays / nested objects and must remain
    # in their original dataset representation.
    # ========================================================

    # ========================================================
    # CREATE OUTPUT DIRECTORY
    # ========================================================

    output_parent = os.path.dirname(
        output_parquet
    )

    if output_parent:

        os.makedirs(
            output_parent,
            exist_ok=True
        )

    # ========================================================
    # SAVE ONE-ROW PARQUET
    # ========================================================

    matches.to_parquet(
        output_parquet,
        index=False
    )

    if not os.path.exists(
        output_parquet
    ):

        raise RuntimeError(
            "Experiment parquet was not created."
        )

    # ========================================================
    # VERIFY SAVED PARQUET
    # ========================================================

    test_df = pd.read_parquet(
        output_parquet
    )

    if len(
        test_df
    ) != 1:

        raise RuntimeError(
            "Experiment parquet must contain exactly 1 row."
        )

    test_row = test_df.iloc[
        0
    ]

    # ========================================================
    # PRINT FIELD TYPES
    # ========================================================

    print(
        "\nPARQUET FIELD TYPES:"
    )

    for column in test_df.columns:

        value = test_row[
            column
        ]

        value_preview = repr(
            value
        )

        if len(
            value_preview
        ) > 200:

            value_preview = (
                value_preview[
                    :200
                ]
                +
                " ..."
            )

        print(
            column,
            "|",
            type(
                value
            ).__name__,
            "|",
            value_preview
        )

    # ========================================================
    # CHECK FOR NaN IN EXPECTED STRING FIELDS
    # ========================================================

    bad_string_fields = []

    for column in string_columns:

        if column not in test_df.columns:

            continue

        value = test_row[
            column
        ]

        # Strings are valid.
        if isinstance(
            value,
            str
        ):

            continue

        # Anything else in these fields is suspicious.
        bad_string_fields.append(
            {
                "column":
                    column,

                "type":
                    type(
                        value
                    ).__name__,

                "value":
                    repr(
                        value
                    )
            }
        )

    if bad_string_fields:

        print(
            "\nWARNING — NON-STRING VALUES REMAIN:"
        )

        for item in bad_string_fields:

            print(
                item[
                    "column"
                ],
                "| type =",
                item[
                    "type"
                ],
                "| value =",
                item[
                    "value"
                ]
            )

    # ========================================================
    # REPORT
    # ========================================================

    print(
        "\nDataset index:",
        dataset_index
    )

    print(
        "\nExperiment parquet:"
    )

    print(
        output_parquet
    )

    print(
        "Exists:",
        os.path.exists(
            output_parquet
        )
    )

    print(
        "Rows:",
        len(
            test_df
        )
    )

    print(
        "\nAUTODESK INPUT PARQUET READY"
    )

    # ========================================================
    # RETURN
    # ========================================================

    return dataset_index


# ============================================================
# OUTPUT FILE DISCOVERY
# ============================================================

def list_output_files(
    output_dir
):

    found = []


    if not os.path.exists(
        output_dir
    ):

        return found


    for root, dirs, files in os.walk(
        output_dir
    ):

        for filename in files:

            path = os.path.join(
                root,
                filename
            )


            found.append(
                path
            )


    return found


# ============================================================
# MAIN AUTODESK PIPELINE
# ============================================================

def run_autodesk(
    config,
    project_root
):

    header(
        "AUTODESK / neuralCAD-Edit BASELINE"
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


    autodesk_cfg = config.get(
        "autodesk",
        {}
    )


    harness_name = str(
        autodesk_cfg.get(
            "harness",
            "cadquery_script"
        )
    ).strip()


    model_name = str(
        autodesk_cfg.get(
            "model",
            "gpt-5.2"
        )
    ).strip()


    if harness_name != "cadquery_script":

        raise ValueError(
            "This Autodesk adapter currently "
            "supports harness= cadquery_script"
        )


    # ========================================================
    # MODEL KEY
    # ========================================================

    model_key = (
        f"{model_name}_cadquery-script"
    )


    # ========================================================
    # PATHS
    # ========================================================

    repo_root = os.path.join(
        project_root,
        "neuralCAD-Edit"
    )


    config_path = os.path.join(
        repo_root,
        "src",
        "config",
        "edit_192_external.json"
    )


    harness_path = os.path.join(
        repo_root,
        "src",
        "harnesses",
        "cadquery_script.py"
    )


    master_parquet = resolve_path(
        project_root,
        config[
            "dataset"
        ][
            "parquet"
        ]
    )


    experiment_dir = os.path.join(
        project_root,
        "experiments",
        experiment_id
    )


    experiment_parquet = os.path.join(
        experiment_dir,
        f"val_edit_{experiment_id}.parquet"
    )


    output_dir = os.path.join(
        experiment_dir,
        "autodesk_output"
    )


    stdout_log = os.path.join(
        output_dir,
        "stdout.log"
    )


    report_path = os.path.join(
        output_dir,
        "autodesk_report.json"
    )


    os.makedirs(
        output_dir,
        exist_ok=True
    )


    # ========================================================
    # REPORT CONFIG
    # ========================================================

    print(
        "Experiment:"
    )

    print(
        experiment_id
    )


    print(
        "\nRequest:"
    )

    print(
        request_id
    )


    print(
        "\nModel key:"
    )

    print(
        model_key
    )


    print(
        "\nConfig:"
    )

    print(
        config_path
    )


    print(
        "\nHarness:"
    )

    print(
        harness_path
    )


    print(
        "\nOutput:"
    )

    print(
        output_dir
    )


    # ========================================================
    # CHECKS
    # ========================================================

    header(
        "AUTODESK — CHECKS"
    )


    checks = {

        "repo_exists":
            os.path.exists(
                repo_root
            ),

        "config_exists":
            os.path.exists(
                config_path
            ),

        "harness_exists":
            os.path.exists(
                harness_path
            ),

        "master_parquet_exists":
            os.path.exists(
                master_parquet
            ),

        "api_key_available":
            bool(
                os.environ.get(
                    "OPENAI_API_KEY"
                )
            )
    }


    for key, value in checks.items():

        print(
            key,
            ":",
            value
        )


    if not checks[
        "repo_exists"
    ]:

        raise FileNotFoundError(
            repo_root
        )


    if not checks[
        "config_exists"
    ]:

        raise FileNotFoundError(
            config_path
        )


    if not checks[
        "harness_exists"
    ]:

        raise FileNotFoundError(
            harness_path
        )


    if not checks[
        "master_parquet_exists"
    ]:

        raise FileNotFoundError(
            master_parquet
        )


    if not checks[
        "api_key_available"
    ]:

        raise RuntimeError(
            "OPENAI_API_KEY not found."
        )


    # ========================================================
    # PREPARE INPUT PARQUET
    # ========================================================

    dataset_index = prepare_experiment_parquet(

        master_parquet=
            master_parquet,

        request_id=
            request_id,

        output_parquet=
            experiment_parquet
    )


    # ========================================================
    # ORIGINAL AUTODESK COMMAND
    # ========================================================

    command = [

        sys.executable,

        "-m",

        "src.scripts_benchmark_inference.run_harness",

        "--config",
        config_path,

        "--input",
        experiment_parquet,

        "--userId",
        model_key,

        "--harness",
        harness_path,

        "--output_dir",
        output_dir,

        "--required-extensions",
        "step",

        "--n-rows",
        "1"
    ]


    header(
        "AUTODESK — RUN BASELINE"
    )


    print(
        "Command:"
    )


    print(
        subprocess.list2cmdline(
            command
        )
    )


    print(
        "\nStarting real neuralCAD-Edit baseline..."
    )


    # ========================================================
    # RUN
    # ========================================================

    start_time = time.time()


    result = subprocess.run(

        command,

        cwd=
            repo_root,

        text=True,

        stdout=
            subprocess.PIPE,

        stderr=
            subprocess.STDOUT,

        env=
            os.environ.copy()
    )


    elapsed = (
        time.time()
        -
        start_time
    )


    # ========================================================
    # SAVE STDOUT
    # ========================================================

    with open(
        stdout_log,
        "w",
        encoding="utf-8",
        errors="replace"
    ) as f:

        f.write(
            result.stdout
            if result.stdout
            else ""
        )


    # Also print original baseline output.

    print(
        result.stdout
        if result.stdout
        else ""
    )


    # ========================================================
    # OUTPUT FILES
    # ========================================================

    output_files = list_output_files(
        output_dir
    )


    step_files = [

        path

        for path in output_files

        if os.path.splitext(
            path
        )[
            1
        ].lower()
        in {
            ".step",
            ".stp"
        }
    ]


    stl_files = [

        path

        for path in output_files

        if os.path.splitext(
            path
        )[
            1
        ].lower()
        ==
        ".stl"
    ]


    json_files = [

        path

        for path in output_files

        if os.path.splitext(
            path
        )[
            1
        ].lower()
        ==
        ".json"
    ]


    # ========================================================
    # STATUS
    # ========================================================

    return_code = int(
        result.returncode
    )


    step_success = (
        len(
            step_files
        )
        > 0
    )


    if (
        return_code == 0
        and
        step_success
    ):

        status = "SUCCESS"


    elif return_code == 0:

        status = (
            "COMPLETED_NO_STEP"
        )


    else:

        status = "FAILED"


    # ========================================================
    # FINAL REPORT
    # ========================================================

    report = {

        "experiment_id":
            experiment_id,

        "request_id":
            request_id,

        "dataset_index":
            dataset_index,

        "method":
            "AUTODESK",

        "baseline":
            "neuralCAD-Edit",

        "model":
            model_name,

        "model_key":
            model_key,

        "harness":
            harness_name,

        "status":
            status,

        "return_code":
            return_code,

        "runtime_sec":
            float(
                elapsed
            ),

        "runtime_min":
            float(
                elapsed
                /
                60.0
            ),

        "step_success":
            step_success,

        "input_parquet":
            experiment_parquet,

        "config":
            config_path,

        "harness_file":
            harness_path,

        "output_dir":
            output_dir,

        "stdout_log":
            stdout_log,

        "output_files":
            output_files,

        "step_files":
            step_files,

        "stl_files":
            stl_files,

        "json_files":
            json_files
    }


    save_json(
        report,
        report_path
    )


    # ========================================================
    # RESULT
    # ========================================================

    header(
        "AUTODESK BASELINE RESULT"
    )


    print(
        "Experiment:",
        experiment_id
    )


    print(
        "Status:",
        status
    )


    print(
        "Return code:",
        return_code
    )


    print(
        "Runtime:",
        f"{elapsed:.2f}",
        "s"
    )


    print(
        "Runtime:",
        f"{elapsed / 60.0:.2f}",
        "min"
    )


    print(
        "STEP success:",
        step_success
    )


    print(
        "STEP files:",
        len(
            step_files
        )
    )


    print(
        "STL files:",
        len(
            stl_files
        )
    )


    print(
        "JSON files:",
        len(
            json_files
        )
    )


    print(
        "\nReport:"
    )

    print(
        report_path
    )


    print(
        "\nStdout:"
    )

    print(
        stdout_log
    )


    return report


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    print(
        "pipeline/autodesk.py"
    )

    print(
        "Run through 1_MAIN.py."
    )