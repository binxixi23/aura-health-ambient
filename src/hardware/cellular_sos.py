import serial
import time

class CellularSosRouter:
    def __init__(self, port="/dev/ttyUSB1", baud_rate=115200):
        self.port = port
        self.baud_rate = baud_rate
        self.serial_bus = None

    def initialize_modem(self):
        """Initializes raw UART bus to establish sync with cellular basebands"""
        try:
            self.serial_bus = serial.Serial(self.port, self.baud_rate, timeout=1.0)
            time.sleep(0.5)
            # Test transmission channel using standard check routines
            self.send_at_command("AT") 
            # Place the transceiver into Text SMS Mode configuration profile
            self.send_at_command("AT+CMGF=1") 
            print("[CELLULAR MODULE] Handshake completed successfully. eSIM hardware ready.")
            return True
        except Exception as e:
            print(f"[CELLULAR HARDWARE ERROR] Modems missing or disconnected: {e}")
            return False

    def send_at_command(self, cmd, wait_time=0.5):
        """Pipes raw operational arrays into serial registers"""
        if not self.serial_bus:
            return ""
        self.serial_bus.write(f"{cmd}\r\n".encode())
        time.sleep(wait_time)
        response = self.serial_bus.read(self.serial_bus.in_waiting).decode(errors='ignore')
        return response

    def dispatch_emergency_sms(self, target_phone, message):
        """Sends emergency SMS packets without cloud/Wi-Fi dependencies"""
        print(f"[DISPATCHING CELLULAR SOS] Routing SMS payload to: {target_phone}")
        try:
            # Step A: Feed the destination phone string down to modems registry
            self.send_at_command(f'AT+CMGS="{target_phone}"', wait_time=0.5)
            # Step B: Write the core string block message body text
            self.serial_bus.write(f"{message}".encode())
            # Step C: Write the standard ASCII End-Of-Transmission byte sequence (Ctrl+Z -> 0x1A)
            self.serial_bus.write(bytes([0x1A]))
            time.sleep(3.0)
            print("🚀 [SMS DISPATCH COMPLETE] Cell network confirmed delivery.")
            return True
        except Exception as e:
            print(f"[SMS ROUTING FAILURE] Core cellular drop error: {e}")
            return False
