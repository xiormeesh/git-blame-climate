import os
import tempfile
import sqlite3
from datetime import datetime
from unittest.mock import patch
import io
import sys
from weather_data import backfill_command, update_command, init_database, insert_weather_data


def test_backfill_command_single_chunk():
    """Test backfill with date range < 1 year (single chunk)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')

        config = {
            'location': {
                'latitude': 40.0,
                'longitude': -3.0,
                'timezone': 'Europe/Madrid'
            },
            'data': {
                'database_file': db_path
            },
            'api': {
                'open_meteo': {
                    'archive_url': 'https://test.com/api'
                }
            }
        }

        # Mock API response
        mock_records = [
            {
                'timestamp': '2021-06-01 00:00:00',
                'temperature_c': 20.0,
                'precipitation_mm': 0.0,
                'wind_speed_kmh': 10.0,
                'relative_humidity': 60.0,
                'source': 'open-meteo',
                'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            }
        ]

        with patch('weather_data.fetch_weather_data', return_value=mock_records):
            backfill_command(config, '2021-06-01', '2021-06-02')

        # Verify data inserted
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM weather_data")
        count = cursor.fetchone()[0]
        assert count == 1
        conn.close()


def test_backfill_command_multiple_chunks():
    """Test backfill with date range > 1 year (multiple chunks)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')

        config = {
            'location': {
                'latitude': 40.0,
                'longitude': -3.0,
                'timezone': 'Europe/Madrid'
            },
            'data': {
                'database_file': db_path
            },
            'api': {
                'open_meteo': {
                    'archive_url': 'https://test.com/api'
                }
            }
        }

        mock_records = [{'timestamp': '2020-01-01 00:00:00', 'temperature_c': 15.0,
                        'precipitation_mm': 0.0, 'wind_speed_kmh': 5.0,
                        'relative_humidity': 50.0, 'source': 'open-meteo',
                        'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}]

        with patch('weather_data.fetch_weather_data', return_value=mock_records) as mock_fetch:
            backfill_command(config, '2020-01-01', '2022-06-01')

            # Should be called multiple times (one per chunk)
            assert mock_fetch.call_count > 1


def test_update_command_with_existing_data():
    """Test update fetches from last timestamp to now."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')

        # Insert some existing data
        init_database(db_path)

        existing = [{
            'timestamp': '2021-06-01 12:00:00',
            'temperature_c': 20.0,
            'precipitation_mm': 0.0,
            'wind_speed_kmh': 10.0,
            'relative_humidity': 60.0,
            'source': 'open-meteo',
            'created_at': '2021-06-01 13:00:00'
        }]
        insert_weather_data(db_path, existing)

        config = {
            'location': {'latitude': 40.0, 'longitude': -3.0, 'timezone': 'Europe/Madrid'},
            'data': {'database_file': db_path},
            'api': {'open_meteo': {
                'archive_url': 'https://test.com/archive',
                'forecast_url': 'https://test.com/forecast'
            }}
        }

        new_records = [{
            'timestamp': '2021-06-02 12:00:00',
            'temperature_c': 22.0,
            'precipitation_mm': 0.5,
            'wind_speed_kmh': 12.0,
            'relative_humidity': 65.0,
            'source': 'open-meteo',
            'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }]

        with patch('weather_data.fetch_weather_data', return_value=new_records):
            update_command(config)

        # Verify new data added
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM weather_data")
        assert cursor.fetchone()[0] == 2
        conn.close()


def test_update_command_empty_database():
    """Test update with empty database suggests backfill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')

        config = {
            'location': {'latitude': 40.0, 'longitude': -3.0, 'timezone': 'Europe/Madrid'},
            'data': {'database_file': db_path},
            'api': {'open_meteo': {
                'archive_url': 'https://test.com/archive',
                'forecast_url': 'https://test.com/forecast'
            }}
        }

        captured = io.StringIO()
        sys.stdout = captured

        update_command(config)

        sys.stdout = sys.__stdout__
        output = captured.getvalue()

        assert 'run backfill first' in output.lower()
