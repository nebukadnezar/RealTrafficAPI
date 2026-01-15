# RealTraffic API

Python example scripts for the RealTraffic API - providing real-time aviation traffic data, weather information, and airport data for flight simulators.

## Overview

RealTraffic aggregates global ADS-B data from multiple providers along with weather information from over 5000 airports globally and from the 0.25-degree resolution GFS model weather data. The data is available for live, real-time consumption, and up to 2 weeks into the past.

## Requirements

- Python 3.x
- A valid RealTraffic license (stored in `~/Documents/.InsideSystems/RealTraffic.lic`)

### Python Dependencies

```bash
pip install requests matplotlib textalloc cartopy
```

## Scripts

| Script | Description |
|--------|-------------|
| `API_tester.py` | Full API demo - ties all endpoints together with terminal-based flight tracking |
| `API_traffic.py` | Traffic API tester (locationtraffic, destinationtraffic, parkedtraffic) |
| `API_weather.py` | Weather API tester (GFS weather data and METARs) |
| `API_search.py` | Search API tester (find flights by callsign, flight number, type, etc.) |
| `API_airportinfo.py` | Airport Info API tester (runway/MSA data) |
| `API_nearestmetar.py` | Nearest METAR API tester |
| `API_sigmet.py` | SIGMET API tester |
| `API_active_runway.py` | Active runway monitor (continuous monitoring) |
| `RT_App_Tester.py` | Simulates a flight sim connecting to RealTraffic app |

## Usage Examples

```bash
# Full API demo at an airport location
./API_tester.py -a YSSY -r 100 -z 30000

# Follow a specific flight by callsign
./API_tester.py -fcs QFA1 -r 50

# Traffic with map visualization
./API_traffic.py --airport YSSY --traffictype parkedtraffic --plot --radius 3

# Weather at an airport
./API_weather.py -a LSZH

# Search for flights
./API_search.py -p CallsignExact -s QFA1
./API_search.py -p Type -s B77W
```

## Documentation

See `RealTraffic API.md` for complete API documentation including:
- Authentication workflow
- All API endpoints and parameters
- Traffic and weather data formats
- Integration with flight simulators

## License

Requires a valid RealTraffic license. Visit [flyrealtraffic.com](https://flyrealtraffic.com) for more information.
