#!/usr/bin/env python3
"""
git-blame-climate - Weather data collection and analysis tool
"""
import sqlite3
import yaml
import os
import requests
import time
import argparse
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
import webbrowser


def get_table_name(location_id: str) -> str:
    """Get database table name for location.

    Args:
        location_id: Location ID from config

    Returns:
        Table name (e.g., "weather_data_santander")
    """
    return f"weather_data_{location_id}"


def get_available_locations(config: Dict[str, Any]) -> List[str]:
    """Get list of available location IDs from config.

    Args:
        config: Loaded configuration

    Returns:
        List of location IDs (e.g., ["santander", "madrid"])
    """
    if 'locations' not in config or not config['locations']:
        return []
    return [loc['id'] for loc in config['locations']]


def validate_location_id(config: Dict[str, Any], location_id: str) -> Dict[str, Any]:
    """Validate location exists in config and return location dict.

    Args:
        config: Loaded configuration
        location_id: Location ID to validate

    Returns:
        Location dictionary with id, name, latitude, longitude, timezone

    Raises:
        ValueError: If location not found in config
    """
    available = get_available_locations(config)
    if not available:
        raise ValueError(
            "No locations configured in config.yaml\n"
            "Add at least one location under 'locations:' section"
        )

    for loc in config['locations']:
        if loc['id'] == location_id:
            return loc

    raise ValueError(
        f"Location '{location_id}' not found in config.\n"
        f"Available locations: {', '.join(available)}"
    )


def calculate_backfill_years() -> List[int]:
    """Calculate 11-year range for backfill (current + 10 prior).

    Returns:
        List of years (e.g., [2016, 2017, ..., 2026] for year 2026)
    """
    current_year = datetime.now().year
    return list(range(current_year - 10, current_year + 1))


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

    created_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

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


def backfill_command(config: Dict[str, Any], start_date: str, end_date: str) -> None:
    """Backfill weather data for a date range.

    Args:
        config: Configuration dict
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    """
    db_path = config['data']['database_file']
    init_database(db_path)

    # Parse dates
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    if start >= end:
        raise ValueError("Start date must be before end date")

    # Split into 1-year (365 day) chunks
    chunks = []
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=365), end)
        chunks.append((current, chunk_end))
        current = chunk_end

    total_inserted = 0
    failed_chunks = 0

    for chunk_start, chunk_end in chunks:
        start_str = chunk_start.strftime('%Y-%m-%d')
        end_str = chunk_end.strftime('%Y-%m-%d')

        print(f"Fetching {start_str} to {end_str}...")

        try:
            records = fetch_weather_data(
                archive_url=config['api']['open_meteo']['archive_url'],
                latitude=config['location']['latitude'],
                longitude=config['location']['longitude'],
                start_date=start_str,
                end_date=end_str,
                timezone=config['location']['timezone']
            )

            inserted = insert_weather_data(db_path, records)
            total_inserted += inserted
            print(f"✓ {inserted} records inserted")

        except RuntimeError as e:
            print(f"✗ Failed to fetch chunk: {e}")
            failed_chunks += 1

    print(f"\nBackfill complete: {total_inserted} records inserted, {failed_chunks} chunks failed")


def update_command(config: Dict[str, Any]) -> None:
    """Update database with recent weather data.

    Args:
        config: Configuration dict
    """
    db_path = config['data']['database_file']
    init_database(db_path)

    # Find latest timestamp in database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(timestamp) FROM weather_data")
    result = cursor.fetchone()
    conn.close()

    if result[0] is None:
        print("Database is empty. Please run backfill first:")
        print("  python weather_data.py backfill")
        return

    last_timestamp = result[0]
    last_date = datetime.strptime(last_timestamp, '%Y-%m-%d %H:%M:%S')
    today = datetime.now()

    # Determine which API to use
    days_since_last = (today - last_date).days

    if days_since_last == 0:
        print("Database is already up to date")
        return

    print(f"Updating from {last_date.strftime('%Y-%m-%d')} to today...")

    total_inserted = 0

    # Use forecast API for last 16 days, archive for older
    if days_since_last <= 16:
        # Recent data - use forecast API
        try:
            records = fetch_weather_data(
                archive_url=config['api']['open_meteo']['forecast_url'],
                latitude=config['location']['latitude'],
                longitude=config['location']['longitude'],
                start_date=last_date.strftime('%Y-%m-%d'),
                end_date=today.strftime('%Y-%m-%d'),
                timezone=config['location']['timezone']
            )

            inserted = insert_weather_data(db_path, records)
            total_inserted += inserted
            print(f"✓ {inserted} records inserted from forecast API")

        except RuntimeError as e:
            print(f"✗ Failed to fetch recent data: {e}")
    else:
        # Older gap - use archive API with chunking
        backfill_command(config, last_date.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))
        return

    print(f"\nUpdate complete: {total_inserted} records inserted")


def query_command(config: Dict[str, Any], sql: str) -> None:
    """Execute SQL query and print results.

    Args:
        config: Configuration dict
        sql: SQL query string
    """
    db_path = config['data']['database_file']

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("Run backfill first to create database")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(sql)
        results = cursor.fetchall()

        # Print column names
        if cursor.description:
            col_names = [desc[0] for desc in cursor.description]
            print(' | '.join(col_names))
            print('-' * (len(' | '.join(col_names))))

        # Print rows
        for row in results:
            print(' | '.join(str(val) for val in row))

        print(f"\n{len(results)} row(s) returned")

    except sqlite3.Error as e:
        print(f"SQL error: {e}")
    finally:
        conn.close()


def visualize_command(config: Dict[str, Any]) -> None:
    """Generate interactive temperature visualization.

    Args:
        config: Configuration dict containing database_file path
    """
    db_path = config['data']['database_file']

    if not os.path.exists(db_path):
        print("Error: No weather data found in database.")
        print("Run 'python weather_data.py backfill' first.")
        return

    # Query database for daily max temperatures
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                strftime('%Y', timestamp) as year,
                strftime('%j', timestamp) as day_of_year,
                MAX(temperature_c) as max_temp
            FROM weather_data
            GROUP BY year, day_of_year
            ORDER BY year, day_of_year
        """)

        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        conn.close()
        print("Error: No weather data found in database.")
        print("Run 'python weather_data.py backfill' first.")
        return

    conn.close()

    if not rows:
        print("Error: No weather data found in database.")
        print("Run 'python weather_data.py backfill' first.")
        return

    # Process data into year-grouped structure
    year_data = {}
    for year_str, day_str, temp in rows:
        day_num = int(day_str)

        # Skip Feb 29 (day 60) for leap years to maintain 365-day axis
        if day_num == 60:
            # Check if leap year
            year_int = int(year_str)
            is_leap = (year_int % 4 == 0 and year_int % 100 != 0) or (year_int % 400 == 0)
            if is_leap:
                continue  # Skip Feb 29

        # Adjust day numbers after Feb 29 for leap years
        if day_num > 60:
            year_int = int(year_str)
            is_leap = (year_int % 4 == 0 and year_int % 100 != 0) or (year_int % 400 == 0)
            if is_leap:
                day_num -= 1  # Shift down by 1

        if year_str not in year_data:
            year_data[year_str] = []

        year_data[year_str].append((day_num, temp))

    # Create plotly figure
    fig = go.Figure()

    # Add one trace per year
    for year in sorted(year_data.keys()):
        data = year_data[year]
        days = [d for d, t in data]
        temps = [t for d, t in data]

        fig.add_trace(go.Scatter(
            x=days,
            y=temps,
            mode='lines',
            name=year,
            hovertemplate='Day %{x}<br>%{y:.1f}°C<extra></extra>'
        ))

    # Configure layout
    fig.update_layout(
        title='Daily Maximum Temperature (2016-2026)',
        xaxis_title='Date',
        yaxis_title='Temperature (°C)',
        hovermode='x unified',
        legend_title='Year (click to toggle)',
        width=1200,
        height=600
    )

    # X-axis: Month labels at month boundaries
    fig.update_xaxes(
        tickmode='array',
        tickvals=[1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335],
        ticktext=['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    )

    # Save to HTML file
    output_file = 'temperature_chart.html'
    try:
        fig.write_html(output_file)
        print(f"Chart saved to {output_file}")
    except IOError as e:
        print(f"Error: Cannot write to {output_file}")
        print(f"Check file permissions in current directory.")
        return

    # Auto-open in browser
    try:
        file_url = f'file://{os.path.abspath(output_file)}'
        webbrowser.open(file_url)
        print("Opening chart in browser...")
    except Exception:
        print("Could not auto-open browser. Open the file manually.")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='git-blame-climate - Weather data collection tool'
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Backfill command
    backfill_parser = subparsers.add_parser('backfill', help='Backfill historical weather data')
    backfill_parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    backfill_parser.add_argument('--end-date', help='End date (YYYY-MM-DD, defaults to today)')

    # Update command (placeholder for next task)
    update_parser = subparsers.add_parser('update', help='Update with recent weather data')

    # Query command (placeholder for next task)
    query_parser = subparsers.add_parser('query', help='Run SQL query on database')
    query_parser.add_argument('sql', help='SQL query to execute')

    # Visualize command
    visualize_parser = subparsers.add_parser('visualize',
        help='Generate interactive temperature visualization')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Load config
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(str(e))
        return

    try:
        if args.command == 'backfill':
            start_date = args.start_date or config['data']['backfill_start_date']
            end_date = args.end_date or datetime.now().strftime('%Y-%m-%d')

            backfill_command(config, start_date, end_date)

        elif args.command == 'update':
            update_command(config)

        elif args.command == 'query':
            query_command(config, args.sql)

        elif args.command == 'visualize':
            visualize_command(config)

    except ValueError as e:
        print(f"Error: {e}")
        return


if __name__ == '__main__':
    main()
