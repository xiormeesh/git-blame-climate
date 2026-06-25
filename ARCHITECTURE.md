# Architecture

## Design Decisions

### Single-file implementation
All code lives in `weather_data.py` for simplicity. The project is small enough that splitting into modules would add unnecessary complexity. If it grows, natural split points would be:
- `api.py` - Open-Meteo client
- `database.py` - SQLite operations
- `cli.py` - Command-line interface

### Database schema
SQLite with **one table per location**: `weather_data_<location_id>`. Each table has identical schema with timestamp as primary key (one reading per hour). Indexes on `timestamp` and `DATE(timestamp)` optimize time-range and daily aggregations.

**Why separate tables instead of a location_id column?**
- Simpler queries (no need to filter by location_id)
- Better SQLite performance (smaller indexes per table)
- Easier to drop/recreate individual location data
- Table name immediately identifies the location

Wind speed and humidity are nullable because Open-Meteo may not have data for all hours/locations.

### API retry logic
Network requests retry 3 times with exponential backoff (1s, 2s, 4s). This handles transient failures without overwhelming the API. After 3 failures, we skip the chunk and continue - better to have partial data than fail the entire backfill.

### Data coverage (11-year sliding window)
Backfill always fetches **11 years of data**: current incomplete year + 10 full prior years. For example, in 2026 it fetches 2016-01-01 through 2026-06-25.

This sliding window automatically drops old data as time passes - in 2027, backfill will fetch 2017-2027 (2016 is no longer included).

Formula: `range(current_year - 10, current_year + 1)`

### Chunking strategy
The 11-year range is processed year-by-year (not 365-day chunks) to:
- Show clear progress (one line per year per location)
- Handle current year specially (only fetch through today)
- Avoid API timeouts (one year = ~8760 hourly records)

### Update command
Uses forecast API for recent data (<16 days) because it's optimized for near-real-time data. Falls back to archive API for older gaps. If the database is empty, suggests running backfill instead - backfill's chunking is more efficient for large ranges.

### Configuration
YAML for human readability. Supports multiple locations in a `locations:` list, each with:
- `id`: Machine-friendly identifier used for table names and commands (e.g., "madrid")
- `name`: Human-friendly display name (e.g., "Santander")
- `latitude`, `longitude`, `timezone`: Coordinates and timezone for API requests

The example uses Madrid and Barcelona instead of real locations to avoid exposing private information in the public repo. User's actual config.yaml is gitignored.

## Data Flow

```
User runs backfill
    ↓
Load and validate config.yaml (multi-location format)
    ↓
Calculate 11-year range (current + 10 prior)
    ↓
Initialize database with one table per location
    ↓
For each location in config:
    For each year in range:
        Fetch year's data from Open-Meteo API (with retry)
        ↓
        Parse response into records
        ↓
        INSERT OR IGNORE into weather_data_<location_id>
        ↓
        Report progress (e.g., "Fetching 2020... 8784 records inserted")
    ↓
    Report location total
```

### Query/Visualize Flow
```
User runs query/visualize --location <id>
    ↓
Load config.yaml
    ↓
Validate location ID exists in config
    ↓
Determine table name: weather_data_<location_id>
    ↓
Execute SQL query / Generate chart
    ↓
Display results / Save chart to temperature_chart_<location_id>.html
```

## Extension Points

To add a new weather variable (e.g., cloud cover):
1. Update `hourly` parameter in `fetch_weather_data()`
2. Add column to database schema in `init_database()`
3. Update `_parse_weather_response()` to extract the new field

To add a new data source (e.g., AEMET):
1. Add config section for the new API
2. Create new fetch function (similar to `fetch_weather_data()`)
3. Use `source` column to distinguish between providers
4. Compare data quality with queries like `SELECT AVG(temperature_c) FROM weather_data GROUP BY source`

Visualization is already implemented using Plotly:
- `python weather_data.py visualize --location <id>` generates interactive HTML charts
- Shows 11 years of daily max temperatures with toggleable year lines
- Saves to `temperature_chart_<location_id>.html` and auto-opens in browser
