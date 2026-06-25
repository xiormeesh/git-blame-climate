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


def init_database(db_path: str, locations: List[Dict[str, Any]]) -> None:
    """Initialize SQLite database with one table per location.

    Args:
        db_path: Path to SQLite database file
        locations: List of location dicts from config (each with 'id' field)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for location in locations:
        location_id = location['id']
        table_name = get_table_name(location_id)

        # Create table for this location
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                timestamp TEXT PRIMARY KEY,
                temperature_c REAL NOT NULL,
                precipitation_mm REAL NOT NULL,
                wind_speed_kmh REAL,
                relative_humidity REAL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Create indexes for this location
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_timestamp_{location_id} ON {table_name}(timestamp)")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_date_{location_id} ON {table_name}(DATE(timestamp))")

    conn.commit()
    conn.close()


def insert_weather_data(db_path: str, location_id: str, records: List[Dict[str, Any]]) -> int:
    """Insert weather data records into location-specific table.

    Args:
        db_path: Path to SQLite database
        location_id: Location ID (determines table name)
        records: List of dicts with keys: timestamp, temperature_c, precipitation_mm,
                 wind_speed_kmh, relative_humidity, source, created_at

    Returns:
        Number of records inserted (excludes duplicates)
    """
    if not records:
        return 0

    table_name = get_table_name(location_id)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    inserted = 0
    for record in records:
        try:
            cursor.execute(f"""
                INSERT OR IGNORE INTO {table_name}
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
    """Load and validate configuration from YAML file.

    Args:
        config_path: Path to config.yaml

    Returns:
        Configuration dictionary with validated locations list

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config format is invalid or required fields missing
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            "Run: cp config.yaml.example config.yaml and edit with your settings"
        )

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Check for old single-location format
    if 'location' in config and 'locations' not in config:
        raise ValueError(
            "Invalid config format\n"
            "Expected 'locations:' (list), found 'location:' (dict)\n\n"
            "Migration required:\n"
            "1. Rename 'location:' to 'locations:'\n"
            "2. Convert to list format:\n"
            "   locations:\n"
            "     - id: \"santander\"\n"
            "       name: \"Santander\"\n"
            "       ...\n"
            "3. Re-run backfill command"
        )

    # Validate locations list exists
    if 'locations' not in config:
        raise ValueError(
            "Missing 'locations' section in config.yaml\n"
            "Add at least one location under 'locations:' section"
        )

    if not isinstance(config['locations'], list):
        raise ValueError("'locations' must be a list")

    if len(config['locations']) == 0:
        raise ValueError(
            "No locations configured in config.yaml\n"
            "Add at least one location under 'locations:' section\n\n"
            "Example:\n"
            "locations:\n"
            "  - id: \"madrid\"\n"
            "    name: \"Madrid\"\n"
            "    latitude: 40.4168\n"
            "    longitude: -3.7038\n"
            "    timezone: \"Europe/Madrid\""
        )

    # Validate each location has required fields
    required_fields = ['id', 'name', 'latitude', 'longitude', 'timezone']
    location_ids = set()

    for i, location in enumerate(config['locations']):
        # Check required fields
        for field in required_fields:
            if field not in location:
                raise ValueError(f"locations[{i}].{field} is required")

        # Check for duplicate IDs
        loc_id = location['id']
        if loc_id in location_ids:
            raise ValueError(f"Duplicate location ID: '{loc_id}' appears multiple times")
        location_ids.add(loc_id)

        # Validate latitude/longitude ranges
        if not (-90 <= location['latitude'] <= 90):
            raise ValueError(f"locations[{i}].latitude must be between -90 and 90")
        if not (-180 <= location['longitude'] <= 180):
            raise ValueError(f"locations[{i}].longitude must be between -180 and 180")

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


def backfill_command(config: Dict[str, Any]) -> None:
    """Backfill historical weather data for all locations.

    Fetches 11 years of data (current year + 10 prior full years) for each
    location configured in config.yaml.

    Args:
        config: Configuration dictionary with locations list
    """
    db_path = config['data']['database_file']
    locations = config['locations']

    # Initialize database with tables for all locations
    init_database(db_path, locations)

    # Calculate 11-year range
    years = calculate_backfill_years()
    start_year = years[0]
    end_year = years[-1]

    # Backfill each location
    for location in locations:
        location_id = location['id']
        location_name = location['name']

        print(f"\nBackfilling {location_name} ({start_year}-{end_year})...")
        total_inserted = 0

        for year in years:
            # Calculate date range for this year
            start_date = f"{year}-01-01"

            # For current year, only fetch through today
            current_year = datetime.now().year
            if year == current_year:
                end_date = datetime.now().strftime("%Y-%m-%d")
            else:
                end_date = f"{year}-12-31"

            # Fetch data for this year
            records = fetch_weather_data(
                archive_url=config['api']['open_meteo']['archive_url'],
                latitude=location['latitude'],
                longitude=location['longitude'],
                start_date=start_date,
                end_date=end_date,
                timezone=location['timezone']
            )

            # Insert records
            inserted = insert_weather_data(db_path, location_id, records)
            total_inserted += inserted

            # Show progress
            if year == current_year:
                print(f"  Fetching {year}... {inserted} records inserted (through {end_date})")
            else:
                print(f"  Fetching {year}... {inserted} records inserted")

        print(f"Total: {total_inserted} records inserted for {location_name}")

    print(f"\nAll locations backfilled successfully.")


def update_command(config: Dict[str, Any]) -> None:
    """Update database with recent weather data.

    Args:
        config: Configuration dict
    """
    db_path = config['data']['database_file']
    init_database(db_path, config['locations'])

    today = datetime.now()
    total_inserted = 0

    for location in config['locations']:
        location_id = location['id']
        table_name = get_table_name(location_id)

        # Find latest timestamp in this location's table
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT MAX(timestamp) FROM {table_name}")
        result = cursor.fetchone()
        conn.close()

        if result[0] is None:
            print(f"{location_id}: Database is empty. Please run backfill first.")
            continue

        last_timestamp = result[0]
        last_date = datetime.strptime(last_timestamp, '%Y-%m-%d %H:%M:%S')

        # Determine which API to use
        days_since_last = (today - last_date).days

        if days_since_last == 0:
            print(f"{location_id}: Already up to date")
            continue

        print(f"Updating {location_id} from {last_date.strftime('%Y-%m-%d')} to today...")

        # Use forecast API for last 16 days, archive for older
        if days_since_last <= 16:
            # Recent data - use forecast API
            try:
                records = fetch_weather_data(
                    archive_url=config['api']['open_meteo']['forecast_url'],
                    latitude=location['latitude'],
                    longitude=location['longitude'],
                    start_date=last_date.strftime('%Y-%m-%d'),
                    end_date=today.strftime('%Y-%m-%d'),
                    timezone=location['timezone']
                )

                inserted = insert_weather_data(db_path, location_id, records)
                total_inserted += inserted
                print(f"✓ {inserted} records inserted from forecast API")

            except RuntimeError as e:
                print(f"✗ Failed to fetch recent data: {e}")
        else:
            # Older gap - use archive API with chunking
            print(f"Fetching {days_since_last} days of data from archive API...")
            try:
                # Split into 1-year chunks
                current = last_date
                while current < today:
                    chunk_end = min(current + timedelta(days=365), today)
                    start_str = current.strftime('%Y-%m-%d')
                    end_str = chunk_end.strftime('%Y-%m-%d')

                    records = fetch_weather_data(
                        archive_url=config['api']['open_meteo']['archive_url'],
                        latitude=location['latitude'],
                        longitude=location['longitude'],
                        start_date=start_str,
                        end_date=end_str,
                        timezone=location['timezone']
                    )

                    inserted = insert_weather_data(db_path, location_id, records)
                    total_inserted += inserted
                    print(f"✓ {start_str} to {end_str}: {inserted} records inserted")
                    current = chunk_end

            except RuntimeError as e:
                print(f"✗ Failed to fetch archive data: {e}")

    print(f"\nUpdate complete: {total_inserted} records inserted")


def query_command(config: Dict[str, Any], location_id: str, sql: str) -> None:
    """Execute arbitrary SQL query on location-specific table.

    Args:
        config: Configuration dictionary
        location_id: Location ID (validates against config)
        sql: SQL query string (user must specify full table name)

    Raises:
        ValueError: If location_id not found in config
    """
    # Validate location exists
    try:
        validate_location_id(config, location_id)
    except ValueError as e:
        print(f"Error: {e}")
        return

    db_path = config['data']['database_file']

    if not os.path.exists(db_path):
        print(f"Error: Database not found: {db_path}")
        print("Run 'python weather_data.py backfill' first.")
        return

    # Execute query
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(sql)
        results = cursor.fetchall()

        # Print results
        for row in results:
            print(row)

        if not results:
            print("(no results)")

    except sqlite3.Error as e:
        print(f"SQL error: {e}")

    finally:
        conn.close()


def visualize_command(config: Dict[str, Any], location_id: str) -> None:
    """Generate interactive temperature visualization for specified location.

    Shows 11 years of daily max temperatures (current year + 10 prior full years).

    Args:
        config: Configuration dictionary
        location_id: Location ID to visualize

    Raises:
        ValueError: If location_id not found in config
    """
    # Validate location exists
    try:
        location = validate_location_id(config, location_id)
    except ValueError as e:
        print(f"Error: {e}")
        return

    location_name = location['name']
    table_name = get_table_name(location_id)
    db_path = config['data']['database_file']

    if not os.path.exists(db_path):
        print(f"Error: No weather data found in database.")
        print("Run 'python weather_data.py backfill' first.")
        return

    # Calculate year range (11 years: current + 10 prior)
    years = calculate_backfill_years()
    start_year = years[0]
    end_year = years[-1]

    print(f"Querying weather data for {location_name} ({start_year}-{end_year})...")

    # Query database for daily max temperatures
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(f"""
            SELECT
                strftime('%Y', timestamp) as year,
                strftime('%j', timestamp) as day_of_year,
                MAX(temperature_c) as max_temp
            FROM {table_name}
            GROUP BY year, day_of_year
            ORDER BY year, day_of_year
        """)
    except sqlite3.OperationalError as e:
        conn.close()
        print(f"Error: No weather data found for {location_name}.")
        print("Run 'python weather_data.py backfill' first.")
        return

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print(f"Error: No weather data found for {location_name}.")
        print("Run 'python weather_data.py backfill' first.")
        return

    print("Generating chart...")

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
        title=f'Daily Maximum Temperature - {location_name} ({start_year}-{end_year})',
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

    # Save to HTML file with location in filename
    output_file = f'temperature_chart_{location_id}.html'
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
    backfill_parser = subparsers.add_parser('backfill', help='Backfill historical weather data (11 years)')

    # Update command (placeholder for next task)
    update_parser = subparsers.add_parser('update', help='Update with recent weather data')

    # Query command
    query_parser = subparsers.add_parser('query',
        help='Run SQL query on weather database')
    query_parser.add_argument('--location', required=True,
        help='Location ID to query')
    query_parser.add_argument('sql', help='SQL query to execute')

    # Visualize command
    visualize_parser = subparsers.add_parser('visualize',
        help='Generate interactive temperature visualization')
    visualize_parser.add_argument('--location', required=True,
        help='Location ID to visualize')

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
            backfill_command(config)

        elif args.command == 'update':
            update_command(config)

        elif args.command == 'query':
            if not hasattr(args, 'location') or args.location is None:
                available = get_available_locations(config)
                print("Error: --location flag is required")
                print(f"Available locations: {', '.join(available)}")
                print("\nUsage: python weather_data.py query --location <location_id> \"<SQL>\"")
                return
            query_command(config, args.location, args.sql)

        elif args.command == 'visualize':
            if not hasattr(args, 'location') or args.location is None:
                available = get_available_locations(config)
                print("Error: --location flag is required")
                print(f"Available locations: {', '.join(available)}")
                print("\nUsage: python weather_data.py visualize --location <location_id>")
                return
            visualize_command(config, args.location)

    except ValueError as e:
        print(f"Error: {e}")
        return


if __name__ == '__main__':
    main()
