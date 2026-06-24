import json
from unittest.mock import patch, Mock
from weather_data import fetch_weather_data

def test_fetch_weather_data_success():
    mock_response = {
        'hourly': {
            'time': ['2021-06-01T00:00', '2021-06-01T01:00'],
            'temperature_2m': [18.5, 18.2],
            'precipitation': [0.0, 0.1],
            'wind_speed_10m': [12.3, 11.8],
            'relative_humidity_2m': [65, 67]
        }
    }

    with patch('requests.get') as mock_get:
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: mock_response
        )

        records = fetch_weather_data(
            archive_url='https://archive-api.open-meteo.com/v1/archive',
            latitude=43.46,
            longitude=-3.80,
            start_date='2021-06-01',
            end_date='2021-06-01',
            timezone='Europe/Madrid'
        )

        assert len(records) == 2
        assert records[0]['timestamp'] == '2021-06-01 00:00:00'
        assert records[0]['temperature_c'] == 18.5
        assert records[0]['precipitation_mm'] == 0.0
        assert records[0]['wind_speed_kmh'] == 12.3
        assert records[0]['relative_humidity'] == 65
        assert records[0]['source'] == 'open-meteo'
        assert 'created_at' in records[0]

def test_fetch_weather_data_with_nulls():
    mock_response = {
        'hourly': {
            'time': ['2021-06-01T00:00'],
            'temperature_2m': [18.5],
            'precipitation': [0.0],
            'wind_speed_10m': [None],
            'relative_humidity_2m': [None]
        }
    }

    with patch('requests.get') as mock_get:
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: mock_response
        )

        records = fetch_weather_data(
            archive_url='https://test.com/api',
            latitude=43.46,
            longitude=-3.80,
            start_date='2021-06-01',
            end_date='2021-06-01',
            timezone='Europe/Madrid'
        )

        assert records[0]['wind_speed_kmh'] is None
        assert records[0]['relative_humidity'] is None

def test_fetch_weather_data_retries_on_failure():
    with patch('requests.get') as mock_get:
        # Fail twice, succeed on third
        mock_get.side_effect = [
            Mock(status_code=500),
            Mock(status_code=500),
            Mock(status_code=200, json=lambda: {
                'hourly': {
                    'time': ['2021-06-01T00:00'],
                    'temperature_2m': [18.5],
                    'precipitation': [0.0],
                    'wind_speed_10m': [12.3],
                    'relative_humidity_2m': [65]
                }
            })
        ]

        with patch('time.sleep'):  # Don't actually sleep in tests
            records = fetch_weather_data(
                archive_url='https://test.com/api',
                latitude=43.46,
                longitude=-3.80,
                start_date='2021-06-01',
                end_date='2021-06-01',
                timezone='Europe/Madrid'
            )

        assert len(records) == 1
        assert mock_get.call_count == 3

def test_fetch_weather_data_fails_after_retries():
    with patch('requests.get') as mock_get:
        mock_get.return_value = Mock(status_code=500)

        with patch('time.sleep'):
            try:
                fetch_weather_data(
                    archive_url='https://test.com/api',
                    latitude=43.46,
                    longitude=-3.80,
                    start_date='2021-06-01',
                    end_date='2021-06-01',
                    timezone='Europe/Madrid'
                )
                assert False, "Should raise RuntimeError"
            except RuntimeError as e:
                assert 'Failed to fetch' in str(e)

        assert mock_get.call_count == 3
