import cv2
import json
import time
import os
import sys
import threading
import queue
import asyncio
import numpy as np
import mediapipe as mp
from scipy.signal import butter, filtfilt
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiohttp import web
from av import VideoFrame

# ----------------------------------------------------
# SYSTEM ENGINE DYNAMIC PATH REALIGNMENT
# ----------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Seamless imports from system sub-folders
from sensors.radar_receiver import MmWaveRadarReceiver
from core.hrv_logger import AuraHrvLogger
from hardware.cellular_sos import CellularSosRouter

# Global config constants for face-mesh crop matrix stabilization
ANCHOR_INDICES = [33, 263, 1]  # Left eye corner, Right eye corner, Nose tip
DST_PTS = np.array([[60, 130], [140, 130], [100, 110]], dtype=np.float32)

# ----------------------------------------------------
# WEBRTC CUSTOM OUTBOUND STREAM TRACK STRUCT
# ----------------------------------------------------
class WebRtcVideoTrack(VideoStreamTrack):
    """Consumes processed frames and streams them over secure P2P channels."""
    def __init__(self, frame_queue):
        super().__init__()
        self.frame_queue = frame_queue

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        while self.frame_queue.empty():
            await asyncio.sleep(0.01)  # Yield thread to avoid lockups
        cv_frame = self.frame_queue.get()
        av_frame = VideoFrame.from_ndarray(cv_frame, format="bgr24")
        av_frame.pts = pts
        av_frame.time_base = time_base
        return av_frame

# ----------------------------------------------------
# WEBRTC HUB SERVER SIGNALLING COMPONENT
# ----------------------------------------------------
class AuraTelehealthStreamServer:
    def __init__(self, shared_frame_queue):
        self.frame_queue = shared_frame_queue
        self.pcs = set()

    async def handle_offer_endpoint(self, request):
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        pc = RTCPeerConnection()
        self.pcs.add(pc)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if pc.connectionState in ["failed", "closed"]:
                await pc.close()
                self.pcs.discard(pc)
                print("ℹ️ [TELEHEALTH DISCONNECT] Monitoring link connection dropped.")

        video_track = WebRtcVideoTrack(self.frame_queue)
        pc.addTrack(video_track)
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

    def start_signaling_server(self, host="0.0.0.0", port=8080):
        app = web.Application()
        app.router.add_post("/offer", self.handle_offer_endpoint)
        loop = asyncio.new_event_loop()
        threading.Thread(target=lambda: web.run_app(app, host=host, port=port, loop=loop), daemon=True).start()
        print(f"📡 [WEBRTC SERVER] Telehealth stream channel active at: http://{host}:{port}/offer")

# ----------------------------------------------------
# CORE ECOSYSTEM ORCHESTRATOR HUB
# ----------------------------------------------------
class AuraHealthAmbientHub:
    def __init__(self, config_path="config/system_config.json"):
        self.config_path = config_path
        self.load_system_configuration()
        
        # Hardware & Queue allocations
        self.cap = None
        self.radar = None
        self.frame_queue = queue.Queue(maxsize=5)
        
        # State indicators
        self.is_running = True
        self.active_mode = "CAMERA"
        self.signal_window = []
        self.prev_y_center = None
        self.prev_radar_z = None
        self.prev_time = time.time()
        self.last_alert_time = 0

        # Submodule Initializations
        self.hrv_logger = AuraHrvLogger()
        self.cellular_router = CellularSosRouter()
        self.cellular_router.initialize_modem()

        # Initialize MediaPipe Frameworks
        self.mp_face_mesh = mp.solutions.face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)
        self.mp_pose = mp.solutions.pose.Pose(
            min_detection_confidence=self.cfg["kinematics_fall_detection"]["mediapipe_pose"]["min_detection_confidence"],
            min_tracking_confidence=self.cfg["kinematics_fall_detection"]["mediapipe_pose"]["min_tracking_confidence"]
        )
        self.mp_drawing = mp.solutions.drawing_utils

        # Setup streaming server link
        self.stream_server = AuraTelehealthStreamServer(self.frame_queue)

    def load_system_configuration(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration profile missing at path: {self.config_path}")
        with open(self.config_path, 'r') as file:
            self.cfg = json.load(file)
        print(f"[CONFIG LOADED] Successful sync with System Parameters (v{self.cfg['system_metadata']['version']})")

    @staticmethod
    def _butter_bandpass(data, lowcut=0.75, highcut=3.0, fs=30, order=3):
        nyq = 0.5 * fs
        b, a = butter(order, [lowcut/nyq, highcut/nyq], btype='band')
        return filtfilt(b, a, data)

    def stabilize_and_extract_roi(self, frame, landmarks, w, h):
        """Removes pixel translations via 2D Affine Alignment matrix warping"""
        src_pts = []
        for idx in ANCHOR_INDICES:
            pt = landmarks.landmark[idx]
            src_pts.append([pt.x * w, pt.y * h])
        src_pts = np.array(src_pts, dtype=np.float32)
        
        M = cv2.getAffineTransform(src_pts, DST_PTS)
        warped_face = cv2.warpAffine(frame, M, (200, 200))
        forehead_roi = warped_face[20:60, 60:140]  # Target high vascular forehead areas
        return cv2.mean(forehead_roi)[:3] if forehead_roi.size > 0 else None

    def execute_pos_algorithm(self, rgb_window):
        """Applies mathematical POS projection to remove dynamic facial illumination movement noise"""
        raw_signal = np.array(rgb_window)
        mean_rgb = np.mean(raw_signal, axis=0)
        normalized_rgb = raw_signal / mean_rgb
        
        projection_matrix = np.array([[-0.2, 0.4, -0.2], [0.2, 0.4, -0.4]])
        h_signal = np.dot(normalized_rgb, projection_matrix.T)
        weight = np.std(h_signal[:, 0]) / np.std(h_signal[:, 1])
        return h_signal[:, 0] - weight * h_signal[:, 1]

    def evaluate_ambient_luminance(self, frame):
        """Monitors room brightness to handle seamless day/night transitions"""
        yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV)
        avg_luma = cv2.mean(yuv[:, :, 0])[0]
        
        if avg_luma < 35.0 and self.active_mode == "CAMERA":
            if self.cfg["sensor_inputs"]["mmwave_radar"]["enabled"]:
                self.active_mode = "RADAR"
                print("⚠️ [SENSORY SHIFT] Low light conditions detected. Engaging mmWave Radar Tracking...")
        elif avg_luma >= 45.0 and self.active_mode == "RADAR":
            self.active_mode = "CAMERA"
            print("☀️ [SENSORY SHIFT] Room illumination restored. Returning to RGB Computer Vision.")

    def video_capture_worker(self):
        source = self.cfg["sensor_inputs"]["camera"]["source_id"]
        self.cap = cv2.VideoCapture(source)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg["sensor_inputs"]["camera"]["target_width"])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg["sensor_inputs"]["camera"]["target_height"])
        
        target_fps = self.cfg["sensor_inputs"]["camera"]["target_fps"]
        while self.is_running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                break
            if not self.frame_queue.full():
                self.frame_queue.put(frame)
            time.sleep(1 / target_fps)

    def main_orchestrator_engine(self):
        r_cfg = self.cfg["sensor_inputs"]["mmwave_radar"]
        self.radar = MmWaveRadarReceiver(r_cfg["serial_port"], r_cfg["baud_rate"], r_cfg["min_range_meters"], r_cfg["max_range_meters"])
        self.radar.connect()

        # Fire up async WebRTC web streams background threads
        self.stream_server.start_signaling_server()
        print("[⚡ SYSTEM START] aura-health-ambient engine is now operating.")

        while self.is_running:
            if self.frame_queue.empty():
                continue
                
            frame = self.frame_queue.get()
            current_time = time.time()
            dt = current_time - self.prev_time
            self.prev_time = current_time
            
            self.evaluate_ambient_luminance(frame)
                        # ----------------------------------------------------
            # MODE A: VISION TRACKING ACTIVE (DAYTIME OPERATION)
            # ----------------------------------------------------
            if self.active_mode == "CAMERA":
                h, w, _ = frame.shape
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Task 1: Non-Contact rPPG Face Processing
                face_results = self.mp_face_mesh.process(rgb_frame)
                if face_results.multi_face_landmarks:
                    mean_rgb = self.stabilize_and_extract_roi(frame, face_results.multi_face_landmarks[0], w, h)
                    if mean_rgb:
                        self.signal_window.append(mean_rgb)
                        if len(self.signal_window) > 300: # 10s evaluation buffer limit
                            self.signal_window.pop(0)

                        if len(self.signal_window) == 300:
                            try:
                                clean_pulse = self.execute_pos_algorithm(self.signal_window)
                                filtered = self._butter_bandpass(clean_pulse, fs=30)
                                fft_data = np.abs(np.fft.rfft(filtered))
                                frequencies = np.fft.rfftfreq(300, d=1.0/30)
                                bpm = frequencies[np.argmax(fft_data)] * 60
                                
                                if 45 <= bpm <= 180:
                                    cv2.putText(frame, f"Vitals (rPPG): {bpm:.1f} BPM", (20, 50),
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                                    # Log data frame along mock environmental data profiles
                                    fake_rr_ms = np.random.normal(60000/bpm, 30, 10)
                                    self.hrv_logger.append_vital_metrics_log(bpm, fake_rr_ms, 22.0, 1013.2, 1014.0)
                            except Exception:
                                pass

                # Task 2: Structural Pose Kinetics (Fall Crash Profiler)
                pose_results = self.mp_pose.process(rgb_frame)
                if pose_results.pose_landmarks:
                    self.mp_drawing.draw_landmarks(frame, pose_results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS)
                    landmarks = pose_results.pose_landmarks.landmark
                    
                    # Explicit index lookup matching Left and Right shoulders
                    y_center = (landmarks[11].y + landmarks[12].y) * h / 2
                    all_x = [lm.x * w for lm in landmarks if lm.visibility > 0.5]
                    all_y = [lm.y * h for lm in landmarks if lm.visibility > 0.5]
                    
                    if all_x and all_y and dt > 0:
                        box_h = max(all_y) - min(all_y)
                        aspect_ratio = (max(all_x) - min(all_x)) / max(1, box_h)
                        velocity_y = (y_center - self.prev_y_center) / dt if self.prev_y_center else 0
                        self.prev_y_center = y_center
                        
                        f_cfg = self.cfg["kinematics_fall_detection"]["thresholds"]
                        if velocity_y > f_cfg["critical_vertical_velocity"] and aspect_ratio > f_cfg["horizontal_aspect_ratio"]:
                            self.trigger_emergency_protocol("VISION-BASED FALL CRASH")

                cv2.putText(frame, "ACTIVE AGENT: COMPUTER VISION (DIURNAL)", (10, h - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # ----------------------------------------------------
            # MODE B: RADAR TRACKING ACTIVE (NIGHTTIME OPERATION)
            # ----------------------------------------------------
            elif self.active_mode == "RADAR":
                if self.radar.is_connected:
                    points = self.radar.read_packet()
                    current_z = self.radar.analyze_fall_kinetics(points)
                    if current_z != 0.0 and self.prev_radar_z is not None and dt > 0:
                        collapse_velocity = (self.prev_radar_z - current_z) / dt
                        if collapse_velocity > 1.8:
                            self.trigger_emergency_protocol("RADAR-BASED NIGHTTIME FALL")
                    if current_z != 0.0:
                        self.prev_radar_z = current_z
                
                frame = np.zeros_like(frame)
                cv2.putText(frame, "ACTIVE AGENT: MMWAVE RADAR (NIGHT MESH ON)", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

            cv2.imshow('AURA-Health-Ambient Control Panel', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.is_running = False

        self.cleanup()

    def trigger_emergency_protocol(self, trigger_source):
        cooldown = self.cfg["emergency_incident_response"]["alert_cooldown_seconds"]
        if time.time() - self.last_alert_time > cooldown:
            print(f"\n🚨 [CRITICAL ALERT VIA {trigger_source}] Emergency detected!")
            print("Dispatching automated communication channels to medical providers and family...")
            
            # Send hardware SMS via cellular breakout boards
            self.cellular_router.dispatch_emergency_sms(
                target_phone="+1234567890", 
                message=f"CRITICAL MEDICAL ALERT: AURA registered an unacknowledged {trigger_source} event. Please check immediately."
            )
            self.last_alert_time = time.time()

    def cleanup(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
        if self.radar:
            self.radar.close()
        cv2.destroyAllWindows()

    def run(self):
        capture_thread = threading.Thread(target=self.video_capture_worker)
        orchestration_thread = threading.Thread(target=self.main_orchestrator_engine)
        
        capture_thread.start()
        orchestration_thread.start()
        
        capture_thread.join()
        orchestration_thread.join()

if __name__ == "__main__":
    print("\n[INIT] Instantiating Aura Health Ambient Hub...")
    try:
        hub = AuraHealthAmbientHub()
        
        # Automatically configure the testing profile for local desktop evaluation
        hub.cfg["sensor_inputs"]["camera"]["source_id"] = 0  # Force local webcam index
        hub.cfg["sensor_inputs"]["mmwave_radar"]["enabled"] = False  # Ignore serial timeouts on Windows
        
        print("[INIT] Launching background processing loops...")
        hub.run()
    except Exception as error:
        print(f"❌ [CRITICAL LAUNCH ERROR] System runtime encountered an issue: {error}")
