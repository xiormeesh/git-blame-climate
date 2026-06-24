#!/usr/bin/env python3
"""
git-blame-climate - Weather data collection and analysis tool
"""
import sqlite3
import yaml
import os
import requests
import time
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


def fetch_weather_data(
    archive_url: str,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    timezone: str
) -> List[Dict[str, Any]]:
    """Fetch weather data from Open-Meteo API with retry logic.

    Args:
        archive_url: Open-Meteo archive API URL
        latitude: Location latitude
        longitude: Location longitude
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        timezone: Timezone (e.g., 'Europe/Madrid')

    Returns:
        List of weather records as dicts

    Raises:
        RuntimeError: If all retries fail
    """
    params = {
        'latitude': latitude,
        'longitude': longitude,
        'start_date': start_date,
        'end_date': end_date,
        'hourly': 'temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m',
        'timezone': timezone
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(archive_url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                return _parse_weather_response(data)

            # Non-200 status, will retry
            if attempt < max_retries - 1:
                sleep_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                time.sleep(sleep_time)
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                sleep_time = 2 ** attempt
                time.sleep(sleep_time)
            else:
                raise RuntimeError(f"Failed to fetch weather data after {max_retries} retries: {e}")

    raise RuntimeError(f"Failed to fetch weather data: HTTP {response.status_code}")


def _parse_weather_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse Open-Meteo API response into database records.

    Args:
        data: API response JSON

    Returns:
        List of weather records
    """
    hourly = data['hourly']
    times = hourly['time']
    temps = hourly['temperature_2m']
    precip = hourly['precipitation']
    wind = hourly.get('wind_speed_10m', [None] * len(times))
    humidity = hourly.get('relative_humidity_2m', [None] * len(times))

    created_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    records = []
    for i in range(len(times)):
        # Convert ISO format to database format
        timestamp = times[i].replace('T', ' ')
        if '+' in timestamp:
            timestamp = timestamp.split('+')[0]
        # Ensure seconds are included (add :00 if only HH:MM)
        if timestamp.count(':') == 1:
            timestamp += ':00'

        records.append({
            'timestamp': timestamp,
            'temperature_c': temps[i],
            'precipitation_mm': precip[i],
            'wind_speed_kmh': wind[i],
            'relative_humidity': humidity[i],
            'source': 'open-meteo',
            'created_at': created_at
        })

    return records
