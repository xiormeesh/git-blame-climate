# Architecture

## Design Decisions

### Single-file implementation
All code lives in `weather_data.py` for simplicity. The project is small enough that splitting into modules would add unnecessary complexity. If it grows, natural split points would be:
- `api.py` - Open-Meteo client
- `database.py` - SQLite operations
- `cli.py` - Command-line interface

### Database schema
SQLite with a single `weather_data` table. Timestamp is the primary key since each hour has one reading. Indexes on `timestamp` and `DATE(timestamp)` optimize the most common queries (time-range and daily aggregations).

Wind speed and humidity are nullable because Open-Meteo may not have data for all hours/locations.

### API retry logic
Network requests retry 3 times with exponential backoff (1s, 2s, 4s). This handles transient failures without overwhelming the API. After 3 failures, we skip the chunk and continue - better to have partial data than fail the entire backfill.

### Chunking strategy
Large date ranges (e.g., 10 years) are split into 1-year chunks to:
- Avoid API timeouts
- Show progress during long-running operations
- Enable partial success if some chunks fail

Each chunk is 365 days from the start date, not calendar years. This keeps chunk sizes consistent regardless of the start date.

### Update command
Uses forecast API for recent data (<16 days) because it's optimized for near-real-time data. Falls back to archive API for older gaps. If the database is empty, suggests running backfill instead - backfill's chunking is more efficient for large ranges.

### Configuration
YAML for human readability. The example uses Madrid instead of the user's real location to avoid exposing private information in the public repo.

## Data Flow

```
User runs backfill/update
    ↓
Load config.yaml
    ↓
Initialize database (if needed)
    ↓
Calculate date chunks
    ↓
For each chunk:
    Fetch from Open-Meteo API (with retry)
    ↓
    Parse response into records
    ↓
    INSERT OR IGNORE into SQLite
    ↓
    Report progress
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

To add visualization:
1. Add matplotlib to requirements.txt
2. Add new subcommand (e.g., `plot`)
3. Query database and generate charts
