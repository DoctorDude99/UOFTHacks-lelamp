"""
Video streaming service for WebUI.

Provides MJPEG video feed with face detection overlay.
"""

import time
import cv2
import numpy as np
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import lelamp.globals as g

router = APIRouter()


def draw_face_overlay(frame: np.ndarray, face_data, show_box: bool = True) -> np.ndarray:
    """Draw face detection overlay on frame."""
    if not face_data or not face_data.detected:
        return frame

    frame_h, frame_w = frame.shape[:2]

    # Convert normalized position to pixel coordinates
    pos_x, pos_y = face_data.position
    center_x = int((pos_x + 1.0) * frame_w / 2)
    center_y = int((pos_y + 1.0) * frame_h / 2)

    # Draw bounding box based on face size
    box_size = int(face_data.size * 200)
    if show_box and box_size > 0:
        x1 = max(0, center_x - box_size // 2)
        y1 = max(0, center_y - box_size // 2)
        x2 = min(frame_w, center_x + box_size // 2)
        y2 = min(frame_h, center_y + box_size // 2)

        # Draw green box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Draw center crosshair
        cv2.circle(frame, (center_x, center_y), 5, (0, 255, 0), -1)
        cv2.line(frame, (center_x - 10, center_y), (center_x + 10, center_y), (0, 255, 0), 2)
        cv2.line(frame, (center_x, center_y - 10), (center_x, center_y + 10), (0, 255, 0), 2)

    # Draw head pose if available
    if hasattr(face_data, "head_pose") and face_data.head_pose:
        pitch = face_data.head_pose["pitch"]
        yaw = face_data.head_pose["yaw"]
        roll = face_data.head_pose["roll"]
        text = f"Y:{yaw:.1f} P:{pitch:.1f} R:{roll:.1f}"
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    return frame


def generate_video_feed(show_box: bool = True):
    """Generate video frames with face detection overlay.
    Uses g.vision_service directly to always get the current service.
    """
    no_camera_frame = None

    while True:
        # Get vision service from globals (updated dynamically)
        vs = g.vision_service

        if not vs or not vs.cap:
            # Return a blank frame if no camera, but keep the stream open
            if no_camera_frame is None:
                blank = np.zeros((240, 320, 3), dtype=np.uint8)
                cv2.putText(blank, "No Camera", (80, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                _, buffer = cv2.imencode(".jpg", blank)
                no_camera_frame = buffer.tobytes()
            yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + no_camera_frame + b"\r\n")
            time.sleep(0.5)  # Check less frequently when no camera
            continue

        ret, frame = vs.cap.read()
        if not ret:
            time.sleep(0.1)
            continue

        # Get face data and draw overlay
        face_data = vs.get_face_data()
        if show_box:
            frame = draw_face_overlay(frame, face_data, show_box=True)

        # Encode frame
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

        time.sleep(0.033)  # ~30fps


@router.get("/video_feed")
async def video_feed(show_box: bool = True):
    """Stream video with face detection overlay (MJPEG)."""
    return StreamingResponse(
        generate_video_feed(show_box=show_box),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
