import numpy as np
import time
import json
import os

class AuraSensorNoiseAnalyzer:
    def __init__(self, config_path="config/system_config.json"):
        self.config_path = config_path
        with open(self.config_path, 'r') as f:
            self.cfg = json.load(f)
            
    def analyze_camera_noise_floor(self, cap_source=0):
        """Measures high-frequency pixel noise and illumination stability profiles"""
        import cv2
        cap = cv2.VideoCapture(cap_source)
        if not cap.isOpened():
            print("🔴 [ANALYZER] Failed to open target video source.")
            return
            
        print("\n--- 📷 ANALYZING CAMERA PIXEL NOISE FLOOR ---")
        print("Please ensure the monitoring zone is empty and static...")
        
        luma_samples = []
        for _ in range(90):  # Sample 3 seconds of video at 30 FPS
            ret, frame = cap.read()
            if not ret:
                break
            yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV)
            avg_luma = cv2.mean(yuv[:, :, 0])[0]
            luma_samples.append(avg_luma)
            time.sleep(0.033)
            
        cap.release()
        
        luma_array = np.array(luma_samples)
        variance = np.var(luma_array)
        std_dev = np.std(luma_array)
        
        print(f"-> Mean Lux Luma Index: {np.mean(luma_array):.2f}")
        print(f"-> Temporal Luma Variance: {variance:.4f}")
        print(f"-> Standard Deviation (σ): {std_dev:.4f}")
        
        if std_dev > 2.5:
            print("❌ [WARNING] High illumination flicker detected! Check for fluorescent ballast noise or pulsing AC lights.")
        else:
            print("✅ [PASSED] Ambient light stability is clean enough for rPPG micro-color extraction.")

    def analyze_radar_clutter_profile(self, points_cloud_stream):
        """Computes structural noise floors and isolates background multi-path reflections"""
        print("\n--- 📡 ANALYZING MMWAVE RADAR STATIC CLUTTER ---")
        if points_cloud_stream is None or len(points_cloud_stream) == 0:
            print("⚠️ [EMPTY CLOUD] No returns detected. Sensor field is clear.")
            return
            
        z_array = points_cloud_stream[:, 2] # Extract elevation axis data
        v_array = points_cloud_stream[:, 3] # Extract Doppler velocity vectors
        
        mean_v = np.mean(np.abs(v_array))
        std_z = np.std(z_array)
        
        print(f"-> Total Active Reflection Points: {len(points_cloud_stream)}")
        print(f"-> Baseline Velocity Noise Vector: {mean_v:.4f} m/s")
        print(f"-> Target Spatial Thickness (σ_z): {std_z:.4f}m")
        
        if mean_v > 0.15:
            print("❌ [WARNING] High baseline velocity noise detected! Check for moving fans, pets, or loose mechanical structures.")
        else:
            print("✅ [PASSED] Radar static clutter environments are within safe processing limits.")

if __name__ == "__main__":
    analyzer = AuraSensorNoiseAnalyzer()
    # Execute camera analysis using native pipeline hooks
    analyzer.analyze_camera_noise_floor(cap_source=0)
    
    # Simulate a static room array matrix to confirm mathematical threshold parsers
    mock_static_radar_stream = np.column_stack((
        np.random.normal(0.0, 0.05, 30), # X
        np.random.normal(2.5, 0.05, 30), # Y
        np.random.normal(1.4, 0.02, 30), # Z (Static height center)
        np.random.normal(0.0, 0.01, 30)  # V (Velocity near absolute zero)
    ))
    analyzer.analyze_radar_clutter_profile(mock_static_radar_stream)
