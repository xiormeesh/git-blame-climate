import os
import tempfile
import io
import sys
from weather_data import query_command, init_database, insert_weather_data
from datetime import datetime, timezone

def test_query_command():
    """Test query command executes SQL and prints results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')

        # Setup database with test data
        init_database(db_path)
        records = [
            {
                'timestamp': '2021-06-01 12:00:00',
                'temperature_c': 30.0,
                'precipitation_mm': 0.0,
                'wind_speed_kmh': 10.0,
                'relative_humidity': 60.0,
                'source': 'open-meteo',
                'created_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'timestamp': '2021-06-01 13:00:00',
                'temperature_c': 36.0,
                'precipitation_mm': 0.0,
                'wind_speed_kmh': 12.0,
                'relative_humidity': 55.0,
                'source': 'open-meteo',
                'created_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            }
        ]
        insert_weather_data(db_path, records)

        config = {'data': {'database_file': db_path}}

        # Capture stdout
        captured = io.StringIO()
        sys.stdout = captured

        query_command(config, "SELECT COUNT(*) FROM weather_data WHERE temperature_c > 35")

        sys.stdout = sys.__stdout__
        output = captured.getvalue()

        assert '1' in output  # One record over 35°C
