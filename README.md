# git-blame-climate

Weather data collection tool for year-over-year trend analysis.

## Setup

```bash
# Clone and install
git clone git@github.com:xiormeesh/git-blame-climate.git
cd git-blame-climate
pip install -r requirements.txt

# Configure for your location
cp config.yaml.example config.yaml
# Edit config.yaml with your coordinates and timezone
```

## Usage

```bash
# Backfill historical data (default: from config start date to now)
python weather_data.py backfill

# Custom date range
python weather_data.py backfill --start-date 2020-01-01 --end-date 2023-12-31

# Update with recent data
python weather_data.py update

# Query the database
python weather_data.py query "SELECT COUNT(*) FROM weather_data WHERE temperature_c > 35"
```

## Example Queries

```sql
-- Days over 35°C by year
SELECT 
  strftime('%Y', timestamp) as year,
  COUNT(DISTINCT DATE(timestamp)) as days_over_35
FROM weather_data 
WHERE temperature_c > 35
GROUP BY year
ORDER BY year;

-- Average summer temperature by year
SELECT 
  strftime('%Y', timestamp) as year,
  AVG(temperature_c) as avg_temp
FROM weather_data 
WHERE strftime('%m', timestamp) IN ('06', '07', '08')
GROUP BY year
ORDER BY year;
```

## Data Source

Weather data from [Open-Meteo](https://open-meteo.com/) - free, no API key required.

## License

MIT
