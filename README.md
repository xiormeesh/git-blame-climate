# git-blame-climate

Weather data collection tool for year-over-year trend analysis.

## Setup

```bash
# Clone and install
git clone git@github.com:xiormeesh/git-blame-climate.git
cd git-blame-climate
uv sync

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

## Advanced Examples

### Heat wave analysis
```sql
-- Days over 35°C by year
SELECT 
  strftime('%Y', timestamp) as year,
  COUNT(DISTINCT DATE(timestamp)) as days_over_35
FROM weather_data 
WHERE temperature_c > 35
GROUP BY year
ORDER BY year;
```

### Summer comparison
```sql
-- Average summer temperature (June-August) by year
SELECT 
  strftime('%Y', timestamp) as year,
  AVG(temperature_c) as avg_summer_temp,
  MAX(temperature_c) as max_temp,
  SUM(precipitation_mm) as total_rain_mm
FROM weather_data 
WHERE strftime('%m', timestamp) IN ('06', '07', '08')
GROUP BY year
ORDER BY year;
```

### Precipitation trends
```sql
-- Total rainfall by month
SELECT 
  strftime('%Y-%m', timestamp) as month,
  SUM(precipitation_mm) as total_mm
FROM weather_data 
GROUP BY month
ORDER BY month;
```

### Wind patterns
```sql
-- Average wind speed by hour of day
SELECT 
  strftime('%H', timestamp) as hour,
  AVG(wind_speed_kmh) as avg_wind_kmh
FROM weather_data 
WHERE wind_speed_kmh IS NOT NULL
GROUP BY hour
ORDER BY hour;
```

## Troubleshooting

**"config.yaml not found"**
- Run `cp config.yaml.example config.yaml`
- Edit the new file with your location coordinates

**"Database is empty. Please run backfill first"**
- The `update` command requires existing data
- Run `python weather_data.py backfill` first

**API fetch failures**
- Check internet connection
- Open-Meteo may have rate limits - wait a few minutes
- The tool automatically retries 3 times, so transient failures are handled

**Want to start over?**
- Delete `weather.db`
- Run backfill again

## Finding Your Coordinates

1. Visit [openstreetmap.org](https://www.openstreetmap.org/)
2. Search for your city
3. Right-click the location and select "Show address"
4. Copy the latitude and longitude
5. Update `config.yaml` with these values

Timezone should match your location (e.g., "Europe/Madrid", "America/New_York").

## Data Source

Weather data from [Open-Meteo](https://open-meteo.com/) - free, no API key required.

## License

MIT
