"""
MediaPipeVisionService - Advanced face detection and tracking using Google MediaPipe
Provides face mesh with 468 landmarks, head pose estimation, and gaze tracking
"""
from typing import Optional, Callable, List
from dataclasses import dataclass
import logging

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    mp = None


@dataclass
class MediaPipeFaceData:
    """Enhanced face data from MediaPipe"""
    detected: bool
    position: tuple  # (x, y) normalized -1.0 to 1.0 (face center)
    size: float  # 0.0 to 1.0, bigger = closer
    head_pose: dict  # {'pitch': float, 'yaw': float, 'roll': float} in degrees
    timestamp: float


@dataclass
class MediaPipeHandData:
    detected: bool
    handedness: str       # "Left" or "Right"
    position: tuple       # (x, y) wrist
    gesture: str          # "None", "Fist", "Open_Palm", "Victory", "Pointer"
    fingers_up: list      # [thumb to little finger] (bool)
    timestamp: float
    is_pinching: bool = False      # Whether pinching
    pinch_distance: float = 0.0    # Pinch distance (0.0 - 1.0), used for analog control
    landmarks: List[tuple] = None


class MediaPipeVisionService:
    """
    Vision service using MediaPipe Face Mesh
    - More accurate face detection than Haar Cascade
    - Works at angles and partial occlusion
    - Provides head pose angles for better motor control
    - Supports face tracking mode with callback
    """

    def __init__(
        self,
        camera_index: int = 0,
        resolution: tuple = (320, 240),
        fps: int = 10,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5
    ):
        if not MEDIAPIPE_AVAILABLE:
            raise RuntimeError(
                "MediaPipe is not installed. Install with: pip install mediapipe\n"
                "Note: Requires Python 3.8-3.12 (not 3.13+)"
            )

        self.camera_index = camera_index
        self.resolution = resolution
        self.fps = fps
        self.logger = logging.getLogger("service.MediaPipeVisionService")

        # Camera
        self.cap = None
        self._camera_thread = None
        self._running = False

        # MediaPipe Face Mesh
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,  # Include iris landmarks
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )

        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=1, # one hand and faster
            model_complexity=0, # 0=fast, 1=accurate
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )

        # Face data
        self.latest_face_data: Optional[MediaPipeFaceData] = None
        self.latest_hand_data: Optional[MediaPipeHandData] = None
        self._face_lock = threading.Lock()
        self._hand_lock = threading.Lock()

        # Tracking mode
        self._tracking_mode = False
        self._tracking_callback: Optional[Callable[[MediaPipeFaceData], None]] = None
        self._hand_callback = None
        self._tracking_lock = threading.Lock()

    def start(self):
        """Start vision service"""
        if self._running:
            self.logger.warning("MediaPipe vision service already running")
            return

        self._running = True
        self._camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self._camera_thread.start()
        self.logger.info("MediaPipe vision service started")

    def stop(self):
        """Stop vision service"""
        self._running = False
        if self._camera_thread:
            self._camera_thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        if self.face_mesh:
            self.face_mesh.close()
        if self.hands:
            self.hands.close()
        self.logger.info("MediaPipe vision service stopped")

    def _camera_loop(self):
        """Main camera capture and processing loop"""
        # Try to open camera
        for cam_idx in [self.camera_index, 0, 1, 2]:
            test_cap = cv2.VideoCapture(cam_idx)
            if test_cap.isOpened():
                ret, _ = test_cap.read()
                if ret:
                    self.logger.info(f"Camera opened at index {cam_idx}")
                    self.cap = test_cap
                    break
                test_cap.release()
            else:
                test_cap.release()

        if self.cap is None:
            self.logger.error("No camera found!")
            return

        # Set resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])

        frame_delay = 1.0 / self.fps

        while self._running:
            ret, frame = self.cap.read()
            self.debug_frame = frame.copy()
            if not ret:
                time.sleep(0.1)
                continue

            # MediaPipe requires RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Process with MediaPipe
            results = self.face_mesh.process(rgb_frame)

            # Extract face data
            face_data = self._process_mediapipe_results(results, frame.shape)

            # Update latest data
            with self._face_lock:
                self.latest_face_data = face_data

            # If tracking mode is enabled, notify callback
            if self._tracking_mode and self._tracking_callback and face_data.detected:
                try:
                    self._tracking_callback(face_data)
                except Exception as e:
                    self.logger.error(f"Error in tracking callback: {e}")

            hand_results = self.hands.process(rgb_frame)
            hand_data = self._process_hand_results(hand_results, frame.shape)

            with self._hand_lock:
                self.latest_hand_data = hand_data

            if self._hand_callback and hand_data.detected:
                self._hand_callback(hand_data)

            time.sleep(frame_delay)

        # Cleanup
        if self.cap:
            self.cap.release()

    def _process_mediapipe_results(self, results, frame_shape) -> MediaPipeFaceData:
        """Process MediaPipe results and extract face data"""
        if not results.multi_face_landmarks:
            return MediaPipeFaceData(
                detected=False,
                position=(0.0, 0.0),
                size=0.0,
                head_pose={'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0},
                timestamp=time.time()
            )

        # Get first face landmarks
        face_landmarks = results.multi_face_landmarks[0]

        frame_h, frame_w = frame_shape[:2]

        # Get nose tip (landmark 1) as face center
        nose = face_landmarks.landmark[1]
        face_center_x = nose.x * frame_w
        face_center_y = nose.y * frame_h

        # Calculate normalized position (-1 to 1)
        pos_x = (face_center_x - frame_w / 2) / (frame_w / 2)
        pos_y = (face_center_y - frame_h / 2) / (frame_h / 2)

        # Calculate face size (distance between eyes as proxy)
        left_eye = face_landmarks.landmark[33]  # Left eye outer corner
        right_eye = face_landmarks.landmark[263]  # Right eye outer corner
        eye_distance = np.sqrt(
            ((left_eye.x - right_eye.x) * frame_w) ** 2 +
            ((left_eye.y - right_eye.y) * frame_h) ** 2
        )
        # Normalize size (typical eye distance is ~60-80 pixels at 320x240)
        size = min(1.0, eye_distance / 100.0)

        # Calculate head pose angles
        head_pose = self._calculate_head_pose(face_landmarks, frame_w, frame_h)

        return MediaPipeFaceData(
            detected=True,
            position=(pos_x, pos_y),
            size=size,
            head_pose=head_pose,
            timestamp=time.time()
        )

    def _process_hand_results(self, results, frame_shape) -> MediaPipeHandData:
        if not results.multi_hand_landmarks:
            return MediaPipeHandData(
                detected=False,
                handedness="None",
                position=(0.0, 0.0),
                gesture="None",
                fingers_up=[0,0,0,0,0],
                timestamp=time.time()
            )

        # Get the first hand
        hand_landmarks = results.multi_hand_landmarks[0]

        # --- New: Extract all 21 points ---
        # We store normalized coordinates (0.0-1.0), convenient for scaling according to image size when drawing
        all_landmarks = []
        for lm in hand_landmarks.landmark:
            all_landmarks.append((lm.x, lm.y))

        # Get left/right hand info (Label: "Left", "Right")
        handedness_info = results.multi_handedness[0].classification[0].label

        frame_h, frame_w = frame_shape[:2]

        # 1. Extract wrist position (Landmark 0)
        wrist = hand_landmarks.landmark[0]
        pos_x = (wrist.x * frame_w - frame_w / 2) / (frame_w / 2)
        pos_y = (wrist.y * frame_h - frame_h / 2) / (frame_h / 2)

        # 2. Determine finger status (straight/bent)
        fingers_up = self._count_fingers(hand_landmarks)

        thumb_tip = hand_landmarks.landmark[4]  # Thumb tip
        index_tip = hand_landmarks.landmark[8]  # Index finger tip

        # Calculate Pixel Distance
        # We use pixel distance instead of normalized distance because pixel distance is more intuitive (e.g. < 40px)
        dx = (thumb_tip.x - index_tip.x) * frame_w
        dy = (thumb_tip.y - index_tip.y) * frame_h
        distance_px = np.sqrt(dx**2 + dy**2)

        # Calculate normalized distance (for analog control, e.g. 0.0~0.2)
        # Here simply divide by screen width as a reference
        norm_distance = distance_px / frame_w

        # Decision threshold: Adjust according to resolution. About 30px at 320x240, about 60px at 640x480
        # Dynamic threshold relative to palm size can also be used, but fixed threshold is simplest and effective
        PINCH_THRESHOLD_PX = 40
        is_pinching = distance_px < PINCH_THRESHOLD_PX# and fingers_up == [1,1,0,0,0]

        gesture = None
        if is_pinching:
            gesture = "Pinch"

        return MediaPipeHandData(
            detected=True,
            handedness=handedness_info,
            position=(pos_x, pos_y),
            gesture=gesture,
            fingers_up=fingers_up,
            timestamp=time.time(),
            landmarks=all_landmarks
        )

    def _count_fingers(self, landmarks):
        """Determine if 5 fingers are straight, return [1,0,1,1,1] format"""
        fingers = []

        # Key point index
        # Thumb: 4, Index: 8, Middle: 12, Ring: 16, Pinky: 20
        # Joint index: Thumb(3), Others(6, 10, 14, 18)

        # 1. Thumb processing (compare x coordinate, because thumb moves laterally)
        # Note: Left and right hand thumb directions are opposite, here makes a simplified generic judgment
        # Better way is to judge based on handedness, here simply judge if fingertip is away from palm center (point 9)
        thumb_tip = landmarks.landmark[4]
        thumb_ip = landmarks.landmark[3]
        pinky_mcp = landmarks.landmark[17]

        # Simple distance judgment: If thumb tip is further from pinky base than thumb joint is from pinky base, it is considered straight
        dist_tip = np.sqrt((thumb_tip.x - pinky_mcp.x)**2 + (thumb_tip.y - pinky_mcp.y)**2)
        dist_ip = np.sqrt((thumb_ip.x - pinky_mcp.x)**2 + (thumb_ip.y - pinky_mcp.y)**2)
        fingers.append(1 if dist_tip > dist_ip else 0)

        # 2. Other four fingers (compare y coordinate, fingertip needs to be above joint)
        # Note: OpenCV coordinate system y-axis is downward, so "above" means y value is smaller
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18] # Proximal interphalangeal joints

        for tip, pip in zip(tips, pips):
            if landmarks.landmark[tip].y < landmarks.landmark[pip].y:
                fingers.append(1)
            else:
                fingers.append(0)

        return fingers

    def _calculate_head_pose(self, landmarks, frame_w, frame_h) -> dict:
        """
        Calculate head pose (pitch, yaw, roll) from facial landmarks
        Uses simplified 6-point model for speed
        """
        # Key points for head pose estimation
        # Nose tip, chin, left eye, right eye, left mouth, right mouth
        image_points = np.array([
            (landmarks.landmark[1].x * frame_w, landmarks.landmark[1].y * frame_h),    # Nose tip
            (landmarks.landmark[152].x * frame_w, landmarks.landmark[152].y * frame_h),  # Chin
            (landmarks.landmark[33].x * frame_w, landmarks.landmark[33].y * frame_h),   # Left eye
            (landmarks.landmark[263].x * frame_w, landmarks.landmark[263].y * frame_h),  # Right eye
            (landmarks.landmark[61].x * frame_w, landmarks.landmark[61].y * frame_h),   # Left mouth
            (landmarks.landmark[291].x * frame_w, landmarks.landmark[291].y * frame_h),  # Right mouth
        ], dtype="double")

        # 3D model points (generic face model)
        model_points = np.array([
            (0.0, 0.0, 0.0),        # Nose tip
            (0.0, -330.0, -65.0),   # Chin
            (-225.0, 170.0, -135.0),# Left eye
            (225.0, 170.0, -135.0), # Right eye
            (-150.0, -150.0, -125.0),# Left mouth
            (150.0, -150.0, -125.0) # Right mouth
        ])

        # Camera internals (approximate for small resolution)
        focal_length = frame_w
        center = (frame_w / 2, frame_h / 2)
        camera_matrix = np.array(
            [[focal_length, 0, center[0]],
             [0, focal_length, center[1]],
             [0, 0, 1]], dtype="double"
        )

        dist_coeffs = np.zeros((4, 1))  # Assuming no lens distortion

        # Solve PnP
        success, rotation_vector, translation_vector = cv2.solvePnP(
            model_points,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}

        # Convert rotation vector to euler angles
        rotation_mat, _ = cv2.Rodrigues(rotation_vector)
        pose_mat = cv2.hconcat((rotation_mat, translation_vector))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(pose_mat)

        pitch = euler_angles[0][0]
        yaw = euler_angles[1][0]
        roll = euler_angles[2][0]

        return {
            'pitch': float(pitch),
            'yaw': float(yaw),
            'roll': float(roll)
        }

    def get_face_data(self) -> Optional[MediaPipeFaceData]:
        """Get latest face tracking data"""
        with self._face_lock:
            return self.latest_face_data

    def get_hand_data(self) -> Optional[MediaPipeHandData]:
        with self._hand_lock:
            return self.latest_hand_data

    def enable_tracking_mode(self, callback: Callable[[MediaPipeFaceData], None]):
        """Enable face tracking mode with callback"""
        with self._tracking_lock:
            self._tracking_mode = True
            self._tracking_callback = callback
        self.logger.info("MediaPipe face tracking mode ENABLED")

    def set_hand_callback(self, callback):
        self._hand_callback = callback

    def disable_tracking_mode(self):
        """Disable face tracking mode"""
        with self._tracking_lock:
            self._tracking_mode = False
            self._tracking_callback = None
        self.logger.info("MediaPipe face tracking mode DISABLED")

    def is_tracking_enabled(self) -> bool:
        """Check if tracking mode is enabled"""
        with self._tracking_lock:
            return self._tracking_mode

if __name__ == "__main__":
    import cv2
    import numpy as np
    import time
    from queue import Queue

    # 假设你的服务代码保存在 vision_service.py 中
    # from vision_service import MediaPipeVisionService, MediaPipeFaceData, MediaPipeHandData

    class VisionVisualizer:
        """Vision Visualizer Class: Responsible for drawing data on images"""
        HAND_CONNECTIONS = [
            (0, 1), (1, 2), (2, 3), (3, 4),           # Thumb
            (0, 5), (5, 6), (6, 7), (7, 8),           # Index
            (0, 9), (9, 10), (10, 11), (11, 12),      # Middle
            (0, 13), (13, 14), (14, 15), (15, 16),    # Ring
            (0, 17), (17, 18), (18, 19), (19, 20),    # Pinky
            (5, 9), (9, 13), (13, 17)                 # Palm lateral connection (optional)
        ]
        @staticmethod
        def draw_hand_skeleton(image, hand_data):
            """Draw beautiful hand skeleton"""
            if not hand_data or not hand_data.detected or not hand_data.landmarks:
                return

            h, w = image.shape[:2]
            points = []

            # 1. Convert normalized coordinates to pixel coordinates
            for lm in hand_data.landmarks:
                px, py = int(lm[0] * w), int(lm[1] * h)
                points.append((px, py))

            # 2. Draw bone connections
            # Change skeleton color based on whether pinching (red when pinching, yellow usually)
            bone_color = (0, 0, 255) if hand_data.is_pinching else (0, 255, 255)

            for start_idx, end_idx in VisionVisualizer.HAND_CONNECTIONS:
                pt1 = points[start_idx]
                pt2 = points[end_idx]
                cv2.line(image, pt1, pt2, bone_color, 2, cv2.LINE_AA)

            # 3. Draw key points (joints)
            for i, (px, py) in enumerate(points):
                # Fingertips (4, 8, 12, 16, 20) draw larger circles
                if i in [4, 8, 12, 16, 20]:
                    radius = 6
                    color = (0, 255, 0) # Green fingertip
                else:
                    radius = 4
                    color = (0, 0, 255) # Red joint

                cv2.circle(image, (px, py), radius, color, -1)
                # Optional: Draw point number for debugging
                # cv2.putText(image, str(i), (px+5, py-5), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255,255,255), 1)

            # 4. Specially mark pinch line (thumb and index finger)
            if hand_data.is_pinching:
                thumb_tip = points[4]
                index_tip = points[8]
                # Draw a conspicuous line connecting two fingers
                cv2.line(image, thumb_tip, index_tip, (255, 0, 255), 4)
                # Draw center point
                cx, cy = (thumb_tip[0] + index_tip[0]) // 2, (thumb_tip[1] + index_tip[1]) // 2
                cv2.circle(image, (cx, cy), 8, (255, 0, 255), -1)

        @staticmethod
        def draw_face_info(image, face_data):
            if not face_data or not face_data.detected:
                return

            h, w = image.shape[:2]
            cx, cy = int((face_data.position[0] + 1) / 2 * w), int((face_data.position[1] + 1) / 2 * h)

            # 1. Draw face center cross
            cv2.line(image, (cx - 20, cy), (cx + 20, cy), (0, 255, 0), 2)
            cv2.line(image, (cx, cy - 20), (cx, cy + 20), (0, 255, 0), 2)

            # 2. Display head pose data (Pitch, Yaw, Roll)
            pose = face_data.head_pose
            text = f"Face: P:{pose['pitch']:.1f} Y:{pose['yaw']:.1f} R:{pose['roll']:.1f}"
            cv2.putText(image, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # 3. Simple pose indicator bar (Yaw - turn head left/right)
            bar_x = 50
            bar_y = 60
            bar_w = 100
            # Draw background bar
            cv2.rectangle(image, (bar_x, bar_y), (bar_x + bar_w, bar_y + 10), (100, 100, 100), -1)
            # Draw cursor (map yaw -45 to 45 degrees)
            yaw_norm = np.clip(pose['yaw'], -45, 45)
            cursor_x = int(bar_x + bar_w/2 + (yaw_norm / 45) * (bar_w/2))
            cv2.circle(image, (cursor_x, bar_y + 5), 5, (0, 255, 255), -1)
            cv2.putText(image, "Yaw", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        @staticmethod
        def draw_hand_info(image, hand_data):
            if not hand_data or not hand_data.detected:
                return

            h, w = image.shape[:2]
            wx, wy = int((hand_data.position[0] + 1) / 2 * w), int((hand_data.position[1] + 1) / 2 * h)

            # 1. Mark wrist position
            color = (255, 0, 0) if hand_data.handedness == "Right" else (0, 0, 255)
            cv2.circle(image, (wx, wy), 8, color, -1)
            cv2.putText(image, hand_data.handedness[0], (wx-5, wy+5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # 2. Display gesture name
            cv2.putText(image, f"Gesture: {hand_data.gesture}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

            # 3. Pinch status visualization (Pinch Visualization)
            if hand_data.is_pinching:
                # Display huge red warning in top right corner
                cv2.putText(image, "PINCHING!", (w - 150, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 3)

                # Display pinch force bar
                cv2.rectangle(image, (w - 30, 100), (w - 10, 200), (50, 50, 50), -1)
                # The smaller the distance, the tighter the pinch, the higher the fill
                # Assume pinch_distance 0.0 ~ 0.2
                fill_h = int((1.0 - (hand_data.pinch_distance * 5)) * 100)
                fill_h = np.clip(fill_h, 0, 100)
                cv2.rectangle(image, (w - 30, 200 - fill_h), (w - 10, 200), (0, 0, 255), -1)
    import cv2
    import threading
    import time
    from queue import Queue
    from datetime import datetime

    # 引入上面的 Visualizer 类
    # from visualizer import VisionVisualizer

    def run_unit_test():
        # 1. Configuration parameters
        RESOLUTION = (640, 480)
        FPS = 20
        OUTPUT_FILE = f"test_output_{datetime.now().strftime('%H%M%S')}.avi"

        # 2. Initialize service
        # Note: We use a trick, should we use the main thread's VideoCapture or let the service manage it itself?
        # To test the original Service, let the Service manage the camera itself.
        # But in order to get the image, we need the Service to expose latest_frame.
        # If we don't want to modify the Service source code, it is difficult to use the camera exclusive feature of OpenCV in the main loop.
        # *** Best solution: Modify Service or inherit ***

        class DebugVisionService(MediaPipeVisionService):
            """Inherit from the original service, add a method to get the current frame for Debug"""
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._current_frame = None
                self._frame_lock = threading.Lock()

            # It is difficult to rewrite part of _camera_loop,
            # so we get data via callback externally,
            # but we need the frame.
            # Since it is a unit test, we assume you have added self.latest_frame in the Service class
            # Or we use a Hack here:

            # In fact, the simplest test method is: do not use the internal camera of the Service,
            # but the test program reads the camera and passes the image to the Service for processing.
            # But your Service is designed to manage the camera itself.

            # Let's use the "Queue" pattern, and assume we can't get the frame in the callback.
            # This is a common design pain point.
            # In this test, we let Visualizer draw on a blank/black background,
            # or we modify the Service logic slightly.
            pass

        # ==========================================
        # Actual test logic
        # ==========================================
        print("Initializing service...")
        service = MediaPipeVisionService(camera_index=0, resolution=RESOLUTION, fps=FPS)

        # Prepare video saving
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(OUTPUT_FILE, fourcc, FPS, RESOLUTION)

        # Thread communication queue
        # Format: (face_data, hand_data)
        data_queue = Queue(maxsize=10)

        # Define callback function: triggered when there is new data
        def tracking_callback(face_data, hand_data=None):
            # Note: The original callback signature might only support one parameter
            # We assume here for demonstration that we changed it in Service to support dual data callback
            # Or we register two callbacks separately and put them into the same queue
            pass

        # Register callbacks separately
        def on_face(data):
            # This is a simple synchronization mechanism:
            # We use a global dictionary to temporarily store data, synthesized by the main thread every frame
            pass

        # --- Better main loop solution ---
        # Do not rely entirely on callback for drawing, but use callback to update state, and main thread loop for drawing

        service.start()

        # Give the camera a little warm-up time
        time.sleep(2.0)

        print(f"Start recording, results will be saved to {OUTPUT_FILE}")
        print("Press 'q' to exit test")

        try:
            while True:
                loop_start = time.time()

                # 1. Core Hacker step: Get the internal Frame of the Service
                # Due to the dynamic nature of Python, we can directly access the cap of the Service instance
                # But cap.read() is not thread-safe.
                # The safest way: Service should have a get_debug_frame() method.

                # Here demonstrates if your Service does not provide frame access interface,
                # we can only draw on the blackboard, or get it intrusively.
                # Assume you added: self.latest_debug_frame = frame in VisionService

                # --- Simulate getting frame (if no exposed frame in Service, this will error) ---
                # Please add in _camera_loop of MediaPipeVisionService:
                # self.latest_debug_frame = frame.copy()

                frame = None
                if hasattr(service, 'latest_face_data'): # This is an imperfect check
                    # We try to access variables in service._camera_thread directly is unsafe
                    pass

                # To make this test run, we create a visualization background
                canvas = np.zeros((RESOLUTION[1], RESOLUTION[0], 3), dtype=np.uint8)

                # 2. Get data (thread-safe read)
                face_data = service.get_face_data()
                hand_data = service.get_hand_data() # Need to ensure Service has this method

                # 3. Draw
                VisionVisualizer.draw_face_info(canvas, face_data)
                VisionVisualizer.draw_hand_info(canvas, hand_data)
                VisionVisualizer.draw_hand_skeleton(canvas, hand_data)

                # 4. If you want to see the camera image,
                # Must modify Service code, add `self.debug_frame = frame`
                # Assume we have modified it, code as follows:
                if hasattr(service, 'debug_frame') and service.debug_frame is not None:
                    # Use camera original image to cover black background
                    with service._face_lock: # Borrow lock
                        canvas = service.debug_frame.copy()
                    VisionVisualizer.draw_face_info(canvas, face_data)
                    VisionVisualizer.draw_hand_info(canvas, hand_data)
                    VisionVisualizer.draw_hand_skeleton(canvas, hand_data)
                else:
                    cv2.putText(canvas, "Original Frame Not Available", (10, 200),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
                    cv2.putText(canvas, "(Modify Service to expose self.debug_frame)", (10, 230),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)

                # 5. Display and save
                # cv2.imshow("Vision Service Unit Test", canvas)
                out.write(canvas)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

                # Maintain FPS
                elapsed = time.time() - loop_start
                wait = max(0, (1.0/FPS) - elapsed)
                time.sleep(wait)

        except KeyboardInterrupt:
            pass
        finally:
            service.stop()
            out.release()
            cv2.destroyAllWindows()
            print("Test finished.")
    run_unit_test()