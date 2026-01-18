"""
VisionService - Advanced face detection and tracking using Google MediaPipe
Integrates Face Mesh, Hand Tracking, and LiveKit publishing.
"""

import cv2
import threading
import time
import os
import asyncio
import logging
import numpy as np
from typing import Optional, Dict, Callable, Union, List
from dataclasses import dataclass

# --- Attempt to import MediaPipe ---
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    mp = None


# --- Data Structure Definition ---

@dataclass
class FaceData:
    """
    Enhanced face data (Compatible with MediaPipe and Legacy)
    Includes 3D head pose and normalized position.
    """
    detected: bool
    position: tuple  # (x, y) normalized -1.0 to 1.0 (face center)
    size: float  # 0.0 to 1.0, bigger = closer
    timestamp: float
    head_pose: dict = None # {'pitch': float, 'yaw': float, 'roll': float} in degrees


@dataclass
class HandData:
    """Hand tracking data"""
    detected: bool
    handedness: str       # "Left" or "Right"
    position: tuple       # (x, y) wrist normalized
    gesture: str          # "None", "Pinch", etc.
    fingers_up: list      # [thumb to little finger] (bool/int)
    timestamp: float
    is_pinching: bool = False      # Is pinching
    pinch_distance: float = 0.0    # Normalized pinch distance
    landmarks: List[tuple] = None  # List of (x, y) normalized


class VisionService:
    """
    Unified Vision Service
    - Face detection (MediaPipe FaceMesh with Haar fallback)
    - Hand tracking & Gesture recognition
    - Head pose estimation
    - Motor tracking control
    - LiveKit image publishing
    """

    def __init__(
            self,
            camera_index: Union[int, str] = 0,
            resolution: tuple = (320, 240),
            fps: int = 20, # Increased FPS for smoother MP tracking
            publish_video: bool = False,
            publish_image: bool = False,
            image_fps: float = 1.0,
            max_frame_size: int = 512,
            min_detection_confidence: float = 0.5,
            min_tracking_confidence: float = 0.5
    ):
        self.camera_index = camera_index
        self.resolution = resolution
        self.fps = fps
        self.logger = logging.getLogger("service.VisionService")

        # Camera state
        self.cap = None
        self._camera_thread = None
        self._running = False
        self._video_frame_count = 0

        # --- LiveKit Publishing State ---
        self.publish_image = publish_image
        self.image_fps = image_fps
        self.max_frame_size = max_frame_size
        self._image_callback: Optional[Callable] = None
        self._last_image_time = 0.0
        self._image_frame_count = 0

        # --- MediaPipe Initialization ---
        self.use_mediapipe = MEDIAPIPE_AVAILABLE
        self.mp_face_mesh = None
        self.face_mesh = None
        self.mp_hands = None
        self.hands = None

        if self.use_mediapipe:
            self.logger.info("Initializing MediaPipe solutions...")
            self.mp_face_mesh = mp.solutions.face_mesh
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence
            )
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                max_num_hands=1,
                model_complexity=0, # 0=Lite, 1=Full
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence
            )
        else:
            self.logger.warning("MediaPipe not available. Falling back to Haar Cascade.")
            cascade_path = os.path.join(os.path.dirname(__file__), 'haarcascade_frontalface_default.xml')
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            if self.face_cascade.empty():
                self.logger.error(f"Failed to load face cascade from {cascade_path}")

        # --- Data & Locks ---
        self.latest_face_data: Optional[FaceData] = None
        self.latest_hand_data: Optional[HandData] = None
        self._face_lock = threading.Lock()
        self._hand_lock = threading.Lock()

        # --- Callbacks & Modes ---
        # Face Tracking (Generic)
        self._tracking_mode = False
        self._tracking_callback: Optional[Callable[[FaceData], None]] = None
        self._tracking_lock = threading.Lock()

        # Hand Tracking
        self._hand_callback: Optional[Callable[[HandData], None]] = None

        # Motor Control Direct Tracking
        self._motor_tracking_enabled = False
        self._motor_tracking_callback: Optional[Callable[[float, float, bool], None]] = None

        # Logic: First Face Detection Sound
        self._face_detected_once = False
        self._last_face_detected = False

    def start(self):
        """Start vision service"""
        if self._running:
            self.logger.warning("Vision service already running")
            return

        if self._camera_thread and self._camera_thread.is_alive():
            self._camera_thread.join(timeout=2.0)

        self._running = True
        self._camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self._camera_thread.start()
        self.logger.info(f"Vision service started (MediaPipe: {self.use_mediapipe})")

    def stop(self):
        """Stop vision service"""
        self._running = False
        if self._camera_thread:
            self._camera_thread.join(timeout=2.0)
            self._camera_thread = None

        if self.cap:
            self.cap.release()
            self.cap = None

        # Cleanup MediaPipe resources
        if self.use_mediapipe:
            if self.face_mesh: self.face_mesh.close()
            if self.hands: self.hands.close()

        self.logger.info("Vision service stopped")

    def set_image_callback(self, callback: Callable[[bytes], None]):
        """Set callback for periodic LiveKit image frames"""
        self._image_callback = callback
        self.logger.info(f"Image callback registered, fps={self.image_fps}")

    def set_hand_callback(self, callback: Callable[[HandData], None]):
        """Set callback for hand tracking data"""
        self._hand_callback = callback

    def _camera_loop(self):
        """Main camera capture and processing loop"""
        # 1. Open Camera
        if isinstance(self.camera_index, str):
            candidates = [self.camera_index]
        else:
            candidates = [self.camera_index, 0, 1, 2]

        for cam_idx in candidates:
            test_cap = cv2.VideoCapture(cam_idx)
            if test_cap.isOpened():
                ret, _ = test_cap.read()
                if ret:
                    self.logger.info(f"Camera opened at {cam_idx}")
                    self.cap = test_cap
                    break
                test_cap.release()
            else:
                test_cap.release()

        if self.cap is None:
            self.logger.error(f"No camera found! Tried: {candidates}")
            return

        # 2. Set Resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])

        frame_delay = 1.0 / self.fps

        while self._running:
            start_time = time.time()
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            # 3. Publish Image to LiveKit (if enabled)
            self._publish_image_frame(frame)

            face_data = None
            hand_data = None

            # 4. Process Vision (MediaPipe vs Haar)
            if self.use_mediapipe:
                # MediaPipe requires RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # A. Face Mesh
                mp_face_results = self.face_mesh.process(rgb_frame)
                face_data = self._process_mediapipe_faces(mp_face_results, frame.shape)

                # B. Hands
                mp_hand_results = self.hands.process(rgb_frame)
                hand_data = self._process_hand_results(mp_hand_results, frame.shape)

            else:
                # Fallback to Haar Cascade (Gray)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
                face_data = self._process_haar_faces(faces, frame.shape)
                # No hand tracking in fallback mode

            # 5. Update State
            with self._face_lock:
                self.latest_face_data = face_data

            if hand_data:
                with self._hand_lock:
                    self.latest_hand_data = hand_data

            # 6. "First Face Detected" Sound Logic
            if face_data.detected and not self._last_face_detected:
                if not self._face_detected_once:
                    self._face_detected_once = True
                    try:
                        from lelamp.service.theme import get_theme_service, ThemeSound
                        theme = get_theme_service()
                        if theme:
                            theme.play(ThemeSound.FACE_DETECT)
                            self.logger.info("First face detected - played theme sound")
                    except Exception as e:
                        self.logger.warning(f"Could not play face detect sound: {e}")
            self._last_face_detected = face_data.detected

            # 7. Dispatch Callbacks

            # General Face Tracking
            if self._tracking_mode and self._tracking_callback and face_data.detected:
                try:
                    self._tracking_callback(face_data)
                except Exception as e:
                    self.logger.error(f"Error in tracking callback: {e}")

            # Motor Direct Tracking
            if self._motor_tracking_enabled and self._motor_tracking_callback:
                try:
                    self._motor_tracking_callback(face_data.position[0], face_data.position[1], face_data.detected)
                except Exception as e:
                    self.logger.error(f"Error in motor tracking callback: {e}")

            # Hand Tracking
            if self._hand_callback and hand_data and hand_data.detected:
                try:
                    self._hand_callback(hand_data)
                except Exception as e:
                    self.logger.error(f"Error in hand callback: {e}")

            # FPS Control
            processing_time = time.time() - start_time
            sleep_time = max(0, frame_delay - processing_time)
            time.sleep(sleep_time)

    # --- MediaPipe Processing Methods ---

    def _process_mediapipe_faces(self, results, frame_shape) -> FaceData:
        """Process MediaPipe Face Mesh results"""
        if not results.multi_face_landmarks:
            return FaceData(
                detected=False,
                position=(0.0, 0.0),
                size=0.0,
                timestamp=time.time(),
                head_pose={'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
            )

        face_landmarks = results.multi_face_landmarks[0]
        frame_h, frame_w = frame_shape[:2]

        # Nose tip (landmark 1)
        nose = face_landmarks.landmark[1]

        # Normalized position (-1.0 to 1.0)
        pos_x = (nose.x * frame_w - frame_w / 2) / (frame_w / 2)
        pos_y = (nose.y * frame_h - frame_h / 2) / (frame_h / 2)

        # Size estimation (Eye distance)
        left_eye = face_landmarks.landmark[33]
        right_eye = face_landmarks.landmark[263]
        eye_distance = np.sqrt(
            ((left_eye.x - right_eye.x) * frame_w) ** 2 +
            ((left_eye.y - right_eye.y) * frame_h) ** 2
        )
        size = min(1.0, eye_distance / 100.0)

        # Head Pose
        head_pose = self._calculate_head_pose(face_landmarks, frame_w, frame_h)

        return FaceData(
            detected=True,
            position=(pos_x, pos_y),
            size=size,
            timestamp=time.time(),
            head_pose=head_pose
        )

    def _process_hand_results(self, results, frame_shape) -> HandData:
        """Process MediaPipe Hands results"""
        if not results.multi_hand_landmarks:
            return HandData(
                detected=False,
                handedness="None",
                position=(0.0, 0.0),
                gesture="None",
                fingers_up=[0,0,0,0,0],
                timestamp=time.time()
            )

        hand_landmarks = results.multi_hand_landmarks[0]

        # Store all landmarks
        all_landmarks = [(lm.x, lm.y) for lm in hand_landmarks.landmark]

        # Handedness
        handedness_info = "Right" # Default
        if results.multi_handedness:
            handedness_info = results.multi_handedness[0].classification[0].label

        frame_h, frame_w = frame_shape[:2]

        # Wrist position
        wrist = hand_landmarks.landmark[0]
        pos_x = (wrist.x * frame_w - frame_w / 2) / (frame_w / 2)
        pos_y = (wrist.y * frame_h - frame_h / 2) / (frame_h / 2)

        # Fingers
        fingers_up = self._count_fingers(hand_landmarks)

        # Pinch Detection
        thumb_tip = hand_landmarks.landmark[4]
        index_tip = hand_landmarks.landmark[8]

        dx = (thumb_tip.x - index_tip.x) * frame_w
        dy = (thumb_tip.y - index_tip.y) * frame_h
        distance_px = np.sqrt(dx**2 + dy**2)

        PINCH_THRESHOLD_PX = 40
        is_pinching = distance_px < PINCH_THRESHOLD_PX

        gesture = "Pinch" if is_pinching else "None"

        return HandData(
            detected=True,
            handedness=handedness_info,
            position=(pos_x, pos_y),
            gesture=gesture,
            fingers_up=fingers_up,
            timestamp=time.time(),
            is_pinching=is_pinching,
            pinch_distance=distance_px / frame_w,
            landmarks=all_landmarks
        )

    def _count_fingers(self, landmarks):
        """Count fingers up [Thumb, Index, Middle, Ring, Pinky]"""
        fingers = []
        # Thumb (check x distance from pinky mcp vs ip)
        thumb_tip = landmarks.landmark[4]
        thumb_ip = landmarks.landmark[3]
        pinky_mcp = landmarks.landmark[17]

        dist_tip = np.sqrt((thumb_tip.x - pinky_mcp.x)**2 + (thumb_tip.y - pinky_mcp.y)**2)
        dist_ip = np.sqrt((thumb_ip.x - pinky_mcp.x)**2 + (thumb_ip.y - pinky_mcp.y)**2)
        fingers.append(1 if dist_tip > dist_ip else 0)

        # Other 4 fingers (check y vs pip)
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        for tip, pip in zip(tips, pips):
            fingers.append(1 if landmarks.landmark[tip].y < landmarks.landmark[pip].y else 0)

        return fingers

    def _calculate_head_pose(self, landmarks, frame_w, frame_h) -> dict:
        """Calculate Pitch, Yaw, Roll using PnP"""
        # 2D Image Points
        image_points = np.array([
            (landmarks.landmark[1].x * frame_w, landmarks.landmark[1].y * frame_h),    # Nose
            (landmarks.landmark[152].x * frame_w, landmarks.landmark[152].y * frame_h),  # Chin
            (landmarks.landmark[33].x * frame_w, landmarks.landmark[33].y * frame_h),   # Left Eye
            (landmarks.landmark[263].x * frame_w, landmarks.landmark[263].y * frame_h),  # Right Eye
            (landmarks.landmark[61].x * frame_w, landmarks.landmark[61].y * frame_h),   # Left Mouth
            (landmarks.landmark[291].x * frame_w, landmarks.landmark[291].y * frame_h),  # Right Mouth
        ], dtype="double")

        # 3D Model Points
        model_points = np.array([
            (0.0, 0.0, 0.0),
            (0.0, -330.0, -65.0),
            (-225.0, 170.0, -135.0),
            (225.0, 170.0, -135.0),
            (-150.0, -150.0, -125.0),
            (150.0, -150.0, -125.0)
        ])

        focal_length = frame_w
        center = (frame_w / 2, frame_h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype="double")
        dist_coeffs = np.zeros((4, 1))

        success, rotation_vector, translation_vector = cv2.solvePnP(
            model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}

        rotation_mat, _ = cv2.Rodrigues(rotation_vector)
        pose_mat = cv2.hconcat((rotation_mat, translation_vector))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(pose_mat)

        return {
            'pitch': float(euler_angles[0][0]),
            'yaw': float(euler_angles[1][0]),
            'roll': float(euler_angles[2][0])
        }

    # --- Legacy / Fallback Processing ---

    def _process_haar_faces(self, faces, frame_shape) -> FaceData:
        """Legacy processing for Haar Cascade"""
        if len(faces) == 0:
            return FaceData(False, (0.0, 0.0), 0.0, time.time(), {'pitch': 0, 'yaw': 0, 'roll': 0})

        faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces_sorted[0]
        frame_h, frame_w = frame_shape[:2]

        face_center_x = x + w // 2
        face_center_y = y + h // 2
        pos_x = (face_center_x - frame_w // 2) / (frame_w // 2)
        pos_y = (face_center_y - frame_h // 2) / (frame_h // 2)
        size = (w * h) / (frame_w * frame_h)

        return FaceData(
            detected=True,
            position=(pos_x, pos_y),
            size=size,
            timestamp=time.time(),
            head_pose={'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0} # Haar can't do pose
        )

    # --- LiveKit Publishing ---

    async def _setup_livekit_video_publishing(self):
        """Async setup for LiveKit (Placeholder for compatibility)"""
        try:
            self.logger.info("Setting up LiveKit camera publishing...")
            max_wait = 5.0
            elapsed = 0.0
            while elapsed < max_wait:
                if self.cap and self.cap.isOpened():
                    break
                await asyncio.sleep(0.1)
                elapsed += 0.1
            if not self.cap or not self.cap.isOpened():
                self.logger.error("Cannot publish: camera not ready")
        except Exception as e:
            self.logger.error(f"Failed setup: {e}")

    def _publish_image_frame(self, frame):
        """Send base64 JPEG to callback"""
        if not self.publish_image or not self._image_callback:
            return

        current_time = time.time()
        if (current_time - self._last_image_time) < (1.0 / self.image_fps):
            return

        self._last_image_time = current_time

        try:
            import base64
            import io
            from PIL import Image

            # Resize if needed
            height, width = frame.shape[:2]
            if max(width, height) > self.max_frame_size:
                scale = self.max_frame_size / max(width, height)
                frame = cv2.resize(frame, (int(width * scale), int(height * scale)))

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            buffer = io.BytesIO()
            pil_image.save(buffer, format='JPEG', quality=85)

            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            self._image_callback(base64_image)

            self._image_frame_count += 1
            if self._image_frame_count % 50 == 0:
                self.logger.info(f"Published {self._image_frame_count} frames")

        except Exception as e:
            self.logger.error(f"Error publishing image: {e}")

    # --- Public Accessors & Controls ---

    def get_face_data(self) -> Optional[FaceData]:
        with self._face_lock:
            return self.latest_face_data

    def get_hand_data(self) -> Optional[HandData]:
        with self._hand_lock:
            return self.latest_hand_data

    def enable_tracking_mode(self, callback: Callable[[FaceData], None]):
        """Enable face tracking (full data callback)"""
        with self._tracking_lock:
            self._tracking_mode = True
            self._tracking_callback = callback
        self.logger.info("Face tracking mode ENABLED")

    def disable_tracking_mode(self):
        with self._tracking_lock:
            self._tracking_mode = False
            self._tracking_callback = None
        self.logger.info("Face tracking mode DISABLED")

    def enable_motor_tracking(self, callback: Callable[[float, float, bool], None]):
        """Enable simple motor tracking (x, y, detected)"""
        self._motor_tracking_callback = callback
        self._motor_tracking_enabled = True
        self.logger.info("Motor face tracking ENABLED")

    def disable_motor_tracking(self):
        self._motor_tracking_enabled = False
        self._motor_tracking_callback = None
        self.logger.info("Motor face tracking DISABLED")

    def is_tracking_enabled(self) -> bool:
        with self._tracking_lock:
            return self._tracking_mode