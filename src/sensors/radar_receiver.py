import serial
import time
import struct
import numpy as np

class MmWaveRadarReceiver:
    def __init__(self, port="/dev/ttyUSB0", baud_rate=921600, min_dist=0.5, max_dist=4.5):
        self.port = port
        self.baud_rate = baud_rate
        self.min_dist = min_dist
        self.max_dist = max_dist
        self.serial_conn = None
        self.is_connected = False

    def connect(self):
        """Establishes interface link with the TI mmWave sensor hardware"""
        try:
            self.serial_conn = serial.Serial(self.port, self.baud_rate, timeout=0.1)
            self.is_connected = True
            print(f"[RADAR] Connection successful on port: {self.port}")
        except Exception as e:
            print(f"[RADAR ERROR] Communication initialization failed: {e}")
            self.is_connected = False

    def read_packet(self):
        """
        Parses incoming serial streams.
        Returns array of points [X, Y, Z, Velocity] or None.
        """
        if not self.is_connected or not self.serial_conn.in_waiting:
            return None

        try:
            # Simple demonstration parsing structure for typical TI TLV frames
            # Seeking Magic Word header (0x0102030405060708 sequence)
            header_magic = self.serial_conn.read(8)
            if len(header_magic) < 8:
                return None
                
            # Read structural metadata headers (Version, Length, Platform, Frame Number...)
            header_meta = self.serial_conn.read(32)
            if len(header_meta) < 32:
                return None

            # Unpack total packet length from header block
            total_packet_length = struct.unpack('<I', header_meta[4:8])[0]
            num_tlvs = struct.unpack('<H', header_meta[24:26])[0]
            num_detected_obj = struct.unpack('<H', header_meta[26:28])[0]

            if num_detected_obj == 0:
                return np.empty((0, 4))

            # Read remaining data blocks belonging to this frame
            data_bytes = self.serial_conn.read(total_packet_length - 40)
            
            # Simple simulation parse loop extracting floating variables 
            # Real deployment parses specialized TLV structures (Type-Length-Value)
            points = []
            offset = 0
            for _ in range(min(num_detected_obj, 100)):
                if offset + 16 > len(data_bytes):
                    break
                # Extract coordinates in meters and relative velocity vector
                x, y, z, v = struct.unpack('<ffff', data_bytes[offset:offset+16])
                offset += 16
                
                # Filter points out of boundaries configuration
                distance = np.sqrt(x**2 + y**2 + z**2)
                if self.min_dist <= distance <= self.max_dist:
                    points.append([x, y, z, v])

            return np.array(points) if points else np.empty((0, 4))

        except Exception as e:
            print(f"[RADAR PROCESSING ERROR] Malformed raw stream packet: {e}")
            return None

    def analyze_fall_kinetics(self, point_cloud):
        """Analyzes 3D centroid collapse velocity when vision inputs are offline"""
        if point_cloud is None or len(point_cloud) < 5:
            return False, 0.0

        # Calculate median vertical heights (Z axis) of human cluster
        z_values = point_cloud[:, 2]
        median_z = np.median(z_values)
        
        # Returns current height metrics for main cross-modality evaluation
        return median_z

    def close(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
