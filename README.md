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
# Sync weather data (smart fetch for all locations)
# First run: fetches 11 years (current year + 10 prior)
# Subsequent runs: fetches only new data since last sync
python weather_data.py sync

# Query a specific location's database
python weather_data.py query --location madrid "SELECT COUNT(*) FROM weather_data_madrid WHERE temperature_c > 35"

# Visualize temperature trends for a location
python weather_data.py visualize --location madrid
# Generates: temperature_chart_madrid.html (opens in browser)
```

## Example Queries

Note: Replace `weather_data_madrid` with your location's table name (`weather_data_<location_id>`).

```sql
-- Days over 35°C by year
SELECT 
  strftime('%Y', timestamp) as year,
  COUNT(DISTINCT DATE(timestamp)) as days_over_35
FROM weather_data_madrid 
WHERE temperature_c > 35
GROUP BY year
ORDER BY year;

-- Average summer temperature by year
SELECT 
  strftime('%Y', timestamp) as year,
  AVG(temperature_c) as avg_temp
FROM weather_data_madrid 
WHERE strftime('%m', timestamp) IN ('06', '07', '08')
GROUP BY year
ORDER BY year;
```

## Advanced Examples

### Heat wave analysis
```sql
-- Days over 35°C by year (for Santander)
SELECT 
  strftime('%Y', timestamp) as year,
  COUNT(DISTINCT DATE(timestamp)) as days_over_35
FROM weather_data_madrid 
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
FROM weather_data_madrid 
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
FROM weather_data_madrid 
GROUP BY month
ORDER BY month;
```

### Wind patterns
```sql
-- Average wind speed by hour of day
SELECT 
  strftime('%H', timestamp) as hour,
  AVG(wind_speed_kmh) as avg_wind_kmh
FROM weather_data_madrid 
WHERE wind_speed_kmh IS NOT NULL
GROUP BY hour
ORDER BY hour;
```

### Multi-location comparison
```sql
-- Compare average summer temps across locations
SELECT 
  'madrid' as location,
  strftime('%Y', timestamp) as year,
  AVG(temperature_c) as avg_summer_temp
FROM weather_data_madrid 
WHERE strftime('%m', timestamp) IN ('06', '07', '08')
GROUP BY year
UNION ALL
SELECT 
  'brno' as location,
  strftime('%Y', timestamp) as year,
  AVG(temperature_c) as avg_summer_temp
FROM weather_data_brno 
WHERE strftime('%m', timestamp) IN ('06', '07', '08')
GROUP BY year
ORDER BY year, location;
```

## Troubleshooting

**"config.yaml not found"**
- Run `cp config.yaml.example config.yaml`
- Edit the new file with your location coordinates

**"Location 'X' not found in config"**
- Check `config.yaml` - the location ID must match exactly
- Available locations are listed in the error message
- Location IDs are the `id:` field in your config

**"--location flag is required"**
- Query and visualize commands need to know which location to use
- Example: `python weather_data.py query --location madrid "..."`
- Backfill and update process all locations automatically (no flag needed)

**"No weather data found for location"**
- Run `python weather_data.py sync` first to fetch historical data
- This fetches 11 years for all configured locations on first run

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
