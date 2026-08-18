# ============================================================
# FILE: point_grounding.py
# ASME CIE 2026 STUDENT HACKATHON
#
# COMPONENT:
#     Proposed Hybrid Geometry Map Pipeline
#
# PURPOSE:
#     Resolve the spatial meaning of "HERE" after:
#
#         instruction_grounding.py
#
# has already determined:
#
#         operation
#         engineering parameter
#         exact target B-Rep face
#
# B01 STATUS:
#
#     operation        = ADD_HOLE
#     diameter_mm      = 2.0
#     target_face_id   = F0040
#     exact face match = TRUE
#
# MISSING:
#
#     exact point on F0040
#
# PIPELINE:
#
#     Video
#       ↓
#     frame at selection time
#       ↓
#     visual point / cursor localization
#       ↓
#     screen_point = [u_px, v_px]
#       ↓
#     camera / projection information
#       ↓
#     ray-plane intersection
#       ↓
#     exact STEP target_point [X,Y,Z]
#
# IMPORTANT:
#
#     This file DOES NOT use Ground Truth geometry.
#
#     It also DOES NOT silently assume that the centroid of
#     the selected face is the requested "HERE" point.
#
#     If camera data are unavailable, the result remains
#     SCREEN_GROUNDED_ONLY rather than inventing XYZ.
# ============================================================


import os
import json
import math

import cv2
import numpy as np


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_vector(vector):
    """
    Normalize a three-dimensional vector.
    """

    vector = np.array(
        vector,
        dtype=float
    )

    norm = np.linalg.norm(
        vector
    )

    if norm < 1e-12:
        raise ValueError(
            "Cannot normalize zero-length vector."
        )

    return (
        vector / norm
    )


def save_json(
    data,
    output_json
):
    """
    Save JSON with readable formatting.
    """

    output_json = os.path.abspath(
        output_json
    )

    output_dir = os.path.dirname(
        output_json
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True
        )

    with open(
        output_json,
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
# VIDEO FRAME EXTRACTION
# ============================================================

def get_video_information(
    video_file
):
    """
    Read video metadata.
    """

    video_file = os.path.abspath(
        video_file
    )

    if not os.path.exists(
        video_file
    ):

        raise FileNotFoundError(
            video_file
        )

    cap = cv2.VideoCapture(
        video_file
    )

    if not cap.isOpened():

        raise RuntimeError(
            f"Could not open video: {video_file}"
        )

    fps = float(
        cap.get(
            cv2.CAP_PROP_FPS
        )
    )

    width = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    frame_count = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    duration = (
        frame_count / fps
        if fps > 0
        else None
    )

    cap.release()

    return {
        "fps":
            fps,

        "width":
            width,

        "height":
            height,

        "frame_count":
            frame_count,

        "duration_sec":
            duration
    }


def extract_frame(
    video_file,
    time_sec,
    output_file
):
    """
    Extract one video frame at approximately time_sec.
    """

    video_file = os.path.abspath(
        video_file
    )

    output_file = os.path.abspath(
        output_file
    )

    cap = cv2.VideoCapture(
        video_file
    )

    if not cap.isOpened():

        raise RuntimeError(
            f"Could not open video: {video_file}"
        )

    cap.set(
        cv2.CAP_PROP_POS_MSEC,
        float(time_sec) * 1000.0
    )

    success, frame = cap.read()

    cap.release()

    if not success:

        raise RuntimeError(
            f"Could not read frame at {time_sec:.6f} s."
        )

    output_dir = os.path.dirname(
        output_file
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True
        )

    success = cv2.imwrite(
        output_file,
        frame
    )

    if not success:

        raise RuntimeError(
            f"Could not save frame: {output_file}"
        )

    return {
        "time_sec":
            float(time_sec),

        "frame_path":
            output_file,

        "height":
            int(frame.shape[0]),

        "width":
            int(frame.shape[1])
    }


def extract_grounding_frames(
    video_file,
    event_time,
    output_dir,
    offsets=None
):
    """
    Extract frames around the Fusion selection event.

    Default:
        -0.40
        -0.20
         0.00
        +0.20
        +0.40 seconds
    """

    if offsets is None:

        offsets = [
            -0.40,
            -0.20,
            0.00,
            0.20,
            0.40
        ]

    output_dir = os.path.abspath(
        output_dir
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    frames = []

    for offset in offsets:

        time_sec = (
            float(event_time)
            + float(offset)
        )

        if time_sec < 0:

            continue

        filename = (
            f"frame_{time_sec:.3f}s.png"
        )

        output_file = os.path.join(
            output_dir,
            filename
        )

        frame_info = extract_frame(
            video_file=
                video_file,

            time_sec=
                time_sec,

            output_file=
                output_file
        )

        frame_info[
            "offset_from_event_sec"
        ] = float(
            offset
        )

        frames.append(
            frame_info
        )

    return frames


# ============================================================
# BUILD VISUAL GROUNDING REQUEST
# ============================================================

def build_visual_grounding_request(
    instruction,
    grounding,
    video_file,
    event_time,
    frames
):
    """
    Create a structured description of the visual point
    grounding problem.

    This structure can later be sent to a VLM or another
    visual-point detector.

    The visual model should NOT generate CAD geometry.

    It only needs to answer:

        Where on the selected target face does "HERE" refer?
    """

    return {
        "task":
            "VISUAL_POINT_GROUNDING",

        "instruction":
            instruction,

        "target_face_id":
            grounding.get(
                "target_face_id"
            ),

        "target_surface_type":
            grounding.get(
                "target_surface_type"
            ),

        "known_step_face_center":
            grounding.get(
                "matched_face_details",
                {}
            ).get(
                "step_face_center"
            ),

        "selection_event_time_sec":
            float(
                event_time
            ),

        "video_file":
            os.path.abspath(
                video_file
            ),

        "frames":
            frames,

        "required_visual_output": {

            "screen_x_px":
                "horizontal cursor/indication pixel coordinate",

            "screen_y_px":
                "vertical cursor/indication pixel coordinate",

            "frame_time_sec":
                "frame on which the point is determined",

            "confidence":
                "0..1",

            "evidence":
                "brief description of visual evidence"
        },

        "constraint":
            (
                "The visual stage only identifies the user-indicated "
                "screen location. It must not generate or modify CAD geometry."
            )
    }


# ============================================================
# SCREEN-POINT VALIDATION
# ============================================================

def validate_screen_point(
    screen_point,
    image_width,
    image_height
):
    """
    Validate a screen-space grounding point.
    """

    if screen_point is None:

        raise ValueError(
            "screen_point is required."
        )

    if len(screen_point) != 2:

        raise ValueError(
            "screen_point must be [x_px, y_px]."
        )

    x = float(
        screen_point[0]
    )

    y = float(
        screen_point[1]
    )

    if (
        x < 0
        or x >= image_width
        or y < 0
        or y >= image_height
    ):

        raise ValueError(
            f"Screen point {screen_point} lies outside "
            f"{image_width} x {image_height} image."
        )

    return [
        x,
        y
    ]


# ============================================================
# CAMERA MODEL
# ============================================================

def build_camera_ray(
    screen_point,
    camera
):
    """
    Convert screen pixel to a 3D ray.

    Required camera dictionary:

        {
            "intrinsic_matrix": [[fx,0,cx],
                                 [0,fy,cy],
                                 [0,0,1]],

            "camera_to_world_rotation": [[...],[...],[...]],

            "camera_position": [x,y,z]
        }

    Returns:
        ray_origin
        ray_direction
    """

    if camera is None:

        raise ValueError(
            "Camera calibration is required for pixel -> 3D."
        )

    K = np.array(
        camera[
            "intrinsic_matrix"
        ],
        dtype=float
    )

    R_cw = np.array(
        camera[
            "camera_to_world_rotation"
        ],
        dtype=float
    )

    camera_position = np.array(
        camera[
            "camera_position"
        ],
        dtype=float
    )

    x_px = float(
        screen_point[0]
    )

    y_px = float(
        screen_point[1]
    )

    pixel = np.array(
        [
            x_px,
            y_px,
            1.0
        ],
        dtype=float
    )

    camera_ray = (
        np.linalg.inv(K)
        @ pixel
    )

    camera_ray = normalize_vector(
        camera_ray
    )

    world_ray = (
        R_cw
        @ camera_ray
    )

    world_ray = normalize_vector(
        world_ray
    )

    return (
        camera_position,
        world_ray
    )


# ============================================================
# RAY / PLANE INTERSECTION
# ============================================================

def ray_plane_intersection(
    ray_origin,
    ray_direction,
    plane_point,
    plane_normal
):
    """
    Intersect 3D ray with target planar face plane.
    """

    ray_origin = np.array(
        ray_origin,
        dtype=float
    )

    ray_direction = normalize_vector(
        ray_direction
    )

    plane_point = np.array(
        plane_point,
        dtype=float
    )

    plane_normal = normalize_vector(
        plane_normal
    )

    denominator = float(
        np.dot(
            plane_normal,
            ray_direction
        )
    )

    if abs(
        denominator
    ) < 1e-10:

        raise RuntimeError(
            "Camera ray is parallel to target plane."
        )

    t = float(
        np.dot(
            plane_point - ray_origin,
            plane_normal
        )
        / denominator
    )

    if t < 0:

        raise RuntimeError(
            "Target plane intersection lies behind camera."
        )

    point = (
        ray_origin
        + t * ray_direction
    )

    return point


# ============================================================
# SCREEN POINT -> STEP POINT
# ============================================================

def screen_point_to_step_point(
    screen_point,
    camera,
    target_plane_point,
    target_plane_normal
):
    """
    Convert visual point grounding result into exact
    STEP coordinates through ray-plane intersection.

    This requires camera calibration/view information.
    """

    ray_origin, ray_direction = (
        build_camera_ray(
            screen_point,
            camera
        )
    )

    point = ray_plane_intersection(
        ray_origin=
            ray_origin,

        ray_direction=
            ray_direction,

        plane_point=
            target_plane_point,

        plane_normal=
            target_plane_normal
    )

    return point.tolist()


# ============================================================
# DIRECT 3D TARGET VALIDATION
# ============================================================

def validate_explicit_step_point(
    step_point,
    plane_point,
    plane_normal,
    tolerance_mm=1e-4
):
    """
    Validate an externally obtained 3D point by checking that
    it lies on the already grounded target plane.

    This may later be used by a CAD-native point picker.
    """

    point = np.array(
        step_point,
        dtype=float
    )

    plane_point = np.array(
        plane_point,
        dtype=float
    )

    plane_normal = normalize_vector(
        plane_normal
    )

    signed_distance = float(
        np.dot(
            point - plane_point,
            plane_normal
        )
    )

    valid = (
        abs(
            signed_distance
        )
        <= float(
            tolerance_mm
        )
    )

    projected = (
        point
        - signed_distance
        * plane_normal
    )

    return {
        "valid":
            bool(
                valid
            ),

        "plane_error_mm":
            abs(
                signed_distance
            ),

        "projected_point":
            projected.tolist()
    }


# ============================================================
# CREATE POINT GROUNDING RESULT
# ============================================================

def build_point_grounding_result(
    target_face_id,
    screen_point=None,
    frame_time_sec=None,
    confidence=None,
    evidence=None,
    step_point=None,
    target_plane_point=None,
    target_plane_normal=None,
    camera=None,
    image_width=None,
    image_height=None
):
    """
    Build unified point-grounding result.

    Possible states:

        SCREEN_GROUNDED_ONLY
            screen point known, camera unavailable.

        STEP_POINT_RESOLVED
            exact STEP point successfully computed.

        STEP_POINT_EXPLICIT
            exact 3D point supplied by another geometric
            grounding method and validated on target plane.
    """

    result = {
        "target_face_id":
            target_face_id,

        "screen_point":
            None,

        "frame_time_sec":
            frame_time_sec,

        "confidence":
            confidence,

        "evidence":
            evidence,

        "target_point":
            None,

        "status":
            "UNRESOLVED"
    }


    # ========================================================
    # EXPLICIT STEP POINT
    # ========================================================

    if step_point is not None:

        if (
            target_plane_point is None
            or target_plane_normal is None
        ):

            raise ValueError(
                "Plane geometry required to validate STEP point."
            )

        validation = (
            validate_explicit_step_point(
                step_point=
                    step_point,

                plane_point=
                    target_plane_point,

                plane_normal=
                    target_plane_normal
            )
        )

        result[
            "target_point"
        ] = validation[
            "projected_point"
        ]

        result[
            "plane_validation"
        ] = validation

        result[
            "status"
        ] = "STEP_POINT_EXPLICIT"

        return result


    # ========================================================
    # SCREEN POINT
    # ========================================================

    if screen_point is not None:

        if (
            image_width is None
            or image_height is None
        ):

            raise ValueError(
                "Image dimensions required for screen point."
            )

        screen_point = (
            validate_screen_point(
                screen_point,
                image_width,
                image_height
            )
        )

        result[
            "screen_point"
        ] = screen_point


        # ----------------------------------------------------
        # CAMERA AVAILABLE
        # ----------------------------------------------------

        if camera is not None:

            if (
                target_plane_point is None
                or target_plane_normal is None
            ):

                raise ValueError(
                    "Target plane geometry required "
                    "for ray-plane intersection."
                )

            target_point = (
                screen_point_to_step_point(
                    screen_point=
                        screen_point,

                    camera=
                        camera,

                    target_plane_point=
                        target_plane_point,

                    target_plane_normal=
                        target_plane_normal
                )
            )

            result[
                "target_point"
            ] = target_point

            result[
                "status"
            ] = "STEP_POINT_RESOLVED"


        # ----------------------------------------------------
        # NO CAMERA
        # ----------------------------------------------------

        else:

            result[
                "status"
            ] = "SCREEN_GROUNDED_ONLY"

            result[
                "resolution_note"
            ] = (
                "Screen location is available, but STEP XYZ "
                "cannot be computed without the CAD camera/view "
                "projection."
            )


    return result


# ============================================================
# COMPLETE PREPARATION PIPELINE
# ============================================================

def prepare_point_grounding(
    instruction,
    grounding,
    video_file,
    event_time,
    output_dir
):
    """
    Prepare all visual materials required for point grounding.

    Does NOT guess target XYZ.
    """

    video_info = get_video_information(
        video_file
    )

    frames_dir = os.path.join(
        output_dir,
        "frames"
    )

    frames = extract_grounding_frames(
        video_file=
            video_file,

        event_time=
            event_time,

        output_dir=
            frames_dir
    )

    request = build_visual_grounding_request(
        instruction=
            instruction,

        grounding=
            grounding,

        video_file=
            video_file,

        event_time=
            event_time,

        frames=
            frames
    )

    request[
        "video_info"
    ] = video_info

    output_json = os.path.join(
        output_dir,
        "point_grounding_request.json"
    )

    save_json(
        request,
        output_json
    )

    return request


# ============================================================
# SAVE FINAL POINT GROUNDING
# ============================================================

def save_point_grounding_result(
    result,
    output_json
):
    """
    Save point_grounding.json.
    """

    save_json(
        result,
        output_json
    )