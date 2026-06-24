import os
import tempfile
import sqlite3
from datetime import datetime
from unittest.mock import patch
from weather_data import backfill_command


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
