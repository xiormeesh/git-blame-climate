#!/usr/bin/env python3
"""
git-blame-climate - Weather data collection and analysis tool
"""
import sqlite3
import yaml
import os
from typing import List, Dict, Any
from datetime import datetime


def init_database(db_path: str) -> None:
    """Initialize SQLite database with schema if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_data (
            timestamp TEXT PRIMARY KEY,
            temperature_c REAL NOT NULL,
            precipitation_mm REAL NOT NULL,
            wind_speed_kmh REAL,
            relative_humidity REAL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON weather_data(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON weather_data(DATE(timestamp))")

    conn.commit()
    conn.close()


def insert_weather_data(db_path: str, records: List[Dict[str, Any]]) -> int:
    """Insert weather data records into database.

    Args:
        db_path: Path to SQLite database
        records: List of dicts with keys: timestamp, temperature_c, precipitation_mm,
                 wind_speed_kmh, relative_humidity, source, created_at

    Returns:
        Number of records inserted (excludes duplicates)
    """
    if not records:
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    inserted = 0
    for record in records:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO weather_data
                (timestamp, temperature_c, precipitation_mm, wind_speed_kmh,
                 relative_humidity, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                record['timestamp'],
                record['temperature_c'],
                record['precipitation_mm'],
                record['wind_speed_kmh'],
                record['relative_humidity'],
                record['source'],
                record['created_at']
            ))
            if cursor.rowcount > 0:
                inserted += 1
        except sqlite3.IntegrityError:
            # Duplicate timestamp, skip
            pass

    conn.commit()
    conn.close()
    return inserted


def load_config(config_path: str = 'config.yaml') -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"config.yaml not found at {config_path}\n\n"
            "First-time setup:\n"
            "  cp config.yaml.example config.yaml\n"
            "  # Edit config.yaml with your location\n"
        )

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    return config
