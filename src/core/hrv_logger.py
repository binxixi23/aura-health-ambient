import numpy as np
import json
import csv
import os
import time
from datetime import datetime

class AuraHrvLogger:
    def __init__(self, log_dir="data/vitals_history"):
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        self.log_file = os.path.join(self.log_dir, "hrv_seasonal_trends.csv")
        self.initialize_csv_headers()

    def initialize_csv_headers(self):
        """Builds long-term timeline storage maps if missing"""
        if not os.path.exists(self.log_file):
            with open(self.log_file, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp", "Calculated_BPM", "HRV_RMSSD_ms", 
                    "Ambient_Temp_C", "Barometric_Pressure_hPa", "Cardiac_Risk_Index"
                ])

    def calculate_hrv_rmssd(self, rr_intervals_ms):
        """
        Computes standard clinical RMSSD (Root Mean Square of Successive Differences).
        Higher numbers usually imply healthy autonomic adaptivity.
        """
        if len(rr_intervals_ms) < 2:
            return 0.0
        # Calculate individual step deltas across adjacent heart pulse beats
        diffs = np.diff(rr_intervals_ms)
        squared_diffs = diffs ** 2
        mean_squared_diffs = np.mean(squared_diffs)
        return np.sqrt(mean_squared_diffs)

    def assess_seasonal_vulnerability(self, current_hrv, delta_pressure_hpa):
        """
        Predictive heuristic logic checking if historical drop metrics 
        correlate with incoming atmospheric changes (e.g., sharp pressure drops).
        """
        # Baseline check: Low HRV combined with a major drop in barometric pressure
        if current_hrv < 20.0 and delta_pressure_hpa < -6.0:
            return "CRITICAL_RISK_WARNING" # Low cardiovascular flexibility under strain
        elif current_hrv < 35.0 and delta_pressure_hpa < -3.0:
            return "ELEVATED_VULNERABILITY"
        return "STABLE"

    def append_vital_metrics_log(self, current_bpm, rr_intervals_ms, current_temp, current_press, prev_press):
        """Saves long-term trend data to local storage for diagnostic review"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hrv_ms = self.calculate_hrv_rmssd(rr_intervals_ms)
        
        delta_p = current_press - prev_press
        risk_evaluation = self.assess_seasonal_vulnerability(hrv_ms, delta_p)
        
        with open(self.log_file, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, f"{current_bpm:.1f}", f"{hrv_ms:.2f}", f"{current_temp:.1f}", f"{current_press:.1f}", risk_evaluation])
            
        if risk_evaluation in ["CRITICAL_RISK_WARNING", "ELEVATED_VULNERABILITY"]:
            print(f"⚠️ [SEASONAL CARDIO ALERT] Heart rate tracking signals low HRV adaptivity ({hrv_ms:.1f}ms) under sudden pressure drops ({delta_p:.1f}hPa).")
            return risk_evaluation
        return "STABLE"
