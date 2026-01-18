import argparse
import os
import glob
import csv
from datetime import datetime


def list_recordings():
    """List all recordings."""
    # Get the recordings directory path
    recordings_dir = os.path.join(os.path.dirname(__file__), "recordings")

    if not os.path.exists(recordings_dir):
        print(f"No recordings directory found at {recordings_dir}")
        return

    # Pattern to match all recordings
    pattern = os.path.join(recordings_dir, "*.csv")
    recording_files = glob.glob(pattern)

    if not recording_files:
        print("No recordings found")
        return

    print("Available recordings:")
    print()

    for file_path in sorted(recording_files):
        filename = os.path.basename(file_path)
        recording_name = filename.replace(".csv", "")

        # Count rows in CSV file
        try:
            with open(file_path, 'r') as csvfile:
                reader = csv.reader(csvfile)
                row_count = sum(1 for row in reader) - 1  # Subtract header row
        except Exception as e:
            row_count = "Error reading file"

        # Get modified time
        stat = os.stat(file_path)
        modified_time = datetime.fromtimestamp(stat.st_mtime)

        print(f"{recording_name}")
        print(f"  File: {filename}")
        print(f"  Rows: {row_count}")
        print()


def main():
    parser = argparse.ArgumentParser(description="List available recordings")
    parser.parse_args()

    list_recordings()


if __name__ == "__main__":
    main()