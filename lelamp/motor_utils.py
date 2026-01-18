#!/usr/bin/env python3
"""
motor_utils.py - Motor utility functions for LeLamp setup

This module provides CLI utilities for motor setup, scanning, and calibration.
Used by install/install_motors.sh for interactive and WebUI-driven setup.

Usage:
    python -m lelamp.motor_utils scan --port /dev/lelamp
    python -m lelamp.motor_utils check-ids --port /dev/lelamp
    python -m lelamp.motor_utils id-motor --port /dev/lelamp --target-id 1
    python -m lelamp.motor_utils set-center --port /dev/lelamp --motor-id 1
    python -m lelamp.motor_utils set-center-all --port /dev/lelamp
    python -m lelamp.motor_utils apply-preset --port /dev/lelamp --preset Gentle
"""

import argparse
import sys
import time
import json

# Motor ID to name mapping
MOTOR_NAMES = {
    1: "base_yaw",
    2: "base_pitch",
    3: "elbow_pitch",
    4: "wrist_roll",
    5: "wrist_pitch"
}

# Expected motor IDs for LeLamp
EXPECTED_IDS = [1, 2, 3, 4, 5]

# Center position for STS3215 (4096 resolution / 2)
CENTER_POSITION = 2048

# Voltage limit register addresses (STS3215)
ADDR_MAX_VOLTAGE_LIMIT = 14  # 1 byte, EEPROM
ADDR_MIN_VOLTAGE_LIMIT = 15  # 1 byte, EEPROM
ADDR_TORQUE_ENABLE = 40  # 1 byte, RAM
ADDR_LOCK = 55  # EEPROM lock register

# Voltage configurations (values are in 0.1V units)
VOLTAGE_CONFIGS = {
    "7.4": {"min": 45, "max": 80, "label": "7.4V servos (STS3215)"},   # 4.5V - 8.0V
    "12": {"min": 95, "max": 135, "label": "12V servos"},              # 9.5V - 13.5V
}


def get_port_handler(port: str, baudrate: int = 1000000):
    """Create and open a port handler."""
    import scservo_sdk as scs

    port_handler = scs.PortHandler(port)
    if not port_handler.openPort():
        raise RuntimeError(f"Failed to open port {port}")
    if not port_handler.setBaudRate(baudrate):
        raise RuntimeError(f"Failed to set baudrate to {baudrate}")

    return port_handler


def scan_motors(port: str, verbose: bool = True) -> dict:
    """
    Scan the bus for all connected motors.

    Returns:
        dict: {motor_id: model_number} for all found motors
    """
    import scservo_sdk as scs

    port_handler = get_port_handler(port)
    packet_handler = scs.PacketHandler(0)  # Protocol 0 for STS series

    found_motors = {}

    try:
        # Scan IDs 0-252 (253 is broadcast)
        for motor_id in range(253):
            # Try to ping this ID
            model_number, comm_result, error = packet_handler.ping(port_handler, motor_id)

            if comm_result == scs.COMM_SUCCESS:
                found_motors[motor_id] = model_number
                if verbose:
                    name = MOTOR_NAMES.get(motor_id, "unknown")
                    print(f"  Found motor ID {motor_id} ({name}): model {model_number}")
    finally:
        port_handler.closePort()

    return found_motors


def check_expected_ids(port: str) -> tuple:
    """
    Check if all expected motor IDs (1-5) are present.

    Returns:
        tuple: (all_present: bool, found_ids: list, missing_ids: list, extra_ids: list)
    """
    found = scan_motors(port, verbose=False)
    found_ids = list(found.keys())

    missing_ids = [id for id in EXPECTED_IDS if id not in found_ids]
    extra_ids = [id for id in found_ids if id not in EXPECTED_IDS]
    all_present = len(missing_ids) == 0 and len(extra_ids) == 0

    return all_present, found_ids, missing_ids, extra_ids


def check_id_exists(port: str, target_id: int) -> bool:
    """Check if a specific motor ID exists on the bus."""
    import scservo_sdk as scs

    port_handler = get_port_handler(port)
    packet_handler = scs.PacketHandler(0)

    try:
        model_number, comm_result, error = packet_handler.ping(port_handler, target_id)
        return comm_result == scs.COMM_SUCCESS
    finally:
        port_handler.closePort()


def id_single_motor(port: str, target_id: int, force: bool = False) -> bool:
    """
    ID a single motor connected to the bus.

    Args:
        port: Serial port path
        target_id: The ID to assign (1-5)
        force: If True, skip safety checks

    Returns:
        bool: True if successful
    """
    import scservo_sdk as scs

    if target_id < 1 or target_id > 5:
        print(f"Error: Target ID must be 1-5, got {target_id}")
        return False

    # Check if target ID already exists on the bus
    if not force and check_id_exists(port, target_id):
        print(f"Error: Motor ID {target_id} already exists on the bus!")
        print("Disconnect the existing motor or use a different ID.")
        return False

    # Scan for motors - should find exactly one with wrong ID
    print(f"Scanning for motor to assign ID {target_id}...")
    found = scan_motors(port, verbose=False)

    if len(found) == 0:
        print("Error: No motor found. Make sure exactly one motor is connected.")
        return False

    if len(found) > 1:
        print(f"Error: Found {len(found)} motors. Disconnect all but one motor.")
        print(f"Found IDs: {list(found.keys())}")
        return False

    current_id = list(found.keys())[0]

    if current_id == target_id:
        print(f"Motor already has ID {target_id}. No change needed.")
        return True

    print(f"Found motor with ID {current_id}, changing to ID {target_id}...")

    port_handler = get_port_handler(port)
    packet_handler = scs.PacketHandler(0)

    try:
        # Unlock EEPROM
        comm_result, error = packet_handler.write1ByteTxRx(port_handler, current_id, 55, 0)  # Lock address
        if comm_result != scs.COMM_SUCCESS:
            print(f"Warning: Failed to unlock EEPROM: {packet_handler.getTxRxResult(comm_result)}")

        # Write new ID (address 5 for STS series)
        comm_result, error = packet_handler.write1ByteTxRx(port_handler, current_id, 5, target_id)
        if comm_result != scs.COMM_SUCCESS:
            print(f"Error: Failed to write new ID: {packet_handler.getTxRxResult(comm_result)}")
            return False

        # Lock EEPROM
        comm_result, error = packet_handler.write1ByteTxRx(port_handler, target_id, 55, 1)

        print(f"Successfully changed motor ID from {current_id} to {target_id}")

        # Verify
        time.sleep(0.1)
        if check_id_exists(port, target_id):
            print(f"Verified: Motor now responds to ID {target_id}")
            return True
        else:
            print("Warning: Motor does not respond to new ID. Power cycle may be required.")
            return True  # Still return True as the write succeeded

    finally:
        port_handler.closePort()


def set_center_position(port: str, motor_id: int) -> bool:
    """
    Set a motor's current position as center (2048).

    This writes to the Homing_Offset to make current position = 2048.

    WARNING: Motor should be disconnected from arm mechanism to prevent damage.

    Args:
        port: Serial port path
        motor_id: Motor ID to calibrate (1-5)

    Returns:
        bool: True if successful
    """
    import scservo_sdk as scs

    if motor_id < 1 or motor_id > 5:
        print(f"Error: Motor ID must be 1-5, got {motor_id}")
        return False

    if not check_id_exists(port, motor_id):
        print(f"Error: Motor ID {motor_id} not found on bus")
        return False

    port_handler = get_port_handler(port)
    packet_handler = scs.PacketHandler(0)

    try:
        # Disable torque first
        comm_result, error = packet_handler.write1ByteTxRx(port_handler, motor_id, 40, 0)  # Torque_Enable
        if comm_result != scs.COMM_SUCCESS:
            print(f"Warning: Failed to disable torque")

        # Unlock EEPROM
        comm_result, error = packet_handler.write1ByteTxRx(port_handler, motor_id, 55, 0)  # Lock

        # Read current raw position (address 56-57, 2 bytes)
        current_pos, comm_result, error = packet_handler.read2ByteTxRx(port_handler, motor_id, 56)
        if comm_result != scs.COMM_SUCCESS:
            print(f"Error: Failed to read current position")
            return False

        print(f"Current raw position: {current_pos}")

        # Calculate homing offset to make current position appear as 2048
        # Present_Position = Actual_Position - Homing_Offset
        # 2048 = current_pos - offset
        # offset = current_pos - 2048
        new_offset = current_pos - CENTER_POSITION

        # Homing offset is a signed 16-bit value (address 31-32)
        # Handle sign for negative offsets
        if new_offset < 0:
            new_offset = 65536 + new_offset  # Convert to unsigned

        print(f"Setting homing offset to: {new_offset} (to make position = 2048)")

        # Write homing offset (address 31, 2 bytes)
        comm_result, error = packet_handler.write2ByteTxRx(port_handler, motor_id, 31, new_offset)
        if comm_result != scs.COMM_SUCCESS:
            print(f"Error: Failed to write homing offset: {packet_handler.getTxRxResult(comm_result)}")
            return False

        # Lock EEPROM
        comm_result, error = packet_handler.write1ByteTxRx(port_handler, motor_id, 55, 1)

        # Verify by reading position again
        time.sleep(0.1)
        new_pos, comm_result, error = packet_handler.read2ByteTxRx(port_handler, motor_id, 56)
        print(f"New position reading: {new_pos} (should be close to 2048)")

        print(f"Motor {motor_id} ({MOTOR_NAMES.get(motor_id, 'unknown')}) centered successfully")
        return True

    finally:
        port_handler.closePort()


def set_center_all(port: str, skip_confirm: bool = False) -> bool:
    """
    Set center position for all motors (1-5).

    Args:
        port: Serial port path
        skip_confirm: If True, don't ask for confirmation

    Returns:
        bool: True if all successful
    """
    found = scan_motors(port, verbose=False)

    if not found:
        print("Error: No motors found on bus")
        return False

    success = True
    for motor_id in EXPECTED_IDS:
        if motor_id not in found:
            print(f"Warning: Motor ID {motor_id} not found, skipping")
            continue

        print(f"\nCentering motor {motor_id} ({MOTOR_NAMES.get(motor_id)})...")
        if not set_center_position(port, motor_id):
            success = False

    return success


def apply_gentle_preset(port: str) -> bool:
    """
    Apply Gentle torque preset to all motors.

    Gentle preset uses lower P coefficient and torque limit for safer operation.
    """
    import scservo_sdk as scs

    # Gentle preset values
    P_COEFF = 8
    I_COEFF = 0
    D_COEFF = 10
    TORQUE_LIMIT = 200

    found = scan_motors(port, verbose=False)

    if not found:
        print("Error: No motors found on bus")
        return False

    port_handler = get_port_handler(port)
    packet_handler = scs.PacketHandler(0)

    try:
        for motor_id in found.keys():
            if motor_id not in EXPECTED_IDS:
                continue

            name = MOTOR_NAMES.get(motor_id, "unknown")
            print(f"Applying Gentle preset to motor {motor_id} ({name})...")

            # P coefficient (address 21)
            packet_handler.write1ByteTxRx(port_handler, motor_id, 21, P_COEFF)
            # I coefficient (address 22)
            packet_handler.write1ByteTxRx(port_handler, motor_id, 22, I_COEFF)
            # D coefficient (address 23)
            packet_handler.write1ByteTxRx(port_handler, motor_id, 23, D_COEFF)
            # Torque limit (address 35-36, 2 bytes)
            packet_handler.write2ByteTxRx(port_handler, motor_id, 35, TORQUE_LIMIT)

        print("Gentle preset applied to all motors")
        return True

    finally:
        port_handler.closePort()


def read_voltage_limits(port: str, verbose: bool = True) -> dict:
    """
    Read voltage limits from all motors on the bus.

    Returns:
        dict: {motor_id: {"min": value, "max": value, "min_v": voltage, "max_v": voltage, "config": "7.4"|"12"|"unknown"}}
    """
    import scservo_sdk as scs

    # First scan to find motors
    found = scan_motors(port, verbose=False)

    if not found:
        if verbose:
            print("No motors found on bus")
        return {}

    port_handler = get_port_handler(port)
    packet_handler = scs.PacketHandler(0)

    results = {}

    try:
        for motor_id in found.keys():
            # Read min voltage limit
            min_val, comm_result, error = packet_handler.read1ByteTxRx(
                port_handler, motor_id, ADDR_MIN_VOLTAGE_LIMIT
            )
            if comm_result != scs.COMM_SUCCESS:
                if verbose:
                    print(f"  Motor {motor_id}: Failed to read min voltage limit")
                continue

            # Read max voltage limit
            max_val, comm_result, error = packet_handler.read1ByteTxRx(
                port_handler, motor_id, ADDR_MAX_VOLTAGE_LIMIT
            )
            if comm_result != scs.COMM_SUCCESS:
                if verbose:
                    print(f"  Motor {motor_id}: Failed to read max voltage limit")
                continue

            # Determine which config this matches
            config_type = "unknown"
            for cfg_name, cfg in VOLTAGE_CONFIGS.items():
                if cfg["min"] == min_val and cfg["max"] == max_val:
                    config_type = cfg_name
                    break

            results[motor_id] = {
                "min": min_val,
                "max": max_val,
                "min_v": min_val / 10.0,
                "max_v": max_val / 10.0,
                "config": config_type
            }

            if verbose:
                name = MOTOR_NAMES.get(motor_id, "unknown")
                status = f"({config_type}V config)" if config_type != "unknown" else "(non-standard)"
                print(f"  Motor {motor_id} ({name}): {min_val/10:.1f}V - {max_val/10:.1f}V {status}")

    finally:
        port_handler.closePort()

    return results


def fix_voltage_limits(port: str, target_voltage: str = "7.4", force: bool = False, verbose: bool = True) -> dict:
    """
    Fix voltage limits for all motors on the bus.

    This is useful when motors were accidentally programmed with wrong voltage limits
    (e.g., 12V limits but using 7.4V power supply), causing "Input voltage error".

    Args:
        port: Serial port path
        target_voltage: Target voltage config ("7.4" or "12")
        force: If True, write limits even if they already match
        verbose: Print progress messages

    Returns:
        dict: {motor_id: {"success": bool, "changed": bool, "old": {}, "new": {}}}
    """
    import scservo_sdk as scs

    if target_voltage not in VOLTAGE_CONFIGS:
        raise ValueError(f"Invalid voltage config: {target_voltage}. Must be one of: {list(VOLTAGE_CONFIGS.keys())}")

    target_config = VOLTAGE_CONFIGS[target_voltage]
    target_min = target_config["min"]
    target_max = target_config["max"]

    if verbose:
        print(f"Target voltage config: {target_config['label']}")
        print(f"  Min voltage limit: {target_min/10:.1f}V (register value: {target_min})")
        print(f"  Max voltage limit: {target_max/10:.1f}V (register value: {target_max})")
        print("")

    # First read current limits
    if verbose:
        print("Reading current voltage limits...")
    current_limits = read_voltage_limits(port, verbose=False)

    # Small delay to ensure port is fully released
    time.sleep(0.1)

    if not current_limits:
        if verbose:
            print("No motors found on bus")
        return {}

    results = {}
    motors_to_fix = []

    # Determine which motors need fixing
    for motor_id, limits in current_limits.items():
        needs_fix = force or (limits["min"] != target_min or limits["max"] != target_max)
        if needs_fix:
            motors_to_fix.append(motor_id)

        if verbose:
            name = MOTOR_NAMES.get(motor_id, "unknown")
            current_str = f"{limits['min_v']:.1f}V - {limits['max_v']:.1f}V"
            if needs_fix:
                print(f"  Motor {motor_id} ({name}): {current_str} → needs update")
            else:
                print(f"  Motor {motor_id} ({name}): {current_str} → OK")

    if not motors_to_fix:
        if verbose:
            print("\nAll motors already have correct voltage limits!")
        return {mid: {"success": True, "changed": False, "old": current_limits[mid]} for mid in current_limits}

    if verbose:
        print(f"\nUpdating {len(motors_to_fix)} motor(s)...")

    port_handler = get_port_handler(port)
    packet_handler = scs.PacketHandler(0)

    try:
        for motor_id in motors_to_fix:
            name = MOTOR_NAMES.get(motor_id, "unknown")
            old_limits = current_limits[motor_id]

            if verbose:
                print(f"  Updating motor {motor_id} ({name})...", end=" ", flush=True)

            try:
                # Step 1: Disable torque (required before EEPROM writes)
                comm_result, error = packet_handler.write1ByteTxRx(
                    port_handler, motor_id, ADDR_TORQUE_ENABLE, 0
                )
                # Don't fail on this - motor might already have torque off

                time.sleep(0.05)  # Small delay

                # Step 2: Unlock EEPROM (write 0 to Lock register)
                comm_result, error = packet_handler.write1ByteTxRx(
                    port_handler, motor_id, ADDR_LOCK, 0
                )
                if comm_result != scs.COMM_SUCCESS:
                    err_msg = packet_handler.getTxRxResult(comm_result)
                    raise RuntimeError(f"Failed to unlock EEPROM: {err_msg}")

                time.sleep(0.05)  # Small delay after unlock

                # Step 3: Write min voltage limit
                comm_result, error = packet_handler.write1ByteTxRx(
                    port_handler, motor_id, ADDR_MIN_VOLTAGE_LIMIT, target_min
                )
                if comm_result != scs.COMM_SUCCESS:
                    err_msg = packet_handler.getTxRxResult(comm_result)
                    raise RuntimeError(f"Failed to write min voltage limit: {err_msg}")

                time.sleep(0.05)  # Small delay between writes

                # Step 4: Write max voltage limit
                comm_result, error = packet_handler.write1ByteTxRx(
                    port_handler, motor_id, ADDR_MAX_VOLTAGE_LIMIT, target_max
                )
                if comm_result != scs.COMM_SUCCESS:
                    err_msg = packet_handler.getTxRxResult(comm_result)
                    raise RuntimeError(f"Failed to write max voltage limit: {err_msg}")

                time.sleep(0.05)  # Small delay

                # Step 5: Lock EEPROM (write 1 to Lock register)
                comm_result, error = packet_handler.write1ByteTxRx(
                    port_handler, motor_id, ADDR_LOCK, 1
                )
                # Don't fail on lock - the values were already written

                results[motor_id] = {
                    "success": True,
                    "changed": True,
                    "old": old_limits,
                    "new": {"min": target_min, "max": target_max, "min_v": target_min/10.0, "max_v": target_max/10.0}
                }

                if verbose:
                    print("OK")

            except Exception as e:
                # Try to re-lock EEPROM even on failure
                try:
                    packet_handler.write1ByteTxRx(port_handler, motor_id, ADDR_LOCK, 1)
                except:
                    pass

                results[motor_id] = {
                    "success": False,
                    "changed": False,
                    "old": old_limits,
                    "error": str(e)
                }
                if verbose:
                    print(f"FAILED: {e}")

        # Add unchanged motors to results
        for motor_id in current_limits:
            if motor_id not in results:
                results[motor_id] = {
                    "success": True,
                    "changed": False,
                    "old": current_limits[motor_id]
                }

    finally:
        port_handler.closePort()

    # Summary
    if verbose:
        changed = sum(1 for r in results.values() if r.get("changed", False))
        failed = sum(1 for r in results.values() if not r.get("success", False))
        print(f"\nVoltage limits updated: {changed} motor(s)")
        if failed:
            print(f"Failed: {failed} motor(s)")

    return results


def main():
    parser = argparse.ArgumentParser(description="LeLamp Motor Utilities")
    parser.add_argument("--port", type=str, default="/dev/lelamp",
                       help="Serial port for motor controller")
    parser.add_argument("--json", action="store_true",
                       help="Output results as JSON")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan for all motors on bus")

    # check-ids command
    check_parser = subparsers.add_parser("check-ids",
                                         help="Check if all expected IDs (1-5) are present")

    # id-motor command
    id_parser = subparsers.add_parser("id-motor", help="Assign ID to a single motor")
    id_parser.add_argument("--target-id", type=int, required=True,
                          help="Target motor ID (1-5)")
    id_parser.add_argument("--force", action="store_true",
                          help="Force ID change even if target ID exists")

    # set-center command
    center_parser = subparsers.add_parser("set-center",
                                          help="Set motor's current position as center (2048)")
    center_parser.add_argument("--motor-id", type=int, required=True,
                              help="Motor ID to center (1-5)")

    # set-center-all command
    center_all_parser = subparsers.add_parser("set-center-all",
                                              help="Set center position for all motors")

    # apply-preset command
    preset_parser = subparsers.add_parser("apply-preset", help="Apply motor preset")
    preset_parser.add_argument("--preset", type=str, default="Gentle",
                              choices=["Gentle", "Normal", "Sport"],
                              help="Preset to apply")

    # read-voltage command
    read_voltage_parser = subparsers.add_parser("read-voltage",
                                                 help="Read voltage limits from all motors")

    # fix-voltage command
    fix_voltage_parser = subparsers.add_parser("fix-voltage",
                                                help="Fix voltage limits for all motors")
    fix_voltage_parser.add_argument("--voltage", type=str, default="7.4",
                                    choices=["7.4", "12"],
                                    help="Target voltage config (default: 7.4)")
    fix_voltage_parser.add_argument("--force", action="store_true",
                                    help="Force update even if limits already match")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "scan":
            if not args.json:
                print(f"Scanning for motors on {args.port}...")
            found = scan_motors(args.port)
            if args.json:
                print(json.dumps({"motors": found}))
            else:
                print(f"\nFound {len(found)} motor(s)")
            sys.exit(0 if found else 1)

        elif args.command == "check-ids":
            if not args.json:
                print(f"Checking motor IDs on {args.port}...")
            all_present, found_ids, missing_ids, extra_ids = check_expected_ids(args.port)

            if args.json:
                print(json.dumps({
                    "all_present": all_present,
                    "found_ids": found_ids,
                    "missing_ids": missing_ids,
                    "extra_ids": extra_ids
                }))
            else:
                print(f"Found IDs: {found_ids}")
                if missing_ids:
                    print(f"Missing IDs: {missing_ids}")
                if extra_ids:
                    print(f"Extra IDs (not 1-5): {extra_ids}")
                if all_present:
                    print("All expected motor IDs (1-5) are present!")
                else:
                    print("Motor IDs are NOT fully configured")

            sys.exit(0 if all_present else 1)

        elif args.command == "id-motor":
            success = id_single_motor(args.port, args.target_id, args.force)
            sys.exit(0 if success else 1)

        elif args.command == "set-center":
            success = set_center_position(args.port, args.motor_id)
            sys.exit(0 if success else 1)

        elif args.command == "set-center-all":
            success = set_center_all(args.port)
            sys.exit(0 if success else 1)

        elif args.command == "apply-preset":
            if args.preset == "Gentle":
                success = apply_gentle_preset(args.port)
            else:
                # For other presets, use the full robot setup
                print(f"Preset {args.preset} requires full robot initialization")
                print("Use: uv run python -c \"from lelamp.follower import ...; robot.apply_preset('{args.preset}')\"")
                sys.exit(1)
            sys.exit(0 if success else 1)

        elif args.command == "read-voltage":
            if not args.json:
                print(f"Reading voltage limits from motors on {args.port}...")
            results = read_voltage_limits(args.port, verbose=not args.json)
            if args.json:
                print(json.dumps({"voltage_limits": results}))
            sys.exit(0 if results else 1)

        elif args.command == "fix-voltage":
            if not args.json:
                print(f"Fixing voltage limits on {args.port}...")
                print("")
            results = fix_voltage_limits(args.port, args.voltage, args.force, verbose=not args.json)
            if args.json:
                print(json.dumps({"results": results}))
            # Success if at least one motor was found and no failures
            success = results and all(r.get("success", False) for r in results.values())
            sys.exit(0 if success else 1)

    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
