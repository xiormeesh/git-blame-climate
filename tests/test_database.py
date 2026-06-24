import sqlite3
import os
import tempfile
import yaml
from weather_data import init_database, insert_weather_data, load_config


def test_init_database_creates_table():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        init_database(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='weather_data'")
        assert cursor.fetchone() is not None

        # Check columns
        cursor.execute("PRAGMA table_info(weather_data)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert columns['timestamp'] == 'TEXT'
        assert columns['temperature_c'] == 'REAL'
        assert columns['precipitation_mm'] == 'REAL'
        assert columns['wind_speed_kmh'] == 'REAL'
        assert columns['relative_humidity'] == 'REAL'
        assert columns['source'] == 'TEXT'
        assert columns['created_at'] == 'TEXT'

        # Check indexes exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        assert 'idx_timestamp' in indexes
        assert 'idx_date' in indexes

        conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_init_database_idempotent():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        init_database(db_path)
        init_database(db_path)  # Should not error

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='weather_data'")
        assert cursor.fetchone() is not None
        conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_insert_weather_data():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        init_database(db_path)

        records = [
            {
                'timestamp': '2021-06-01 12:00:00',
                'temperature_c': 25.5,
                'precipitation_mm': 0.0,
                'wind_speed_kmh': 12.3,
                'relative_humidity': 65.0,
                'source': 'open-meteo',
                'created_at': '2026-06-24 10:00:00'
            },
            {
                'timestamp': '2021-06-01 13:00:00',
                'temperature_c': 26.2,
                'precipitation_mm': 0.1,
                'wind_speed_kmh': None,  # Test nullable
                'relative_humidity': None,  # Test nullable
                'source': 'open-meteo',
                'created_at': '2026-06-24 10:00:00'
            }
        ]

        count = insert_weather_data(db_path, records)
        assert count == 2

        # Verify data
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM weather_data")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT * FROM weather_data WHERE timestamp='2021-06-01 12:00:00'")
        row = cursor.fetchone()
        assert row[1] == 25.5  # temperature_c
        assert row[3] == 12.3  # wind_speed_kmh

        cursor.execute("SELECT * FROM weather_data WHERE timestamp='2021-06-01 13:00:00'")
        row = cursor.fetchone()
        assert row[3] is None  # wind_speed_kmh

        conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_insert_weather_data_ignores_duplicates():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        init_database(db_path)

        records = [
            {
                'timestamp': '2021-06-01 12:00:00',
                'temperature_c': 25.5,
                'precipitation_mm': 0.0,
                'wind_speed_kmh': 12.3,
                'relative_humidity': 65.0,
                'source': 'open-meteo',
                'created_at': '2026-06-24 10:00:00'
            }
        ]

        count1 = insert_weather_data(db_path, records)
        assert count1 == 1

        count2 = insert_weather_data(db_path, records)  # Same record
        assert count2 == 0  # Should be ignored

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM weather_data")
        assert cursor.fetchone()[0] == 1
        conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_load_config_success():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_path = f.name
        yaml.dump({
            'location': {
                'name': 'Test City',
                'latitude': 40.0,
                'longitude': -3.0,
                'timezone': 'Europe/Madrid'
            },
            'data': {
                'backfill_start_date': '2020-01-01',
                'database_file': 'test.db'
            },
            'api': {
                'open_meteo': {
                    'archive_url': 'https://archive-api.open-meteo.com/v1/archive',
                    'forecast_url': 'https://api.open-meteo.com/v1/forecast'
                }
            }
        }, f)

    try:
        config = load_config(config_path)
        assert config['location']['name'] == 'Test City'
        assert config['location']['latitude'] == 40.0
        assert config['data']['database_file'] == 'test.db'
    finally:
        if os.path.exists(config_path):
            os.unlink(config_path)


def test_load_config_missing_file():
    try:
        load_config('/nonexistent/config.yaml')
        assert False, "Should raise FileNotFoundError"
    except FileNotFoundError as e:
        assert 'config.yaml not found' in str(e)
