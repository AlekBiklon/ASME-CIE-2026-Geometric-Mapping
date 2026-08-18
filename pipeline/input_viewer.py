# ============================================================
# FILE: pipeline/input_viewer.py
# ASME CIE 2026 STUDENT HACKATHON
#
# MODULE 1:
#     INPUT DATA + INTERACTIVE GEOMETRIC GROUNDING
#
# PURPOSE:
#
#     1. Read request_id from configuration.
#     2. Find the exact request in Autodesk/neuralCAD dataset.
#     3. Extract:
#
#           - dataset index
#           - instruction
#           - file_name
#           - START STEP
#           - video
#           - request events
#
#     4. Copy START STEP into:
#
#           experiments/Bxx/input/Bxx_start.step
#
#     5. Parse the natural-language engineering instruction.
#
#     6. Create:
#
#           edit_request.json
#
#     7. Open the universal geometry_picker.py.
#
#     8. User supplies WHERE through direct 3D selection.
#
#     9. Save exact B-Rep IDs into edit_request.json.
#
#
# IMPORTANT:
#
#     This module DOES NOT edit CAD geometry.
#     This module DOES NOT use Ground Truth.
#     This module DOES NOT calculate metrics.
#
# OUTPUT:
#
#     experiments/Bxx/input/
#
#         Bxx_start.step
#         resolved_input.json
#         edit_request.json
#
# ============================================================


import os
import sys
import re
import json
import shutil

import pandas as pd


# ============================================================
# HELPERS
# ============================================================

def header(title):

    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def save_json(data, path):

    os.makedirs(
        os.path.dirname(path),
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


def parse_brep_start_path(value):

    """
    Extract *.step path from neuralCAD parquet
    brep_start_path structure.
    """

    try:

        import numpy as np

        queue = [value]

        visited = set()


        while queue:

            current = queue.pop(0)

            current_id = id(current)

            if current_id in visited:
                continue

            visited.add(
                current_id
            )


            if isinstance(
                current,
                str
            ):

                if current.lower().endswith(
                    ".step"
                ):

                    return current

                continue


            try:

                items = np.asarray(
                    current,
                    dtype=object
                ).flatten()

                for item in items:

                    queue.append(
                        item
                    )

            except Exception:

                pass


    except Exception:

        pass


    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    text = str(
        value
    )


    match = re.search(
        r"(breps[/\\][^'\"\]\)]+\.step)",
        text,
        flags=re.IGNORECASE
    )


    if match:

        return match.group(1)


    raise RuntimeError(
        "Could not resolve START STEP from:\n"
        + text
    )


def is_missing_value(value):

    """
    Robustly detect missing scalar-like dataset values.

    Handles:
        None
        pandas.NA
        numpy.nan
        empty strings
        textual null markers
    """

    if value is None:

        return True


    try:

        missing = pd.isna(
            value
        )

        if isinstance(
            missing,
            bool
        ):

            if missing:

                return True

    except Exception:

        pass


    if isinstance(
        value,
        str
    ):

        text = value.strip()

        if text.lower() in {
            "",
            "none",
            "null",
            "nan",
            "<na>"
        }:

            return True


    return False


def clean_instruction_text(value):

    """
    Convert a candidate instruction value into clean text.
    Returns an empty string when the value is not usable.
    """

    if is_missing_value(
        value
    ):

        return ""


    if not isinstance(
        value,
        str
    ):

        return ""


    text = value.strip()


    if not text:

        return ""


    if text.lower() in {
        "none",
        "null",
        "nan",
        "<na>"
    }:

        return ""


    return text


def extract_text_from_structure(
    value,
    preferred_keys=None
):

    """
    Recursively extract human instruction text from dict/list structures.

    This is intentionally conservative: it prefers known textual fields
    and does not stringify arbitrary dictionaries as instructions.
    """

    if preferred_keys is None:

        preferred_keys = [
            "instruction",
            "request_instruction",
            "prompt",
            "text",
            "transcript",
            "utterance",
            "content",
            "message"
        ]


    if is_missing_value(
        value
    ):

        return ""


    if isinstance(
        value,
        str
    ):

        text = value.strip()


        if not text:

            return ""


        if (
            text.startswith("{")
            or
            text.startswith("[")
        ):

            try:

                decoded = json.loads(
                    text
                )

                extracted = extract_text_from_structure(
                    decoded,
                    preferred_keys=
                        preferred_keys
                )

                if extracted:

                    return extracted

            except Exception:

                pass


        return clean_instruction_text(
            text
        )


    if isinstance(
        value,
        dict
    ):

        for key in preferred_keys:

            if key not in value:

                continue


            extracted = extract_text_from_structure(
                value.get(
                    key
                ),
                preferred_keys=
                    preferred_keys
            )


            if extracted:

                return extracted


        segments = value.get(
            "segments"
        )


        if isinstance(
            segments,
            (list, tuple)
        ):

            texts = []


            for segment in segments:

                if isinstance(
                    segment,
                    dict
                ):

                    segment_text = clean_instruction_text(
                        segment.get(
                            "text"
                        )
                    )

                else:

                    segment_text = clean_instruction_text(
                        segment
                    )


                if segment_text:

                    texts.append(
                        segment_text
                    )


            if texts:

                return " ".join(
                    texts
                )


        for nested_value in value.values():

            if isinstance(
                nested_value,
                (dict, list, tuple)
            ):

                extracted = extract_text_from_structure(
                    nested_value,
                    preferred_keys=
                        preferred_keys
                )


                if extracted:

                    return extracted


        return ""


    if isinstance(
        value,
        (list, tuple)
    ):

        candidates = []


        for item in value:

            extracted = extract_text_from_structure(
                item,
                preferred_keys=
                    preferred_keys
            )


            if extracted:

                candidates.append(
                    extracted
                )


        if candidates:

            operation_words = (
                "chamfer",
                "fillet",
                "hole",
                "add",
                "create",
                "remove",
                "move",
                "cut"
            )


            for candidate in candidates:

                lower = candidate.lower()


                if any(
                    word in lower
                    for word in operation_words
                ):

                    return candidate


            return candidates[0]


    return ""


def parse_transcript(value):

    """
    Extract clean instruction from request_transcript.

    Some Autodesk/neuralCAD rows contain a missing/null transcript.
    In that case this function returns an empty string instead of failing.
    The caller can then use request-event / row-column fallbacks.
    """

    if is_missing_value(
        value
    ):

        return ""


    if isinstance(
        value,
        dict
    ):

        data = value


    elif isinstance(
        value,
        str
    ):

        text = value.strip()


        if not text:

            return ""


        try:

            data = json.loads(
                text
            )

        except Exception:

            return text


    else:

        return extract_text_from_structure(
            value
        )


    if data is None:

        return ""


    if isinstance(
        data,
        dict
    ):

        segments = data.get(
            "segments",
            []
        )


        if isinstance(
            segments,
            (list, tuple)
        ):

            texts = []


            for segment in segments:

                if isinstance(
                    segment,
                    dict
                ):

                    segment_text = clean_instruction_text(
                        segment.get(
                            "text",
                            ""
                        )
                    )

                else:

                    segment_text = clean_instruction_text(
                        segment
                    )


                if segment_text:

                    texts.append(
                        segment_text
                    )


            if texts:

                return " ".join(
                    texts
                )


    return extract_text_from_structure(
        data
    )


def resolve_instruction(
    row,
    events
):

    """
    Resolve the engineering instruction without using Ground Truth.

    Priority:
        1. request_transcript
        2. explicit instruction/prompt/text columns in the parquet row
        3. request_events content

    Returns:
        (instruction, source_name)
    """

    instruction = parse_transcript(
        row.get(
            "request_transcript"
        )
    )


    if instruction:

        return (
            instruction,
            "request_transcript"
        )


    candidate_columns = [
        "instruction",
        "request_instruction",
        "edit_instruction",
        "prompt",
        "request_text",
        "text",
        "description",
        "request_prompt"
    ]


    for column in candidate_columns:

        if column not in row.index:

            continue


        candidate = extract_text_from_structure(
            row.get(
                column
            )
        )


        if candidate:

            return (
                candidate,
                f"row.{column}"
            )


    candidate = extract_text_from_structure(
        events
    )


    if candidate:

        return (
            candidate,
            "request_events"
        )


    available_columns = [
        str(column)
        for column in row.index
    ]


    raise RuntimeError(
        "Could not resolve engineering instruction for this request.\n"
        "request_transcript is missing/empty and no usable instruction "
        "was found in fallback row fields or request_events.\n\n"
        "Available parquet columns:\n"
        + ", ".join(
            available_columns
        )
    )


def parse_events(value):

    if value is None:

        return []


    if isinstance(
        value,
        list
    ):

        return value


    if isinstance(
        value,
        str
    ):

        text = value.strip()


        if not text:

            return []


        try:

            data = json.loads(
                text
            )

            if isinstance(
                data,
                list
            ):

                return data

        except Exception:

            pass


    return []


# ============================================================
# VALUE EXTRACTION
# ============================================================

def extract_mm_value(text):

    """
    Extract a dimensional value expressed in millimetres.

    Supported examples:
        2 mm
        2mm
        2.0 mm
        0.5 mm
        2 millimeter
        2 millimeters
        2 millimetre
        2 millimetres
    """

    if text is None:
        raise RuntimeError(
            "Cannot extract mm value from None."
        )

    text = str(text).strip()

    patterns = [
        # Abbreviation: 2 mm, 2mm, 2.5 mm
        r"(\d+(?:\.\d+)?)\s*mm\b",

        # American English:
        # 2 millimeter / 2 millimeters
        r"(\d+(?:\.\d+)?)\s*millimeters?\b",

        # British English:
        # 2 millimetre / 2 millimetres
        r"(\d+(?:\.\d+)?)\s*millimetres?\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:

            value = float(
                match.group(1)
            )

            print(
                "Parsed dimension:",
                value,
                "mm"
            )

            return value

    raise RuntimeError(
        "Could not extract millimetre value "
        "from instruction:\n"
        + text
    )



def extract_all_mm_values(text):

    """
    Extract all dimensional values expressed in millimetres
    in their order of appearance.

    Supported:
        2 mm
        1 mm
        2 millimetre
        1 millimetres
        2 millimeter
        1 millimeters
    """

    if text is None:
        return []

    text = str(text)

    pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s*"
        r"(?:mm\b|millimeters?\b|millimetres?\b)",
        flags=re.IGNORECASE
    )

    return [
        float(match.group(1))
        for match in pattern.finditer(text)
    ]


def parse_fillet_groups(instruction):

    """
    Detect compound FILLET instructions with multiple radii.

    Example:
        'fillet of 2 mm to the four outer edges and
         fillet of 1 mm to all the four inner edges'

    Returns:
        [] for a normal single-radius FILLET,
        otherwise a list of group descriptors.
    """

    text = str(instruction)
    lower = text.lower()

    if lower.count("fillet") < 2:
        return []

    values = extract_all_mm_values(text)

    if len(values) < 2:
        return []

    groups = []

    # Preserve textual order. For B07 this yields:
    # group 1 -> 2 mm, group 2 -> 1 mm.
    for index, value in enumerate(values, start=1):

        if index == 1 and "outer" in lower:
            label = "OUTER_EDGES"

        elif index == 2 and "inner" in lower:
            label = "INNER_EDGES"

        else:
            label = f"FILLET_GROUP_{index}"

        groups.append({
            "group_index": index,
            "label": label,
            "radius_mm": float(value)
        })

    return groups


# ============================================================
# TEXT -> ENGINEERING INTENT
# ============================================================

def parse_engineering_instruction(
    instruction
):

    """
    WHAT + PARAMETER are extracted from text.

    WHERE is NOT inferred here.

    WHERE will be supplied through the 3D viewer.
    """

    text = instruction.lower()


    # ========================================================
    # CHAMFER
    # ========================================================

    if "chamfer" in text:

        mm_values = extract_all_mm_values(
            instruction
        )

        reference_phrases = (
            "same size as",
            "same chamfer as",
            "match the chamfer",
            "matching the chamfer",
            "same as present",
            "same as existing",
            "same size of"
        )

        uses_reference_geometry = any(
            phrase in text
            for phrase in reference_phrases
        )

        if uses_reference_geometry and not mm_values:

            return {

                "operation":
                    "CHAMFER",

                "parameters": {

                    "distance_source":
                        "REFERENCE_GEOMETRY"
                },

                "selection_mode":
                    "REFERENCE_AND_TARGET_EDGE",

                "entity_type":
                    "REFERENCE_TARGET_EDGES",

                "target_semantics":
                    "COPY_EXISTING_CHAMFER_SIZE_TO_TARGET_EDGE"
            }

        distance_mm = extract_mm_value(
            instruction
        )

        if (
            "both sides" in text
            or
            "from both sides" in text
        ):

            semantics = (
                "BOTH_SIDES_OF_TARGET_HOLE"
            )

        else:

            semantics = (
                "USER_SELECTED_EDGES"
            )

        return {

            "operation":
                "CHAMFER",

            "parameters": {

                "distance_mm":
                    distance_mm,

                "distance_source":
                    "TEXT"
            },

            "selection_mode":
                "MULTI_EDGE",

            "entity_type":
                "EDGES",

            "target_semantics":
                semantics
        }


    # ========================================================
    # FILLET
    # ========================================================

    if "fillet" in text:

        fillet_groups = parse_fillet_groups(
            instruction
        )

        if fillet_groups:

            return {

                "operation":
                    "FILLET",

                "parameters": {

                    "radius_mm":
                        fillet_groups[0][
                            "radius_mm"
                        ],

                    "fillet_groups":
                        fillet_groups
                },

                "selection_mode":
                    "MULTI_EDGE_GROUPS",

                "entity_type":
                    "EDGE_GROUPS",

                "target_semantics":
                    "USER_SELECTED_FILLET_GROUPS"
            }

        radius_mm = extract_mm_value(
            instruction
        )

        return {

            "operation":
                "FILLET",

            "parameters": {

                "radius_mm":
                    radius_mm
            },

            "selection_mode":
                "MULTI_EDGE",

            "entity_type":
                "EDGES",

            "target_semantics":
                "USER_SELECTED_EDGES"
        }


    # ========================================================
    # ADD HOLE
    # ========================================================

    if (
        "hole" in text
        and
        (
            "add" in text
            or
            "create" in text
        )
    ):

        mm_values = extract_all_mm_values(
            instruction
        )

        # ----------------------------------------------------
        # REFERENCE-BASED HOLE / B09
        #
        # Example:
        # "add one more hole which would have the same setup
        #  as these two holes, ... in the middle between ..."
        #
        # No diameter is taken from text. Two existing holes
        # are selected and Module 2 derives geometry from them.
        # ----------------------------------------------------

        reference_hole_phrases = (
            "same setup as these two holes",
            "same setup as the two holes",
            "same as these two holes",
            "same as the two holes",
            "middle between this hole and this hole",
            "in the middle between",
            "middle between",
            "midway between",
            "between this hole and this hole"
        )

        uses_reference_holes = any(
            phrase in text
            for phrase in reference_hole_phrases
        )

        if (
            uses_reference_holes
            and
            not mm_values
        ):

            return {

                "operation":
                    "ADD_HOLE",

                "parameters": {

                    "geometry_source":
                        "REFERENCE_HOLES",

                    "position_rule":
                        "MIDPOINT",

                    "setup_rule":
                        "COPY_EXISTING_HOLE_SETUP"
                },

                "selection_mode":
                    "REFERENCE_HOLE_PAIR",

                "entity_type":
                    "REFERENCE_HOLE_EDGES",

                "target_semantics":
                    "MIDPOINT_BETWEEN_REFERENCE_HOLES"
            }

        # ----------------------------------------------------
        # LEGACY EXPLICIT-DIAMETER ADD_HOLE
        # Keeps B04/B05-style behavior unchanged.
        # ----------------------------------------------------

        diameter_mm = extract_mm_value(
            instruction
        )

        return {

            "operation":
                "ADD_HOLE",

            "parameters": {

                "diameter_mm":
                    diameter_mm,

                "geometry_source":
                    "TEXT"
            },

            "selection_mode":
                "POINT",

            "entity_type":
                "FACE_POINT",

            "target_semantics":
                "USER_SELECTED_POINT_ON_FACE"
        }


    raise NotImplementedError(
        "Unsupported instruction:\n"
        + instruction
    )


# ============================================================
# MAIN MODULE FUNCTION
# ============================================================

def run_input_viewer(
    config,
    project_root
):

    header(
        "MODULE 1 — INPUT DATA + GEOMETRIC GROUNDING"
    )


    # ========================================================
    # CONFIG
    # ========================================================

    experiment_id = str(
        config[
            "experiment_id"
        ]
    ).strip()


    request_id = str(
        config[
            "request_id"
        ]
    ).strip()


    parquet_relative = (
        config[
            "dataset"
        ][
            "parquet"
        ]
    )


    parquet_path = os.path.normpath(

        os.path.join(
            project_root,
            parquet_relative
        )
    )


    print(
        "Experiment:",
        experiment_id
    )

    print(
        "Request:",
        request_id
    )


    # ========================================================
    # READ DATASET
    # ========================================================

    header(
        "READ DATASET"
    )


    print(
        "Parquet:"
    )

    print(
        parquet_path
    )


    if not os.path.exists(
        parquet_path
    ):

        raise FileNotFoundError(
            parquet_path
        )


    df = pd.read_parquet(
        parquet_path
    )


    matches = df[
        df[
            "request"
        ].astype(
            str
        ) == request_id
    ]


    if len(matches) == 0:

        raise RuntimeError(
            "Request ID not found:\n"
            + request_id
        )


    if len(matches) > 1:

        raise RuntimeError(
            "Request ID is not unique."
        )


    dataset_index = matches.index[0]

    row = matches.iloc[0]


    # ========================================================
    # RESOLVE DATA
    # ========================================================

    file_name = str(
        row.get(
            "file_name"
        )
    )


    request_type = str(
        row.get(
            "request_type"
        )
    )


    events = parse_events(
        row.get(
            "request_events"
        )
    )


    instruction, instruction_source = (
        resolve_instruction(
            row,
            events
        )
    )


    brep_relative = parse_brep_start_path(
        row.get(
            "brep_start_path"
        )
    )


    video_relative = row.get(
        "request_video_30fps_720p_audio"
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


    source_step = os.path.normpath(

        os.path.join(
            dataset_root,
            brep_relative
        )
    )


    video_path = None


    if isinstance(
        video_relative,
        str
    ):

        video_relative = (
            video_relative.strip()
        )


        if video_relative:

            video_path = os.path.normpath(

                os.path.join(
                    dataset_root,
                    video_relative
                )
            )


    # ========================================================
    # REPORT ORIGINAL INPUT
    # ========================================================

    header(
        "ORIGINAL REQUEST"
    )


    print(
        "Dataset index:",
        dataset_index
    )


    print(
        "\nFile name:"
    )

    print(
        file_name
    )


    print(
        "\nInstruction:"
    )

    print(
        instruction
    )


    print(
        "Instruction source:",
        instruction_source
    )


    print(
        "\nSTART STEP:"
    )

    print(
        source_step
    )


    print(
        "Exists:",
        os.path.exists(
            source_step
        )
    )


    print(
        "\nVideo:"
    )

    print(
        video_path
    )


    print(
        "\nRequest events:",
        len(
            events
        )
    )


    if not os.path.exists(
        source_step
    ):

        raise FileNotFoundError(
            source_step
        )


    # ========================================================
    # EXPERIMENT PATHS
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


    os.makedirs(
        input_dir,
        exist_ok=True
    )


    local_step = os.path.join(
        input_dir,
        f"{experiment_id}_start.step"
    )


    resolved_input_path = os.path.join(
        input_dir,
        "resolved_input.json"
    )


    edit_request_path = os.path.join(
        input_dir,
        "edit_request.json"
    )


    # ========================================================
    # COPY START STEP
    # ========================================================

    shutil.copy2(
        source_step,
        local_step
    )


    # ========================================================
    # SAVE RESOLVED INPUT
    # ========================================================

    resolved_input = {

        "experiment_id":
            experiment_id,

        "dataset_index":
            int(
                dataset_index
            ),

        "request_id":
            request_id,

        "request_type":
            request_type,

        "file_name":
            file_name,

        "instruction":
            instruction,

        "instruction_source":
            instruction_source,

        "source_start_step":
            source_step,

        "local_start_step":
            local_step,

        "video_path":
            video_path,

        "request_events":
            events,

        "request_event_count":
            len(
                events
            )
    }


    save_json(
        resolved_input,
        resolved_input_path
    )


    # ========================================================
    # PARSE ENGINEERING INTENT
    # ========================================================

    header(
        "TEXT -> ENGINEERING INTENT"
    )


    parsed = parse_engineering_instruction(
        instruction
    )


    operation = parsed[
        "operation"
    ]


    parameters = parsed[
        "parameters"
    ]


    selection_mode = parsed[
        "selection_mode"
    ]


    entity_type = parsed[
        "entity_type"
    ]


    target_semantics = parsed[
        "target_semantics"
    ]


    print(
        "WHAT:"
    )

    print(
        operation
    )


    print(
        "\nPARAMETERS:"
    )

    print(
        parameters
    )


    print(
        "\nWHERE:"
    )

    print(
        "Will be supplied by user in 3D viewer."
    )


    print(
        "\nSelection mode:"
    )

    print(
        selection_mode
    )


    # ========================================================
    # CREATE EDIT REQUEST
    # ========================================================

    target = {

        "entity_type":
            entity_type,

        "selection_semantics":
            target_semantics,

        "source":
            None,

        "selection_count":
            0
    }


    if selection_mode == "MULTI_EDGE":

        target[
            "edge_ids"
        ] = []


    elif selection_mode == "MULTI_EDGE_GROUPS":

        target[
            "edge_groups"
        ] = []


    elif selection_mode == "REFERENCE_AND_TARGET_EDGE":

        target[
            "reference_edge_ids"
        ] = []

        target[
            "edge_ids"
        ] = []


    elif selection_mode == "REFERENCE_HOLE_PAIR":

        target[
            "reference_hole_1_edge_ids"
        ] = []

        target[
            "reference_hole_2_edge_ids"
        ] = []


    elif selection_mode == "POINT":

        target[
            "face_id"
        ] = None

        target[
            "point_xyz"
        ] = []


    edit_request = {

        "experiment_id":
            experiment_id,

        "dataset_index":
            int(
                dataset_index
            ),

        "request_id":
            request_id,

        "instruction":
            instruction,

        "instruction_source":
            instruction_source,

        "operation":
            operation,

        "parameters":
            parameters,

        "target":
            target
    }


    save_json(
        edit_request,
        edit_request_path
    )


    # ========================================================
    # UNIVERSAL VIEWER
    # ========================================================

    header(
        "3D GEOMETRY PICKER"
    )


    repo_root = os.path.join(
        project_root,
        "neuralCAD-Edit"
    )


    if repo_root not in sys.path:

        sys.path.insert(
            0,
            repo_root
        )


    import pyvista as pv


    try:

        pv.set_jupyter_backend(
            "none"
        )

    except Exception:

        pass


    from src.harnesses.geometry_map.geometry_picker import (
        run_geometry_picker
    )


    print(
        "STEP:"
    )

    print(
        local_step
    )


    print(
        "\nOperation:",
        operation
    )


    print(
        "Parameters:",
        parameters
    )


    print(
        "\nSelection mode:",
        selection_mode
    )


    # ========================================================
    # USER INSTRUCTION
    # ========================================================

    if operation == "CHAMFER":

        if selection_mode == "REFERENCE_AND_TARGET_EDGE":

            print(
                "\nThis chamfer uses an existing chamfer as its size reference."
            )

            print(
                "The viewer will open twice:"
            )

            print(
                "1. Select ONE representative edge belonging to the existing "
                "reference chamfer at the top."
            )

            print(
                "2. Select the target lower cylindrical edge where the new "
                "chamfer must be created."
            )

        else:

            print(
                "\nSelect all B-Rep edges forming "
                "the requested chamfer geometry."
            )


    elif operation == "FILLET":

        if selection_mode == "MULTI_EDGE_GROUPS":

            print(
                "\nThis instruction contains multiple fillet radii."
            )

            print(
                "The viewer will open once for each fillet group."
            )

        else:

            print(
                "\nSelect all B-Rep edges "
                "requiring fillet."
            )


    elif operation == "ADD_HOLE":

        if selection_mode == "REFERENCE_HOLE_PAIR":

            print(
                "\nThis instruction uses two existing holes as "
                "geometric references."
            )

            print(
                "The viewer will open twice:"
            )

            print(
                "1. Select ONE circular B-Rep edge of the first "
                "reference hole."
            )

            print(
                "2. Select ONE corresponding circular B-Rep edge "
                "of the second reference hole."
            )

            print(
                "The new hole center and setup will be derived "
                "automatically from those references."
            )

        else:

            print(
                "\nSelect the target point "
                "on the required face."
            )


    # ========================================================
    # RUN VIEWER
    # ========================================================

    if selection_mode == "REFERENCE_HOLE_PAIR":

        picker_result = {
            "finished": True
        }

        selected_reference_holes = []

        # ----------------------------------------------------
        # TWO SEQUENTIAL REFERENCE-HOLE SELECTIONS
        # ----------------------------------------------------

        for hole_index in (
            1,
            2
        ):

            print(
                "\n" + "=" * 78
            )

            print(
                f"REFERENCE HOLE {hole_index} SELECTION"
            )

            print(
                "=" * 78
            )

            print(
                f"Select exactly ONE circular B-Rep edge "
                f"belonging to reference hole {hole_index}, "
                f"then finish the selection."
            )

            temporary_request = {

                "experiment_id":
                    experiment_id,

                "dataset_index":
                    int(
                        dataset_index
                    ),

                "request_id":
                    request_id,

                "instruction":
                    instruction,

                "instruction_source":
                    instruction_source,

                "operation":
                    operation,

                "parameters": {

                    "geometry_source":
                        "REFERENCE_HOLES",

                    "position_rule":
                        "MIDPOINT",

                    "setup_rule":
                        "COPY_EXISTING_HOLE_SETUP"
                },

                "target": {

                    "entity_type":
                        "EDGES",

                    "selection_semantics":
                        f"REFERENCE_HOLE_{hole_index}",

                    "source":
                        None,

                    "selection_count":
                        0,

                    "edge_ids":
                        []
                }
            }

            save_json(
                temporary_request,
                edit_request_path
            )

            hole_picker_result = run_geometry_picker(

                step_file=
                    local_step,

                edit_request_json=
                    edit_request_path,

                mode=
                    "MULTI_EDGE"
            )

            picker_result[
                "finished"
            ] = bool(
                picker_result[
                    "finished"
                ]
                and
                hole_picker_result.get(
                    "finished"
                )
            )

            with open(
                edit_request_path,
                "r",
                encoding="utf-8"
            ) as f:

                selected_request = json.load(
                    f
                )

            selected_edge_ids = (
                selected_request.get(
                    "target",
                    {}
                ).get(
                    "edge_ids",
                    []
                )
            )

            if len(
                selected_edge_ids
            ) != 1:

                raise RuntimeError(
                    f"Reference hole {hole_index} requires "
                    f"exactly ONE selected edge. "
                    f"Selected: {selected_edge_ids}"
                )

            selected_reference_holes.append(
                selected_edge_ids[
                    0
                ]
            )

        # ----------------------------------------------------
        # PREVENT ACCIDENTALLY USING THE SAME EDGE TWICE
        # ----------------------------------------------------

        if (
            selected_reference_holes[
                0
            ]
            ==
            selected_reference_holes[
                1
            ]
        ):

            raise RuntimeError(
                "The two reference holes must be different. "
                "The same B-Rep edge was selected twice."
            )

        # ----------------------------------------------------
        # FINAL B09 REQUEST FOR MODULE 2
        # ----------------------------------------------------

        edit_request = {

            "experiment_id":
                experiment_id,

            "dataset_index":
                int(
                    dataset_index
                ),

            "request_id":
                request_id,

            "instruction":
                instruction,

            "instruction_source":
                instruction_source,

            "operation":
                operation,

            "parameters": {

                "geometry_source":
                    "REFERENCE_HOLES",

                "position_rule":
                    "MIDPOINT",

                "setup_rule":
                    "COPY_EXISTING_HOLE_SETUP"
            },

            "reference": {

                "entity_type":
                    "REFERENCE_HOLE_PAIR",

                "hole_1_edge_ids":
                    [
                        selected_reference_holes[
                            0
                        ]
                    ],

                "hole_2_edge_ids":
                    [
                        selected_reference_holes[
                            1
                        ]
                    ],

                "selection_count":
                    2,

                "source":
                    "USER_3D_SELECTION"
            },

            "target": {

                "entity_type":
                    "DERIVED_HOLE",

                "selection_semantics":
                    "MIDPOINT_BETWEEN_REFERENCE_HOLES",

                "source":
                    "GEOMETRIC_DERIVATION",

                "selection_count":
                    0
            }
        }

        save_json(
            edit_request,
            edit_request_path
        )


    elif selection_mode == "REFERENCE_AND_TARGET_EDGE":

        picker_result = {
            "finished": True
        }

        # ----------------------------------------------------
        # PASS 1: EXISTING CHAMFER REFERENCE
        # ----------------------------------------------------

        print(
            "\n" + "=" * 78
        )

        print(
            "CHAMFER REFERENCE SELECTION"
        )

        print(
            "=" * 78
        )

        print(
            "Select ONE representative B-Rep edge on the EXISTING "
            "top chamfer, then finish the selection."
        )

        reference_request = dict(
            edit_request
        )

        reference_request[
            "target"
        ] = {
            "entity_type":
                "EDGES",

            "selection_semantics":
                "EXISTING_CHAMFER_REFERENCE",

            "source":
                None,

            "selection_count":
                0,

            "edge_ids":
                []
        }

        save_json(
            reference_request,
            edit_request_path
        )

        reference_picker_result = run_geometry_picker(

            step_file=
                local_step,

            edit_request_json=
                edit_request_path,

            mode=
                "MULTI_EDGE"
        )

        picker_result[
            "finished"
        ] = bool(
            picker_result[
                "finished"
            ]
            and
            reference_picker_result.get(
                "finished"
            )
        )

        with open(
            edit_request_path,
            "r",
            encoding="utf-8"
        ) as f:

            selected_reference_request = json.load(
                f
            )

        reference_edge_ids = (
            selected_reference_request.get(
                "target",
                {}
            ).get(
                "edge_ids",
                []
            )
        )

        if not reference_edge_ids:

            raise RuntimeError(
                "No reference chamfer edge was selected."
            )

        # ----------------------------------------------------
        # PASS 2: TARGET EDGE
        # ----------------------------------------------------

        print(
            "\n" + "=" * 78
        )

        print(
            "CHAMFER TARGET SELECTION"
        )

        print(
            "=" * 78
        )

        print(
            "Now select the LOWER cylindrical edge where the new "
            "chamfer must be created, then finish the selection."
        )

        target_request = dict(
            edit_request
        )

        target_request[
            "target"
        ] = {
            "entity_type":
                "EDGES",

            "selection_semantics":
                "USER_SELECTED_TARGET_EDGES",

            "source":
                None,

            "selection_count":
                0,

            "edge_ids":
                []
        }

        save_json(
            target_request,
            edit_request_path
        )

        target_picker_result = run_geometry_picker(

            step_file=
                local_step,

            edit_request_json=
                edit_request_path,

            mode=
                "MULTI_EDGE"
        )

        picker_result[
            "finished"
        ] = bool(
            picker_result[
                "finished"
            ]
            and
            target_picker_result.get(
                "finished"
            )
        )

        with open(
            edit_request_path,
            "r",
            encoding="utf-8"
        ) as f:

            selected_target_request = json.load(
                f
            )

        target_edge_ids = (
            selected_target_request.get(
                "target",
                {}
            ).get(
                "edge_ids",
                []
            )
        )

        if not target_edge_ids:

            raise RuntimeError(
                "No target chamfer edge was selected."
            )

        # Restore the final reference-based request for Module 2.
        edit_request = {

            "experiment_id":
                experiment_id,

            "dataset_index":
                int(
                    dataset_index
                ),

            "request_id":
                request_id,

            "instruction":
                instruction,

            "instruction_source":
                instruction_source,

            "operation":
                operation,

            "parameters": {

                "distance_source":
                    "REFERENCE_GEOMETRY"
            },

            "reference": {

                "entity_type":
                    "EXISTING_CHAMFER_EDGE",

                "edge_ids":
                    reference_edge_ids,

                "selection_count":
                    len(
                        reference_edge_ids
                    ),

                "source":
                    "USER_3D_SELECTION"
            },

            "target": {

                "entity_type":
                    "EDGES",

                "selection_semantics":
                    "USER_SELECTED_TARGET_EDGES",

                "source":
                    "USER_3D_SELECTION",

                "selection_count":
                    len(
                        target_edge_ids
                    ),

                "edge_ids":
                    target_edge_ids
            }
        }

        save_json(
            edit_request,
            edit_request_path
        )


    elif selection_mode == "MULTI_EDGE_GROUPS":

        fillet_groups = parameters.get(
            "fillet_groups",
            []
        )

        consolidated_groups = []

        picker_result = {
            "finished": True
        }

        for group in fillet_groups:

            group_index = int(
                group.get(
                    "group_index"
                )
            )

            group_radius = float(
                group.get(
                    "radius_mm"
                )
            )

            group_label = str(
                group.get(
                    "label",
                    f"FILLET_GROUP_{group_index}"
                )
            )

            print(
                "\n" + "=" * 78
            )

            print(
                f"FILLET SELECTION GROUP {group_index}"
            )

            print(
                "=" * 78
            )

            print(
                "Label:",
                group_label
            )

            print(
                "Radius:",
                group_radius,
                "mm"
            )

            print(
                "Select ONLY the edges for this fillet group, "
                "then finish the selection."
            )

            # Prepare temporary single-group request because the
            # existing geometry_picker understands MULTI_EDGE.
            with open(
                edit_request_path,
                "r",
                encoding="utf-8"
            ) as f:

                group_request = json.load(
                    f
                )

            group_request[
                "parameters"
            ] = {
                "radius_mm":
                    group_radius
            }

            group_request[
                "target"
            ] = {
                "entity_type":
                    "EDGES",

                "selection_semantics":
                    group_label,

                "source":
                    None,

                "selection_count":
                    0,

                "edge_ids":
                    []
            }

            save_json(
                group_request,
                edit_request_path
            )

            group_picker_result = run_geometry_picker(

                step_file=
                    local_step,

                edit_request_json=
                    edit_request_path,

                mode=
                    "MULTI_EDGE"
            )

            picker_result[
                "finished"
            ] = bool(
                picker_result[
                    "finished"
                ]
                and
                group_picker_result.get(
                    "finished"
                )
            )

            with open(
                edit_request_path,
                "r",
                encoding="utf-8"
            ) as f:

                selected_group_request = json.load(
                    f
                )

            selected_target = selected_group_request.get(
                "target",
                {}
            )

            selected_edge_ids = selected_target.get(
                "edge_ids",
                []
            )

            consolidated_groups.append({

                "group_index":
                    group_index,

                "label":
                    group_label,

                "radius_mm":
                    group_radius,

                "edge_ids":
                    selected_edge_ids,

                "selection_count":
                    len(
                        selected_edge_ids
                    ),

                "source":
                    "USER_3D_SELECTION"
            })

        # Restore a compound FILLET request for Module 2.
        edit_request = {

            "experiment_id":
                experiment_id,

            "dataset_index":
                int(
                    dataset_index
                ),

            "request_id":
                request_id,

            "instruction":
                instruction,

            "instruction_source":
                instruction_source,

            "operation":
                operation,

            "parameters": {

                "radius_mm":
                    fillet_groups[0][
                        "radius_mm"
                    ],

                "fillet_groups":
                    fillet_groups
            },

            "target": {

                "entity_type":
                    "EDGE_GROUPS",

                "selection_semantics":
                    "USER_SELECTED_FILLET_GROUPS",

                "source":
                    "USER_3D_SELECTION",

                "selection_count":
                    sum(
                        group[
                            "selection_count"
                        ]
                        for group in consolidated_groups
                    ),

                "edge_groups":
                    consolidated_groups
            }
        }

        save_json(
            edit_request,
            edit_request_path
        )

    else:

        picker_result = run_geometry_picker(

            step_file=
                local_step,

            edit_request_json=
                edit_request_path,

            mode=
                selection_mode
        )


    # ========================================================
    # RESULT
    # ========================================================

    header(
        "MODULE 1 RESULT"
    )


    print(
        "Viewer finished:",
        picker_result.get(
            "finished"
        )
    )


    # Reload saved request.

    with open(
        edit_request_path,
        "r",
        encoding="utf-8"
    ) as f:

        final_request = json.load(f)


    print(
        "\nEdit request:"
    )

    print(
        edit_request_path
    )


    print(
        "\nTarget:"
    )

    print(
        json.dumps(
            final_request.get(
                "target",
                {}
            ),
            indent=4,
            ensure_ascii=False
        )
    )


    print(
        "\nSTART STEP:"
    )

    print(
        local_step
    )


    print(
        "\nResolved input:"
    )

    print(
        resolved_input_path
    )


    return {

        "experiment_id":
            experiment_id,

        "dataset_index":
            int(
                dataset_index
            ),

        "start_step":
            local_step,

        "resolved_input":
            resolved_input_path,

        "edit_request":
            edit_request_path,

        "viewer_finished":
            bool(
                picker_result.get(
                    "finished"
                )
            )
    }


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print(
        "This module should normally be launched "
        "through 1_MAIN.py"
    )