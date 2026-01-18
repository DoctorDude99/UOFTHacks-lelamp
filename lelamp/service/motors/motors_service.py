import os
import csv
import time
import logging
from typing import Any, List, Dict, Literal
from ..base import ServiceBase
from lelamp.follower import LeLampFollowerConfig, LeLampFollower

LAMP_ID = "lelamp"
logger = logging.getLogger(__name__)

# Voltage limit presets
VOLTAGE_PRESETS = {
    "7.4": {"min": 45, "max": 80},   # 4.5V - 8.0V
    "12": {"min": 45, "max": 140},   # 4.5V - 14.0V
}

# STS3215 EEPROM addresses
ADDR_MIN_VOLTAGE = 10
ADDR_MAX_VOLTAGE = 11
ADDR_LOCK = 48


class MotorsService(ServiceBase):
    def __init__(self, port: str, fps: int = 30):
        super().__init__("motors")
        self.port = port
        self.fps = fps
        self.robot_config = LeLampFollowerConfig(port=port, id=LAMP_ID)
        self.robot: LeLampFollower = None
        self.recordings_dir = os.path.join(os.path.dirname(__file__), "..", "..", "recordings")
    
    def start(self):
        super().start()

        # Check if motors are enabled in config
        import lelamp.globals as g
        motors_config = g.CONFIG.get("motors", {})
        if not motors_config.get("enabled", True):
            self.logger.info("Motors disabled in config - motors service not started")
            return

        self.robot = LeLampFollower(self.robot_config)

        # Check if calibration file exists before connecting
        if not os.path.exists(self.robot.calibration_fpath):
            # Set global flag for post-assembly setup
            g.calibration_required = True
            g.calibration_path = self.robot.calibration_fpath
            self.logger.warning(f"Calibration required: {self.robot.calibration_fpath}")
            self.logger.info("Motors service will remain disabled until calibration is complete")
            self.logger.info(f"Complete setup wizard at WebUI or run: uv run -m lelamp.calibrate --port {self.port}")
            # Don't raise error - just return without connecting
            return

        self.robot.connect(calibrate=True)
        self.logger.info(f"Motors service connected to {self.port}")

    def stop(self, timeout: float = 5.0):
        if self.robot:
            self.robot.disconnect()
            self.robot = None
        super().stop(timeout)
    
    def handle_event(self, event_type: str, payload: Any):
        if event_type == "play":
            self._handle_play(payload)
        else:
            self.logger.warning(f"Unknown event type: {event_type}")
    
    def _handle_play(self, recording_name: str):
        """Play a recording by name"""
        if not self.robot:
            self.logger.error("Robot not connected")
            return

        csv_filename = f"{recording_name}.csv"
        csv_path = os.path.join(self.recordings_dir, csv_filename)
        
        if not os.path.exists(csv_path):
            self.logger.error(f"Recording not found: {csv_path}")
            return
        
        try:
            with open(csv_path, 'r') as csvfile:
                csv_reader = csv.DictReader(csvfile)
                actions = list(csv_reader)
            
            self.logger.info(f"Playing {len(actions)} actions from {recording_name}")
            
            for row in actions:
                t0 = time.perf_counter()
                
                # Extract action data (exclude timestamp column)
                action = {key: float(value) for key, value in row.items() if key != 'timestamp'}
                self.robot.send_action(action)
                
                # Use time.sleep instead of busy_wait to avoid blocking other threads
                sleep_time = 1.0 / self.fps - (time.perf_counter() - t0)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            self.logger.info(f"Finished playing recording: {recording_name}")
            
        except Exception as e:
            self.logger.error(f"Error playing recording {recording_name}: {e}")
    
    def get_available_recordings(self) -> List[str]:
        """Get list of available recording names"""
        if not os.path.exists(self.recordings_dir):
            return []

        recordings = []

        for filename in os.listdir(self.recordings_dir):
            if filename.endswith(".csv"):
                recording_name = filename[:-4]  # Remove .csv
                recordings.append(recording_name)

        return sorted(recordings)


def fix_motor_voltage_limits(port: str, voltage: Literal["7.4", "12"]) -> Dict[str, Any]:
    """
    Fix motor voltage limits for all connected motors.

    Args:
        port: Serial port (e.g., "/dev/lelamp")
        voltage: Target voltage - "7.4" or "12"

    Returns:
        Dict with success status and per-motor results
    """
    import scservo_sdk as scs

    if voltage not in VOLTAGE_PRESETS:
        return {
            "success": False,
            "error": f"Invalid voltage: {voltage}. Must be '7.4' or '12'"
        }

    preset = VOLTAGE_PRESETS[voltage]
    min_voltage = preset["min"]
    max_voltage = preset["max"]

    results = {
        "success": True,
        "voltage": voltage,
        "min_limit": min_voltage,
        "max_limit": max_voltage,
        "motors": {}
    }

    try:
        port_handler = scs.PortHandler(port)
        packet = scs.PacketHandler(0)

        if not port_handler.openPort():
            return {"success": False, "error": f"Failed to open port {port}"}

        port_handler.setBaudRate(1000000)

        # Scan and fix motors 1-5
        for motor_id in range(1, 6):
            motor_result = {"id": motor_id, "found": False}

            try:
                port_handler.setPacketTimeoutMillis(100)
                model, comm, error = packet.ping(port_handler, motor_id)

                if comm != 0:
                    motor_result["error"] = "Not responding"
                    results["motors"][f"motor_{motor_id}"] = motor_result
                    continue

                motor_result["found"] = True
                motor_result["model"] = model

                # Read current values
                old_min, _, _ = packet.read1ByteTxRx(port_handler, motor_id, ADDR_MIN_VOLTAGE)
                old_max, _, _ = packet.read1ByteTxRx(port_handler, motor_id, ADDR_MAX_VOLTAGE)
                curr_v, _, _ = packet.read1ByteTxRx(port_handler, motor_id, 62)

                motor_result["old_min"] = old_min
                motor_result["old_max"] = old_max
                motor_result["present_voltage"] = curr_v / 10

                # Unlock EEPROM
                packet.write1ByteTxRx(port_handler, motor_id, ADDR_LOCK, 0)

                # Write new voltage limits
                packet.write1ByteTxRx(port_handler, motor_id, ADDR_MIN_VOLTAGE, min_voltage)
                packet.write1ByteTxRx(port_handler, motor_id, ADDR_MAX_VOLTAGE, max_voltage)

                # Lock EEPROM
                packet.write1ByteTxRx(port_handler, motor_id, ADDR_LOCK, 1)

                # Verify
                new_min, _, _ = packet.read1ByteTxRx(port_handler, motor_id, ADDR_MIN_VOLTAGE)
                new_max, _, _ = packet.read1ByteTxRx(port_handler, motor_id, ADDR_MAX_VOLTAGE)

                motor_result["new_min"] = new_min
                motor_result["new_max"] = new_max
                motor_result["fixed"] = (new_min == min_voltage and new_max == max_voltage)

                if not motor_result["fixed"]:
                    results["success"] = False
                    motor_result["error"] = "Failed to verify new values"

            except Exception as e:
                motor_result["error"] = str(e)
                results["success"] = False

            results["motors"][f"motor_{motor_id}"] = motor_result

        port_handler.closePort()

        # Count results
        found = sum(1 for m in results["motors"].values() if m.get("found"))
        fixed = sum(1 for m in results["motors"].values() if m.get("fixed"))
        results["summary"] = f"Fixed {fixed}/{found} motors for {voltage}V operation"

        logger.info(results["summary"])
        return results

    except Exception as e:
        logger.error(f"Error fixing voltage limits: {e}")
        return {"success": False, "error": str(e)}