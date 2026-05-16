# RealTraffic Application Programmable Interface (API) Documentation

**Release 3.0 - April 2026**

Questions or comments: Balthasar Indermühle <balt@inside.net>

---

## Table of Contents

- [Readme First](#readme-first)
- [Applications using this API](#applications-using-this-api)
- [Direct API connections](#direct-api-connections)
  - [General workflow](#general-workflow-for-direct-api-connections)
  - [/auth – Authentication](#auth--authentication)
  - [/deauth - Deauthentication](#deauth---deauthentication)
  - [/traffic – Obtaining traffic](#traffic--obtaining-traffic)
  - [/nearestmetar - Nearest Airports with METARs](#nearestmetar---nearest-airports-with-metars)
  - [/weather – Obtaining weather](#weather--obtaining-weather)
  - [/sigmet – Fetch global SIGMETs](#sigmet--fetch-global-sigmets)
  - [/airportinfo – Obtaining information about an airport](#airportinfo--obtaining-information-about-an-airport)
  - [/active_runway – Active runway data](#active_runway--active-runway-data)
  - [/search – Find a flight in the system](#search--find-a-flight-in-the-system)
  - [/tracklog – Retrieve aircraft position history](#tracklog--retrieve-aircraft-position-history)
  - [/emget – Emergency squawk tracker](#emget--emergency-squawk-tracker)
  - [/sattile – Satellite imagery tiles (mbtiles)](#sattile--satellite-imagery-tiles-mbtiles)
  - [/weather_tiles – Weather grid tile data](#weather_tiles--weather-grid-tile-data)
- [Getting the API example scripts to work](#getting-the-api-example-scripts-to-work)
- [Indirect API connections via RT application](#indirect-api-connections-via-rt-application)
  - [Integrating your own flight simulator plugin](#integrating-your-own-flight-simulator-plugin)
  - [Providing your simulator position to RealTraffic](#providing-your-simulator-position-to-realtraffic)
  - [Using the Destination Traffic/Weather feature](#using-the-destination-trafficweather-feature)
  - [How to find out license and version information](#how-to-find-out-license-and-version-information)
  - [Controlling the time offset from the simulator](#controlling-the-time-offset-from-the-simulator)
  - [Reading weather and traffic information](#reading-weather-and-traffic-information)
  - [UDP Weather Broadcasts](#udp-weather-broadcasts)
  - [XTRAFFIC format](#xtraffic-format)
  - [RTTFC/RTDEST format](#rttfcrtdest-format)
  - [Requesting Parked Traffic](#requesting-parked-traffic)
  - [Using Satellite Imagery](#using-satellite-imagery)

---

## Readme First

RealTraffic (RT) aggregates global ADS-B data from multiple global data providers as well as weather information from over 5000 airports globally and from the 0.25-degree resolution GFS model weather data at 20 altitude layers vertically. The data is available for live, real-time consumption, and in identical resolution and fidelity up to 2 weeks into the past.

There are two methods to interface with RT data:

1. **Direct** via API queries to the RT servers
2. **Indirect** via the RT application

When determining which method you want to use, consider the following points:

- Standard RT licenses can retrieve data from the RT servers with a single connection, i.e. no concurrent queries are possible.
- Professional RT licenses get two concurrent connections to the servers.
- If you're simply wanting to retrieve traffic and/or weather for a given location, you're better off using the direct API calls to the RT servers.
- If you're writing a plugin for MSFS, P3D, X-Plane, or PSX, that works in conjunction with the existing plugins PSXT, LiveTraffic, or the RT application, you should consider using the traffic and weather data broadcast by the RT application instead so you don't use one of the available concurrent server connections.
- When using simulator setups with multiple clients that need access to weather and traffic data, use the RT application as it broadcasts the traffic data and weather on the local network, so all of your simulator instances can consume the same data without the need for concurrent access to the API servers.

---

## Applications using this API

The main use case since RealTraffic's inception in 2017 has been to inject real air traffic into flight simulators. As of the writing of this document, the following programs are available for flight simulator traffic and/or weather injection:

| Software | Supported simulators | Traffic Features | Weather Features | Platform | Notes |
|----------|---------------------|------------------|------------------|----------|-------|
| RealTraffic client | Aerowinx PSX | Ground, Flying | Global WX, METARs, SIGMETs | Windows, MacOS, Linux | [Visit](https://flyrealtraffic.com) |
| PSXT | MSFS 2020/2024, P3D | Parked, Ground, Flying | - | Windows | [Visit](https://flypst.com) |
| LiveTraffic | X-Plane 12 | Parked, Ground, Flying | Global WX, METARs | Windows, MacOS, Linux | [Visit](https://github.com/TwinFan/LiveTraffic) |

If you're a developer and would like your application listed here, please reach out via the email on the title page.

---

## Direct API connections

The direct API method gives you access to full traffic data as well as weather and airport data – this is everything you need to have clear situation awareness of all aviation movements in your area of interest.

The responses to the API calls are given in JSON dictionaries. When calling the APIs, please make sure you use the gzip compression setting in the HTTPS requests so as not to incur unnecessary data transfer cost. Input data for the API is always expected as HTTP POST data.

Please refer to the included python example scripts that illustrate:
- The use of each API call
- `API_tester.py` ties it all together and shows you a practical implementation of all the calls and provides you with a neat, terminal based, flight tracking experience!

### What's new in v6

The v6 API introduces several new features while maintaining backwards compatibility with existing endpoints:

- **Token-based authentication** — In addition to legacy license keys, v6 supports API tokens (prefixed with `rt_`) tied to user accounts. Token auth enables account-based subscription management.
- **Brute force protection** — 10 failed login attempts from the same IP triggers a 5-minute lockout (status 429).
- **TAF data in weather responses** — The `/weather` endpoint now returns TAF (Terminal Aerodrome Forecast) data alongside METARs.
- **Eddy Dissipation Rate (EDR)** — The `/weather` endpoint now returns `EDR` (at requested altitude) and `EDRs` (vertical profile) fields in the `locWX` response, providing a standardized turbulence metric used by aviation.
- **New search parameters** — `/search` now supports `XPDR` (transponder code) and `HexID` (ICAO hex identifier) search types.
- **New endpoints:**
  - `/active_runway` — Active runway data with wind components, arrival/departure counts, and runway categorization
  - `/tracklog` — Retrieve historical position track for a specific aircraft
  - `/emget` — Query active and historical emergency squawk codes
  - `/sattile` — Satellite imagery tiles (replaces `/satimage` and `/satimageinfo`)
  - `/weather_tiles` — Access GFS weather data as grid tiles for visualization

### General workflow for direct API connections

The sequence to establish a session and retrieve data works as follows:

1. **Authenticate** using a license string (e.g. `AAA-BBB-CCC-DDD`) or an API token (e.g. `rt_abc123...`)
   - Authentication returns a session GUID (a globally unique identifier that identifies this license's session on the RT servers). Retrieve the GUID and use the GUID in all subsequent requests.
   - It can also return a status 405: Too many sessions. In this case, wait 10 seconds and try authenticating again.
   - Standard licenses are limited to a single concurrent session; professional licenses get two concurrent sessions.

2. **Loop to fetch traffic and weather:**
   - Wait request rate limit (RRL) time in milliseconds since the last traffic request.
   - Fetch traffic.
   - Wait weather request rate limit (WRRL) time in milliseconds since the last weather request.
   - Fetch weather.

3. **Check the status** of each response. Status codes:
   - `200`: Request processed ok
   - `400`: Parameter fault. The message string contains details on which parameter you supplied (or didn't supply) that is causing the error.
   - `401`: GUID not found, reauthenticate. If you receive this response, simply authenticate again and use the new session GUID for subsequent requests.
   - `402`: License expired or no active subscription.
   - `403`: No data for this license type (happens for example when trying to access historical data with a standard license), or email not verified (token auth).
   - `404`: No data (or license/token) was found. Did you send the correct license string? Typo?
   - `405`: Too many sessions. This happens when trying to access RT data with more than one client for a standard license, or more than two clients for a professional license. Also happens if you try to authenticate too quickly after ending a session and that session didn't use deauth to clean up.
   - `406`: Request rate violation. Make sure you wait for request rate limit (the number of) milliseconds specified in the traffic and weather returns. These are the "rrl" (traffic) and "wrrl" (weather) entries respectively. These request rate limits can change dynamically during a session if there is a sudden spike in load on the servers, make sure your code can accommodate that.
   - `407`: History too far back. The maximum history supported at present is 14 days. If you request traffic or weather data that is further back, this error will trigger.
   - `429`: Too many failed login attempts. Wait 5 minutes before trying again.
   - `500`: An internal server error has occurred. The message string will contain some further information. If it's a repeatable problem, please let me know the details of that message string (i.e. you should log it)

4. **Deauthenticate** when your client disconnects/shuts down. Please don't forget this, it helps keeping the server less cluttered with session data from the users. It also allows your client to reconnect immediately if for some reason you need to do that.

The GUID will remain in memory on the server for **120 seconds** after the last use. If more than 120 seconds elapse between your calls, you will need to authenticate again and obtain a new GUID. Thus, session lifetime is 120 seconds (2 minutes).

---

## API call examples

> **Note:** In the cURL command line examples I'm explicitly setting the header to accept gzip compression and pipe the output into gunzip rather than using the `--compressed` option which does the same thing but in a simpler call.
>
> You can also refer to the Python scripts included with the API documentation to see how these calls are implemented.
>
> This is purely to remind you to please use gzip compression in all of your calls! That means putting this in the HTTP header for all of your POST requests:
> ```
> Accept-encoding: gzip
> ```

---

### /auth – Authentication {#auth--authentication}

**Address:** `https://rtwa.flyrealtraffic.com/v6/auth`

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `license` | the user's RealTraffic license, e.g. `AAA-BBB-CCC-DDD` (legacy auth) |
| `token` | an API token prefixed with `rt_` (token-based auth, preferred) |
| `software` | the name and version of your software |

Use either `license` or `token`, not both. Token-based auth is the preferred method for new integrations.

#### Optional POST parameters

| Parameter | Description |
|-----------|-------------|
| `name` | client application name |
| `LANaddr` | local network address |
| `osname` | operating system name |
| `osversion` | OS version |
| `osarch` | OS architecture |
| `usercountry` | user's country |

#### Example call (license auth)

```bash
curl -sH 'Accept-encoding: gzip' -d "license=AAA-BBB-CCC-DDD&software=MyCoolSoftware 1.0" -X POST https://rtwa.flyrealtraffic.com/v6/auth | gunzip -
```

#### Example call (token auth)

```bash
curl -sH 'Accept-encoding: gzip' -d "token=rt_your_api_token_here&software=MyCoolSoftware 1.0" -X POST https://rtwa.flyrealtraffic.com/v6/auth | gunzip -
```

#### Response

```json
{ "status": 200, "type": 2, "rrl": 2000, "wrrl": 2000, "expiry": 1957899487, "GUID": "c0245e11-8840-46f9-9cf9-985183612495", "server": "rtw03a" }
```

| Field | Description |
|-------|-------------|
| `type` | 1 = standard, 2 = professional |
| `rrl` | traffic request rate limit in ms. Make sure you sleep that amount of time before your next traffic request or you will get a request rate violation. |
| `wrrl` | weather request rate limit in ms. Make sure you sleep that amount of time before your next weather request or you will get a request rate violation. |
| `expiry` | UNIX epoch second of the expiration date of the license/subscription. |
| `GUID` | the session GUID you need to store and use in any communications going forward. |
| `server` | the internal name of the server handling the request. Please indicate this name in case you run into repeatable problems using the API. |

#### Error responses

All errors return JSON with a `status` field matching the HTTP-conventional code, plus a human-readable `message`. Bodies always include the `server` field for support purposes.

| `status` | When | `message` example |
|----------|------|-------------------|
| `402` | Token auth: the account has no active subscription and no valid linked license. | `"No active subscription"` |
| `403` | Token auth: the account exists but its email isn't verified. | `"Email not verified"` |
| `404` | License auth: the license string was empty, contained invalid characters, or the format check failed (after whitespace trim). The same status is returned for licenses that pass format checks but aren't in the database. | `"Invalid license format"` or `"License not found"` |
| `404` | Token auth: the supplied `token` doesn't match any row in the `api_tokens` table. | `"Invalid token"` |
| `405` | The license/account is already at its concurrent-sessions cap. | `"Too many sessions"` |
| `429` | The same IP has failed auth (token or license) more than 10 times in the last 5 minutes. Lockout lasts the rest of the 5-minute window. | `"Too many failed attempts"` |
| `500` | Database connection failure or sustained memcached errors (>20 retries with 100 ms backoff). | `"No database connection"`, `"Too many memcache errors. Giving up."` |

**Notes:**
- Active data feeders are automatically upgraded to professional (type 2) with 2 concurrent sessions.
- Token auth checks for an active subscription on the associated account. If no subscription is found, it falls back to any linked license.
- The license string is whitespace-trimmed before validation, so `"  XXXXX-XXXX-XXXXXX-XXXXXX  "` is treated as `"XXXXX-XXXX-XXXXXX-XXXXXX"`. Internal spaces and other non-`[A-Za-z0-9-]` characters still fail with status 404 / `"Invalid license format"`.

---

### /deauth - Deauthentication

**Address:** `https://rtwa.flyrealtraffic.com/v6/deauth`

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the session GUID |

#### Example call

```bash
curl -sH 'Accept-encoding: gzip' -d "GUID=26cb1a52-169b-425e-8df6-7713e5c34835" -X POST https://rtwa.flyrealtraffic.com/v6/deauth | gunzip -
```

#### Response

```json
{ "status": 200, "message": "Deauth success", "Session length": 1572, "Active length": 843, "Distance km": 1247.3, "server": "rtw01a" }
```

| Field | Description |
|-------|-------------|
| `Session length` | the total duration of the session in seconds |
| `Active length` | the number of seconds the session was actively in flight |
| `Distance km` | the distance covered during the session in kilometers |

---

### /traffic – Obtaining traffic {#traffic--obtaining-traffic}

**Address:** `https://rtwa.flyrealtraffic.com/v6/traffic`

Traffic can be retrieved by giving a latitude/longitude box and a time offset in minutes from real-time.

Optionally, if you want to speed up the buffering internally, you can request up to 10 buffers of maximum 10s spacing (maximum 100s of wallclock time). This will return buffer_0 to buffer_n in the data field of the response, with buffer_0 being the youngest in time, and buffer_n the oldest. The endepoch parameter returned contains the unix epoch second of the oldest buffer that was returned.

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the GUID obtained from the auth call |
| `querytype` | For standard traffic queries, pass the string `"locationtraffic"`. For a secondary query that won't run afoul of request rate violations, use `"destinationtraffic"`. For parked traffic, use `"parkedtraffic"`. See below for the format of parked traffic (it is different from the standard format). |
| `bottom` | southern latitude |
| `top` | northern latitude |
| `left` | western longitude |
| `right` | eastern longitude |
| `toffset` | time offset into the past in minutes |
| `buffercount` | [optional] The number of buffers to retrieve. Maximum 10. |
| `buffertime` | [optional] The number of seconds between buffers (must be an even number). Maximum 10 |

#### Example call

```bash
curl -sH 'Accept-encoding: gzip' -d "GUID=76ff411b-d481-470f-9ce5-5c3cbc71a276&top=-16&bottom=-17&left=145&right=146&querytype=locationtraffic&toffset=0" -X POST https://rtwa.flyrealtraffic.com/v6/traffic | gunzip -
```

#### Response

```json
{
    "data": {
        "7c1522": ["7c1522", -16.878799, 145.66705, 103.16, 3025, 127.3, 1752, "X", "A139", "VH-EGK", 1658644400.67, "MRG", "", "RSCU510", 0, -768, "RSCU510", "X_adsb_icao", 3350, 140, 148, 0.224, 1.06, 7.38, 93.87, 100.46, -800, "none", "A7", 1014.4, 1024, 1008, null, "tcas", 8, 186, 1, 9, 2, 0.1, -9.3, 0, 0, 91, 20, null, null],
        "7c68a1": ["7c68a1", -16.754288, 145.693311, 156.07, 2325, 165.2, 6042, "RT", "E190", "VH-UYB", 1658644401.01, "BNE", "CNS", "QFA1926", 0, -960, "QF1926", "F_adsb_icao", 2625, 173, 182, 0.272, -0.09, -1.41, 146.6, 153.18, -928, "none", "A3", 1014.4, 3712, 2896, null, "autopilot|approach|tcas", 8, 186, 1, 9, 2, 0.1, -20.2, 0, 0, 123, 19, null, null]
    },
    "full_count": 6839,
    "source": "MemoryDB",
    "rrl": 2000,
    "status": 200,
    "dataepoch": 16738882
}
```

Each aircraft has a state vector entry, with the transponder's hex ID as the key. Additional fields returned include:

| Field | Description |
|-------|-------------|
| `data` | contains the aircraft data as a dictionary |
| `full_count` | The number of aircraft being tracked in the system at the requested point in time |
| `source` | MemoryDB or DiskDB. Generally, data within 9h of real-time is kept in-memory on the server. Older data comes from disk storage. |
| `rrl` | The number of milliseconds you should wait before sending the next traffic request. During times of heavy load, you may be requested to poll less frequently. If you don't honour this request, you will receive request rate violation errors. |
| `status` | 200 for success, any other status indicates an error |
| `dataepoch` | the epoch seconds in UTC of the data delivered |

#### Traffic data field indices

The data fields for each aircraft entry are as follows (0-indexed):

| Index | Field | Example |
|-------|-------|---------|
| 0 | hexid | 7c68a1 |
| 1 | latitude | -16.754288 |
| 2 | longitude | 145.693311 |
| 3 | track in degrees | 156.07 |
| 4 | barometric altitude in ft (std pressure) | 2325 |
| 5 | Ground speed in kts | 165.2 |
| 6 | Squawk / transponder code | 6042 |
| 7 | Data source (provider code) | "X" |
| 8 | Type | E190 |
| 9 | Registration | VH-UYB |
| 10 | Epoch timestamp of last position update | 1658644401.01 |
| 11 | IATA origin | BNE |
| 12 | IATA destination | CNS |
| 13 | ATC Callsign | QFA1926 |
| 14 | On ground (0/1) | 0 |
| 15 | Barometric vertical rate in fpm | -928 |
| 16 | Flight number | QF1926 |
| 17 | Message source type | adsb_icao |
| 18 | Geometric altitude in ft (GPS altitude) | 2625 |
| 19 | Indicated air speed / IAS in kts | 173 |
| 20 | True air speed / TAS in kts | 182 |
| 21 | Mach number | 0.272 |
| 22 | Track rate of turn (negative = left) | -0.09 |
| 23 | Roll / Bank (negative = left) | -1.41 |
| 24 | Magnetic heading | 146.6 |
| 25 | True heading | 153.18 |
| 26 | Geometric vertical rate in fpm | -928 |
| 27 | Emergency | none |
| 28 | Category | A3 |
| 29 | QNH set by crew in hPa | 1014.4 |
| 30 | MCP selected altitude in ft | 3712 |
| 31 | Autopilot target altitude in ft | 2896 |
| 32 | Selected heading | (empty) |
| 33 | Selected autopilot modes | autopilot\|approach\|tcas |
| 34 | Navigation integrity category | 8 |
| 35 | Radius of containment in meters | 186 |
| 36 | Navigation integrity category for barometric altimeter | 1 |
| 37 | Navigation accuracy for Position | 9 |
| 38 | Navigation accuracy for velocity | 2 |
| 39 | Age of position in seconds | 0.1 |
| 40 | Signal strength reported by receiver | -20.2 dbFS (-49.5 = no signal strength) |
| 41 | Flight status alert bit | 0 |
| 42 | Flight status special position identification bit | 0 |
| 43 | Wind direction | 123 |
| 44 | Wind speed | 19 |
| 45 | SAT/OAT in C | (none) |
| 46 | TAT | (none) |
| 47 | Is this an ICAO valid hex ID | 1 |
| 48 | Operator livery code (ICAO airline / operator flag code) | "QFA" |

**Note:** The v6 traffic data array has 49 fields (indices 0–47 from the original v6 schema plus index 48 for the new operator-livery code). The v5 `record_augmented` field at index 48 has been removed; the slot is now occupied by the operator-livery code described above.

The operator-livery code at index 48 is the ICAO operator/airline flag code as it appears on the airframe (e.g. "QFA" for Qantas, "FDX" for FedEx, "SHF" for Shell-leased helicopters). It is keyed on the hex transponder ID rather than the operating callsign, so it remains correct under wet-lease and codeshare operations where the callsign-derived airline would be wrong. Source: the OperatorFlagCode column of the OpenSky-derived BaseStation aircraft database, refreshed daily. The field is an empty string when the hex is not present in the database (~30% of records; mostly private/military airframes).

#### Message source types

The "message source type" field is preceded by `?_` where `?` contains any alphabetical code to indicate the data provider the data came from, and optionally is preceded by `ID_` if the data is interpolated data. The remainder can contain the following values:

| Type | Description |
|------|-------------|
| `est` | an estimated position |
| `adsb` | a simplified ADS-B position only providing position, speed, altitude and track |
| `adsb_icao` | messages from a Mode S or ADS-B transponder |
| `adsr_icao` | rebroadcast of an ADS-B messages originally sent via another data link |
| `adsc` | ADS-C (received by satellite downlink) – usually old positions, check timestamp |
| `mlat` | MLAT, position calculated by multilateration. Usually somewhat inaccurate |
| `other` | quality/source undisclosed |
| `mode_s` | ModeS data only, no position |
| `adsb_other` | using an anonymised ICAO address. Rare |
| `adsr_other` | rebroadcast of 'adsb_other' ADS-B messages |

#### Transmitter categories

| Category | Description |
|----------|-------------|
| A0 | No information |
| A1 | Light (< 15,500 lbs) |
| A2 | Small (15,500 – 75,000 lbs) |
| A3 | Large (75,000 – 300,000 lbs) |
| A4 | High vortex generating Acft (e.g. B757) |
| A5 | Heavy (> 300,000 lbs) |
| A6 | High Performance (> 5G accel, > 400 kts) |
| A7 | Rotorcraft |
| B0 | No information |
| B1 | Glider/Sailplane |
| B2 | Lighter-than-air |
| B3 | Parachutist/Skydiver |
| B4 | Ultralight/Hangglider/Paraglider |
| B5 | Reserved |
| B6 | Unmanned Aerial Vehicle / Drone |
| B7 | Space/Trans-atmospheric vehicle |
| C0 | No Information |
| C1 | Surface vehicles: Emergency |
| C2 | Surface vehicles: Service |
| C3 | Point obstacles (e.g. tethered balloon) |
| C4 | Cluster obstacle |
| C5 | Line obstacle |
| C6-7 | Reserved |
| D0 | No information |
| D1-7 | Reserved |

#### Parked traffic format

Queries for `parkedtraffic` will return any traffic whose last groundspeed was zero, and whose position timestamp is at least 10 minutes old, but less than 24h old, in the following format:

```json
{
    "data": {
        "7c37c6": [-33.933804, 151.18984, "YSSY_D112A", "GLEX", "VH-LAW", 1767932190.45, "VHLAW"],
        "a700bb": [-33.933758, 151.18991, "YSSY_D112A", "GLF5", "N550PL", 1767937540.7, "N550PL"],
        "7c6db3": [-33.931984, 151.176438, "YSSY_D12", "B738", "VH-VYD", 1767940121.4, "QFA460"]
    },
    "full_count": 13765,
    "source": "DiskDB",
    "rrl": 2000,
    "status": 200,
    "dataepoch": 1721650780
}
```

The fields are: latitude, longitude, gate ID with airport ICAO ID prepended (separated by underscore), type, tail, last timestamp when it was moving into place, and ATC callsign.

---

### Weather system information

RealTraffic provides access to the highest resolution GFS model data available. This allows a realistic weather environment to be simulated, including historical time offsets.

As a first step, you should obtain the airport ICAO code of the nearest airport with METAR information in the RT system. This can be achieved by calling the `/nearestmetar` endpoint. The retrieved airport code should then be fed into the `/weather` endpoint query so that the actual METAR can be retrieved. For best results, you should always use the cloud and wind information from the METARs rather than the global forecasting model when flying near the ground and near an airport. For conditions aloft while enroute (wind, temperature, cloud, and turbulence), you can rely on the altitude profile data returned by the `/weather` endpoint.

---

### /nearestmetar - Nearest Airports with METARs

**Address:** `https://rtwa.flyrealtraffic.com/v6/nearestmetar`

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the GUID obtained from the auth call |
| `toffset` | time offset into the past in minutes |
| `lat` | latitude in degrees |
| `lon` | longitude in degrees (west = negative) |
| `maxcount` | the number of nearest airports to find. Maximum = 20. If omitted, returns only the nearest airport. |

#### Example call

```bash
curl -sH 'Accept-encoding: gzip' -d "GUID=76ff411b-d481-470f-9ce5-5c3cbc71a276&lat=47.5&lon=5.5&toffset=0" -X POST https://rtwa.flyrealtraffic.com/v6/nearestmetar | gunzip -
```

#### Response

When a single airport is returned:

```json
{"wrrl": 2000, "status": 200, "message": "OK", "data": [{"ICAO": "KNSI", "Dist": 10.3, "BrgTo": 42.3, "METAR": "KNSI 130053Z AUTO 28010KT 10SM FEW009 00/ A2986 RMK AO2 SLP114 T0000 $"}]}
```

When multiple airports are returned (using `maxcount`):

```json
{
    "wrrl": 2000,
    "status": 200,
    "message": "OK",
    "data": [
        {"ICAO":"KNSI","Dist":764.3,"BrgTo":32.1,"METAR":"KNSI 130053Z AUTO 28010KT 10SM FEW009 00/ A2986 RMK AO2 SLP114 T0000 $"},
        {"ICAO":"KAVX","Dist":804,"BrgTo":34.7,"METAR":"KAVX 130051Z AUTO VRB06KT 10SM CLR 20/14 A2990 RMK AO2 SLP111 T02000144"},
        {"ICAO":"KLPC","Dist":809.6,"BrgTo":25.6,"METAR":"KLPC 130056Z AUTO 27010KT 10SM CLR 18/15 A2986 RMK AO2 SLP110 T01830150"}
    ]
}
```

| Field | Description |
|-------|-------------|
| `wrrl` | The weather request rate limit in ms |
| `ICAO` | The ICAO code of the nearest Airport that has a METAR. Use this to feed the airports parameter in the weather API call. |
| `Dist` | The distance to the airport in NM |
| `BrgTo` | The true bearing to the airport |
| `METAR` | The current METAR for that airport |

---

### /weather – Obtaining weather {#weather--obtaining-weather}

**Address:** `https://rtwa.flyrealtraffic.com/v6/weather`

Weather (METARs, TAFs) and the local GFS derived weather can be retrieved using this call.

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the GUID obtained from the auth call |
| `querytype` | should be set to the string `"locwx"` |
| `toffset` | time offset into the past in minutes |
| `lat` | latitude in degrees |
| `lon` | longitude in degrees (west = negative) |
| `alt` | geometric altitude in ft |
| `airports` | a list of airports for which to retrieve METARs and TAFs, delimited by pipe (\|) |

#### Example call

```bash
curl -sH 'Accept-encoding: gzip' -d "GUID=76ff411b-d481-470f-9ce5-5c3cbc71a276&lat=47.5&lon=5.5&alt=37000&airports=LSZB|LSZG|LFSB&querytype=locwx&toffset=0" -X POST https://rtwa.flyrealtraffic.com/v6/weather | gunzip -
```

#### Response

> **Note:** The `locWX` field in the response only returns data when sufficient difference in distance (10NM) or altitude (2000ft) has elapsed between the last call and the current call, or if more than 60 seconds have elapsed since the last call, or if it is the initial call.

```json
{
    "ICAO": "YSSY",
    "QNH": 1015,
    "METAR": "YSSY 080830Z AUTO 13006KT 9999 // NCD 23/19 Q1015",
    "TAF": "TAF YSSY 080500Z ...",
    "locWX": {
        "Info": "2026-04-08_0906Z",
        "SLP": 1016.25,
        "WSPD": 77.12,
        "WDIR": 272.62,
        "T": -63.41,
        "ST": 21.28,
        "SVis": 24135,
        "SWSPD": 13.53,
        "SWDIR": 81.35,
        "DZDT": -0.037,
        "EDR": 0.1271,
        "LLC": {
            "cover": 0.0,
            "base": -1,
            "tops": -1,
            "type": -1,
            "confidence": -1
        },
        "MLC": {
            "cover": 4.6,
            "base": 6639,
            "tops": 6906,
            "type": 1.1,
            "confidence": 0.0
        },
        "HLC": {
            "cover": 99.01,
            "base": 8790,
            "tops": 12195,
            "type": 1.03,
            "confidence": 0.26
        },
        "TPP": 12871.01,
        "PRR": 0.0,
        "CAPE": 42.0,
        "DPs": [16.29, 15.08, 9.96, 8.44, 3.07, 0.1, -2.66, -6.81, -12.81, -18.12, -19.05, -22.55, -21.14, -27.02, -36.54, -39.84, -49.86, -60.43, -75.53, -84.75],
        "TEMPs": [20.88, 19.23, 17.22, 16.51, 13.97, 10.15, 7.12, 4.26, 1.36, -2.04, -6.49, -11.03, -16.79, -23.17, -29.53, -39.5, -49.78, -59.22, -63.42, -63.29],
        "WDIRs": [81.35, 76.13, 99.18, 251.82, 251.19, 268.69, 272.31, 258.29, 259.37, 260.53, 264.1, 266.14, 263.26, 259.59, 260.65, 260.86, 267.83, 263.22, 262.15, 272.85],
        "WSPDs": [13.53, 15.87, 4.34, 9.43, 30.28, 35.6, 40.61, 42.82, 38.12, 33.88, 43.5, 55.82, 73.97, 79.89, 92.38, 102.78, 103.12, 123.15, 177.65, 76.42],
        "DZDTs": [0.01, 0.03, 0.04, 0.04, 0.05, 0.02, -0.01, -0.02, -0.02, -0.01, 0.02, 0.05, 0.09, 0.11, 0.12, 0.13, 0.11, 0.0, -0.13, -0.03],
        "EDRs": [0.0559, 0.0559, 0.0932, 0.2536, 0.2396, 0.1221, 0.0746, 0.1081, 0.0423, 0.0328, 0.067, 0.0749, 0.0856, 0.0467, 0.0661, 0.0833, 0.0686, 0.0741, 0.0846, 0.1271],
        "Profiles": "RTFX1              ^S3354.0            ^E15112.0           ^FL518  271/040 -63 ^FL498  269/055 -63 ^FL478  266/070 -63 ^FL458  264/085 -63 ^FL438  263/093 -63 ^^"
    },
    "AM": [],
    "AT": []
}
```

#### Weather response field descriptions

| Field | Description |
|-------|-------------|
| `ICAO` | the ICAO code of the nearest airport. This is the first airport from the list of ICAO codes you supplied in the API call to get the METARs for. See the /nearestmetar API call to retrieve this before calling weather. |
| `QNH` | the reported pressure in hPa, often to within 0.1 hPa precision. For numbers greater than 2000, the unit is inHg, not hPa. |
| `METAR` | contains the full METAR received |
| `TAF` | contains the full TAF (Terminal Aerodrome Forecast) for the primary airport. **New in v6.** |
| `locWX` | the GFS derived location weather at the present position and time |
| `AM` | additional METARs. Contains a list of additional METARs for the remaining airports requested. |
| `AT` | additional TAFs. Contains a list of TAFs corresponding to the airports in AM. **New in v6.** |

#### locWX fields

| Field | Description |
|-------|-------------|
| `Info` | contains the timestamp if data is present, if no data is present it contains the reason for no data. Valid reasons are: `TinyDelta` (less than one minute has elapsed since the last query, or the lateral/vertical distance to the last query is less than 10NM / 2000ft), `error` (there was an error on the server). When asking for older historical data that is not in the cache, you may see "File requested", which indicates it is being retrieved from storage. Wait ~30 seconds before the next weather request. |
| `ST` | surface temperature in C |
| `SWSPD` | surface wind speed in km/h |
| `SWDIR` | surface wind direction in degrees |
| `SVis` | surface visibility in meters |
| `CAPE` | the convective available potential energy in J/kg. This is an indicator for the vertical stability of the atmospheric column at this location. |
| `PRR` | precipitation rate on ground in mm/h: < 0.5 = none or drizzle, < 2.5 = light, < 7.5 = moderate, > 7.5 = heavy |
| `LLC` | low level (lowest third of troposphere) cloud details: cover (%), base (m), tops (m), type (0-3 scale), confidence (0-1) |
| `MLC` | medium level (middle third of troposphere) cloud details |
| `HLC` | high level (top third of troposphere) cloud details |
| `DZDT` | vorticity of atmospheric layer. Turbulence indicator: < 0.05 = still air, < 0.5 = light, < 1 = medium (spills coffee), > 1 = strong (unattached objects go flying), > 2 = severe (block altitude needed) |
| `EDR` | Eddy Dissipation Rate at the supplied altitude. A standardized turbulence metric used by aviation: < 0.1 = smooth, 0.1–0.2 = light, 0.2–0.4 = moderate, 0.4–0.6 = severe, > 0.6 = extreme. **New in v6.** |
| `T` | OAT/SAT in C at the supplied altitude |
| `WDIR` | wind direction in degrees at the supplied altitude |
| `WSPD` | wind speed in km/h at the supplied altitude |
| `TPP` | tropopause height in meters |
| `SLP` | sea level pressure in hPa |
| `DPs` | Array of dew point temperatures in C in a vertical cross section |
| `TEMPs` | Array of still air temperatures in C in a vertical cross section |
| `WDIRs` | Array of wind directions (true north oriented) in a vertical cross section |
| `WSPDs` | Array of wind speeds in km/h in a vertical cross section |
| `DZDTs` | Array of turbulence measurements in m/s in a vertical cross section |
| `EDRs` | Array of Eddy Dissipation Rate values in a vertical cross section. Same altitude levels as other profile arrays. **New in v6.** |
| `Profiles` | Vertical cross section / profile at the current location, formatted as "Aerowinx Format D" |

#### Atmospheric cross section altitude levels (meters)

The atmospheric cross section parameters (TEMPs, DPs, WDIRs, WSPDs, DZDTs) correspond to the following altitude levels in meters, in the same order:

```
[111, 323, 762, 988, 1457, 1948, 2465, 3011, 3589, 4205, 4863, 5572, 6341, 7182, 8114, 9160, 10359, 11770, 13503, 15790]
```

#### Cloud types

The cloud types in the LLC/MLC/HLC fields correspond to the following types, on a sliding scale from 0 – 3:

| Value | Cloud Type |
|-------|------------|
| 0 | Cirrus |
| 1 | Stratus |
| 2 | Cumulus |
| 3 | Cumulonimbus |

### A note on implementing realistic weather in a simulator using RT weather data

The `locWX` data is always model derived, while METARs are always observation derived. Therefore, METARs are always more accurate than the locWX derived data.

**Guidelines:**
- For locations where you have METAR, always use the METAR for the information that METARs provide. In other places and for information not supplied by METARs, use locWX.
- METARs normally are updated every 30 minutes by the airport systems or on-duty meteorologist. If weather is rapidly changing, they are issued more frequently, at most every 10 minutes.
- RT uses a 10 minute cadence to refresh METAR data.
- `locWX` doesn't do a great job depicting thunderstorms but works great with other severe phenomena like hurricanes. Thunderstorms are small and localized atmospheric phenomena that can only be forecast statistically.
- CAPE values from 100 upwards indicate atmospheric instability. A CAPE of 3000 would be indicative of a high likelihood for CBs and severe ones at that.
- Hurricanes and frontal systems are modeled quite accurately in locWX data.

**METAR cloud keywords and how to use them:**

| Keyword | Meaning | Action |
|---------|---------|--------|
| `SKC` (Sky Clear) | No clouds present at all | Override any cloud shown in locWX |
| `CLR` (Clear) | No clouds detected below 12,000 feet | Discard locWX cloud below 12,000ft, keep higher cloud |
| `CAVOK` | Visibility >= 10km, no clouds below 5,000ft or MSA, no CB/TCU | Discard locWX cloud below 6,000ft AGL, keep higher |
| `NSC` (No Significant Cloud) | No clouds below 5,000ft or MSA, no CB/TCU | Discard locWX cloud below 6,000ft AGL |
| `NCD` (No Cloud Detected) | Automated report, no clouds detected | Use locWX cloud (automated systems can malfunction) |
| `VV ///` (Vertical Visibility undefined) | Sky obscured, visibility can't be assessed | Use locWX derived cloud |

---

### /sigmet – Fetch global SIGMETs {#sigmet--fetch-global-sigmets}

**Address:** `https://rtwa.flyrealtraffic.com/v6/sigmet`

Obtains the global SIGMET data for the requested time period.

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the GUID obtained from the auth call |
| `toffset` | The time offset into the past in minutes |

#### Example call

```bash
curl -sH 'Accept-encoding: gzip' -d "GUID=76ff411b-d481-470f-9ce5-5c3cbc71a276&toffset=0" -X POST https://rtwa.flyrealtraffic.com/v6/sigmet | gunzip -
```

#### Response

```json
{
  "source": "MemoryDB",
  "status": 200,
  "data": {
    "DATE": "2024-07-22 04:00:00",
    "DATA": "WSCI35 ZGGG 212345^..."
  }
}
```

The `DATA` field is the raw concatenated SIGMET bulletin text — typically tens of kilobytes. Individual SIGMETs are separated by `^` (caret) characters.

You will need to parse the SIGMET data on your own. This is a complex format, but some help is available online on how to parse it successfully.

---

### /airportinfo – Obtaining information about an airport {#airportinfo--obtaining-information-about-an-airport}

**Address:** `https://rtwa.flyrealtraffic.com/v6/airportinfo`

Provides information on an airport. This includes airport general information, minimum sector altitudes, and runways, and any available ILS systems for the runways.

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the GUID obtained from the auth call |
| `ICAO` | The ICAO code of the airport you want the information for |

#### Example call

```bash
curl -sH 'Accept-encoding: gzip' -d "GUID=76ff411b-d481-470f-9ce5-5c3cbc71a276&ICAO=LSZB" -X POST https://rtwa.flyrealtraffic.com/v6/airportinfo | gunzip -
```

#### Response

```json
{
  "data": {
    "MSA": {
      "MSA_center": "LSZB",
      "MSA_center_lat": 46.91222222,
      "MSA_center_lon": 7.49944444,
      "MSA_radius_limit": 25,
      "MSA_sector1_alt": 15800,
      "MSA_sector1_brg": 250,
      "MSA_sector2_alt": 10700,
      "MSA_sector2_brg": 5,
      "MSA_sector3_alt": 7200,
      "MSA_sector3_brg": 65
    },
    "airport": {
      "elevation": 1675,
      "name": "BELP",
      "ref_lat": 46.91222222,
      "ref_lon": 7.49944444,
      "transition_altitude": 6000,
      "transition_level": -1
    },
    "runways": {
      "RW14": {
        "declination": 2.0,
        "displaced_threshold_distance": 656,
        "gradient": 0.123,
        "gs_angle": 4.0,
        "ils_cat": 1,
        "landing_threshold_elevation": 1668,
        "lat": 46.91793889,
        "length": 5676,
        "llz_brg": 138.0,
        "llz_freq": 110.1,
        "llz_ident": "IBE",
        "lon": 7.49249444,
        "mag_brg": 138.0,
        "surface": "Asphalt",
        "threshold_crossing_height": 43,
        "true_brg": 140.197,
        "width": 98
      },
      "RW32": {
        "declination": -1,
        "displaced_threshold_distance": 0,
        "gradient": -0.123,
        "gs_angle": -1,
        "ils_cat": -1,
        "landing_threshold_elevation": 1675,
        "lat": 46.90738889,
        "length": 5676,
        "llz_brg": -1,
        "llz_freq": -1,
        "llz_ident": "",
        "lon": 7.50536111,
        "mag_brg": 318.0,
        "surface": "Asphalt",
        "threshold_crossing_height": 50,
        "true_brg": 320.206,
        "width": 98
      }
    }
  },
  "message": "OK",
  "rrl": 2000,
  "status": 200
}
```

#### Notes on selected items

**MSA (Minimum Sector Altitude)** can contain up to 5 sectors. Note the bearings are TO the airport (not a radial FROM the airport) – imagine flying towards the airport to find out which sector you are in. Interpretation goes clockwise.

**Transition level** is returned as -1 if it is not applicable. Many airports don't have a fixed TL, but make this dependent on the atmospheric conditions.

**Runways** contains information on all the runways at the airport and any ILS that might be available. Values are empty or -1 for runways that do not have an ILS:
- `declination` - magnetic declination at the LLZ transmitter
- `gs_angle` - glideslope angle in degrees
- `ils_cat` - certified ILS category
- `llz_brg` - localizer bearing in degrees
- `llz_freq` - localizer frequency in MHz (the "ILS Frequency")
- `llz_ident` - identifier for the ILS

---

### /active_runway – Active runway data {#active_runway--active-runway-data}

**Address:** `https://rtwa.flyrealtraffic.com/v6/active_runway`

*New in v6.* Returns active runway information for a given airport, including wind components (headwind/crosswind), arrival and departure counts, and runway categorization. This endpoint provides pre-computed runway activity data — for live data (toffset=0) it reads from the server's real-time cache, for historical data it reads from archived snapshots.

**POST parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `GUID` | Yes | Session GUID from `/auth` |
| `ICAO` | Yes | ICAO airport code (3-4 characters, e.g. `YSSY`, `KJFK`) |
| `toffset` | No | Time offset in minutes into the past. Default: `0` (live). Maximum: server-configured EFS retention days × 1440 |

**curl example:**
```bash
curl -sH 'Accept-encoding: gzip' \
  -d "GUID=76ff411b-d481-470f-9ce5-5c3cbc71a276&ICAO=YSSY&toffset=0" \
  -X POST https://rtwa.flyrealtraffic.com/v6/active_runway | gunzip -
```

**Example script:**
```bash
python API_active_runway.py -a YSSY
python API_active_runway.py -a KJFK --toff 60    # 60 minutes ago
```

**Example response (YSSY):**

```json
{
    "status": 200,
    "message": "OK",
    "server": "rtw01a",
    "toffset": 0,
    "data": {
        "icao": "YSSY",
        "timestamp": "2026-04-09T00:58:54Z",
        "metar": "YSSY 090000Z 33008KT CAVOK 26/17 Q1017",
        "wind_dir": 330,
        "wind_speed": 8,
        "elevation": 21,
        "active_runways": {
            "arrival": [],
            "departure": [],
            "both": ["RW34L", "RW34R"]
        },
        "runways": {
            "RW07": {"true_brg": 74, "mag_brg": 62, "headwind": -2, "crosswind": 7.8, "arrivals_30m": 0, "departures_30m": 0},
            "RW16L": {"true_brg": 168, "mag_brg": 155, "headwind": -7.6, "crosswind": -2.5, "arrivals_30m": 0, "departures_30m": 0},
            "RW16R": {"true_brg": 168, "mag_brg": 155, "headwind": -7.6, "crosswind": -2.5, "arrivals_30m": 0, "departures_30m": 0},
            "RW25": {"true_brg": 254, "mag_brg": 242, "headwind": 2, "crosswind": -7.8, "arrivals_30m": 0, "departures_30m": 0},
            "RW34L": {"true_brg": 348, "mag_brg": 335, "headwind": 7.6, "crosswind": 2.5, "arrivals_30m": 1, "departures_30m": 4},
            "RW34R": {"true_brg": 348, "mag_brg": 335, "headwind": 7.6, "crosswind": 2.5, "arrivals_30m": 3, "departures_30m": 2}
        }
    }
}
```

**Response fields in `data`:**

| Field | Description |
|-------|-------------|
| `icao` | Airport ICAO code |
| `timestamp` | UTC timestamp of the data snapshot |
| `metar` | Current METAR string |
| `wind_dir` | Surface wind direction in degrees |
| `wind_speed` | Surface wind speed in knots |
| `elevation` | Airport elevation in feet |
| `active_runways` | Categorized runway activity: `arrival` (arrivals only), `departure` (departures only), `both` (arrivals and departures) |
| `runways` | Per-runway data with `true_brg` (true bearing), `mag_brg` (magnetic bearing), `headwind` (positive = headwind, negative = tailwind), `crosswind` (positive = from left, negative = from right), `arrivals_30m` and `departures_30m` (counts in last 30 minutes) |

**Status codes:**

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Invalid request (missing/invalid GUID, ICAO, or toffset out of range) |
| 401 | GUID not found or invalid session |
| 402 | License expired |
| 404 | No active runway data available for the requested airport |
| 500 | Server error |

**Standalone monitor:**

The `active_runway_standalone.py` script provides a continuously updating terminal display that computes runway activity client-side using `/airportinfo`, `/weather`, and `/traffic` endpoints. It color-codes runways: green for arrivals, blue for departures, magenta for both, red for tailwind, white for inactive.

```bash
python active_runway_standalone.py -a YSSY
```

---

### /search – Find a flight in the system {#search--find-a-flight-in-the-system}

**Address:** `https://rtwa.flyrealtraffic.com/v6/search`

This lets you search the RealTraffic data for a flight.

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the GUID obtained from the auth call |
| `toffset` | The time offset into the past in minutes |
| `searchParam` | The parameter to search (see below) |
| `search` | The term to search for |

#### searchParam options

| Value | Description |
|-------|-------------|
| `Callsign` | Search the ATC callsign. Matches any substring. E.g. CPA will match CPA123, CPA345 etc. |
| `CallsignExact` | Search the ATC callsign but only return an exact match. |
| `FlightNumber` | Search the IATA flight code. Matches any substring. E.g. CX will match CX123, CX345 etc. |
| `FlightNumberExact` | Search the IATA flight code but only return the exact match. |
| `From` | Return flights originating from this IATA airport code. E.g. HND will return all flights originating at Tokyo Haneda. |
| `To` | Return flights with this destination IATA airport code. E.g. NRT will return all flights with destination Narita. |
| `Type` | Return all aircraft of this given ICAO aircraft type. E.g. B77W will return all Boeing 777 |
| `Tail` | Return all flights with this tail number. E.g. N1234 will find N1234 as well as N12345 etc. |
| `XPDR` | Return all aircraft with this transponder/squawk code. **New in v6.** |
| `HexID` | Return the aircraft with this exact ICAO hex identifier (case-sensitive, lowercase). **New in v6.** |

#### Example call

```bash
curl -sH 'Accept-encoding: gzip' -d "GUID=76ff411b-d481-470f-9ce5-5c3cbc71a276&toffset=0&searchParam=Callsign&search=CPA1" -X POST https://rtwa.flyrealtraffic.com/v6/search | gunzip -
```

#### Response

```json
{
    "status": 200,
    "message": "OK",
    "rrl": 2000,
    "data": {
        "780a37": ["780a37", 17.709503, 119.143596, 327.99, 38000, 490.6, "1165", "H", "B77W", "B-KQE", 1721602623.48, "BNE", "HKG", "CPA156", 0, 0, "CX156"],
        "780a5c": ["780a5c", -22.671359, 142.890015, 137.29, 35000, 566.1, "5334", "H", "B77W", "B-KQL", 1721602623.5, "HKG", "SYD", "CPA101", 0, 0, "CX101"]
    }
}
```

---

### /tracklog – Retrieve aircraft position history {#tracklog--retrieve-aircraft-position-history}

**Address:** `https://rtwa.flyrealtraffic.com/v6/tracklog`

Returns the historical position track log for a specific aircraft, identified by its ICAO hex code. **New in v6.**

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the GUID obtained from the auth call |
| `hexcode` | the ICAO hex code of the aircraft to track |
| `toffset` | time offset into the past in minutes (0 = live) |

#### Example call

```bash
curl -sH 'Accept-encoding: gzip' -d "GUID=76ff411b-d481-470f-9ce5-5c3cbc71a276&hexcode=7c68a1&toffset=0" -X POST https://rtwa.flyrealtraffic.com/v6/tracklog | gunzip -
```

#### Response

Returns a JSON array of position strings. Each string contains comma-separated values:

```json
[
    "37.5949,-122.3131,10050,297,500,0,1644644579",
    "37.5962,-122.3198,10100,297,498,-64,1644644584",
    "37.5974,-122.3265,10075,297,501,128,1644644589"
]
```

| Field | Description |
|-------|-------------|
| lat | latitude in degrees |
| lon | longitude in degrees |
| alt | altitude in feet |
| track | track in degrees |
| gs | ground speed in knots |
| vs | vertical speed in fpm |
| ts | unix epoch timestamp |

**Notes:**
- Live requests (toffset=0) are available to all authenticated users.
- Historical requests (toffset > 0) require a professional license (type 2).
- Subject to the traffic request rate limit.

---

### /emget – Emergency squawk tracker {#emget--emergency-squawk-tracker}

**Address:** `https://rtwa.flyrealtraffic.com/v6/emget`

Returns active and historical emergency squawk codes (7700, 7600, 7500). **New in v6.**

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the GUID obtained from the auth call |
| `toffset` | time offset into the past in minutes (0 = current emergencies, >0 = historical). Optional, defaults to 0. |

#### Example call

```bash
curl -sH 'Accept-encoding: gzip' -d "GUID=76ff411b-d481-470f-9ce5-5c3cbc71a276&toffset=0" -X POST https://rtwa.flyrealtraffic.com/v6/emget | gunzip -
```

#### Response

```json
{
    "status": 200,
    "emergencies": [
        {
            "hex": "a1b2c3",
            "cs": "UAL123",
            "from": "SFO",
            "to": "LAX",
            "type": "B738",
            "reg": "N12345",
            "squawk": 7700,
            "start": 1712345678,
            "end": 1712346000
        }
    ],
    "count": 1,
    "version": "realtime",
    "server": "rtw01a"
}
```

| Field | Description |
|-------|-------------|
| `emergencies` | array of emergency events |
| `hex` | ICAO hex identifier of the aircraft |
| `cs` | ATC callsign |
| `from` | origin airport IATA code |
| `to` | destination airport IATA code |
| `type` | ICAO aircraft type |
| `reg` | aircraft registration |
| `squawk` | the emergency squawk code (7700=general emergency, 7600=radio failure, 7500=hijack) |
| `start` | unix epoch when the emergency squawk was first observed |
| `end` | unix epoch when the emergency squawk was last observed |
| `count` | total number of emergency events returned |
| `version` | `"realtime"` for live data, `"history"` for historical |

**Notes:**
- Live emergencies (toffset=0) are available to all authenticated users.
- Historical emergencies (toffset > 0) require a professional license (type 2).

---

### /sattile – Satellite imagery tiles (mbtiles) {#sattile--satellite-imagery-tiles-mbtiles}

**Address:** `https://rtwa.flyrealtraffic.com/v6/sattile`

Serves individual 256x256 Web Mercator (XYZ) satellite image tiles from mbtiles files. Replaces the old two-phase `/satimageinfo` + `/satimage` API with a single request per tile. The server automatically selects the correct satellite region based on tile coordinates.

#### POST parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `GUID` | yes | the GUID obtained from the auth call |
| `product` | yes | satellite product: `TC`, `PWV`, `B13`, `RDR`, or `RDW` |
| `z` | yes | zoom level (integer, 3–8 typical) |
| `x` | yes | tile column (XYZ / Web Mercator) |
| `y` | yes | tile row (XYZ / Web Mercator) |
| `toffset` | no | time offset in minutes. 0 = latest (~10 min ago). Default: 0. Max: 20160 (14 days). |
| `region` | no | force a specific overlay region (e.g. `USW_MESO1`, `CONUS`). If omitted, base regions are selected automatically. |

#### Products

| Code | Description |
|------|-------------|
| `TC` | True Color (day/night blend) |
| `PWV` | Precipitable Water Vapour |
| `B13` | Thermal infrared (10.3 µm window channel) |
| `RDR` | Radar color composite |
| `RDW` | Radar greyscale |

#### Regions

**Base regions** (selected automatically by tile longitude):

| Region | Longitude | Satellite | Cadence |
|--------|-----------|-----------|---------|
| `USW` | -180 to -90 | GOES-18 | 10 min |
| `USE` | -90 to -45 | GOES-19 | 10 min |
| `EMEA` | -45 to 45 | MTG-I1 | 10 min |
| `IODC` | 45 to 90 | Meteosat-9 | 15 min |
| `APAC` | 90 to 180 | Himawari-9 | 10 min |

**Overlay regions** (request with `region=NAME`):

| Region | Cadence | Description |
|--------|---------|-------------|
| `USW_CONUS` / `USE_CONUS` | 5 min | GOES CONUS sector |
| `USW_MESO1` / `USW_MESO2` | 1 min | GOES-18 mesoscale (variable position) |
| `USE_MESO1` / `USE_MESO2` | 1 min | GOES-19 mesoscale (variable position) |
| `AHITGT` | 2.5 min | Himawari target area (roaming) |
| `AHIJP` | 2.5 min | Himawari Japan area (fixed) |

#### Tile coordinate formulas

Standard XYZ / Web Mercator (same as OpenStreetMap):

```
n = 2^z
x = floor((lon + 180) / 360 * n)
y = floor((1 - ln(tan(lat_rad) + 1/cos(lat_rad)) / pi) / 2 * n)
```

Where `lat_rad = lat * pi / 180`.

#### Response

**200 OK** — binary image data (JPEG or PNG) with headers:

| Header | Description |
|--------|-------------|
| `Content-Type` | `image/jpeg` or `image/png` |
| `Cache-Control` | `public, max-age=300` |
| `X-Sat-Region` | region that served this tile (e.g. `APAC`) |
| `X-Sat-Ts` | actual timestamp served (e.g. `20260419_0350`) |

**204 No Content** — no tile data for this position/time. Render nothing (transparent).

**400** — invalid `product` (must be one of `TC`, `PWV`, `B13`, `RDR`, `RDW`) or other malformed parameter. JSON body: `{"status": 400, "message": "Invalid product. Must be one of: TC, PWV, B13, RDR, RDW", "server": "..."}`.

**401** — auth failure (bad or expired GUID). JSON body.

**402** — license expired. JSON body.

#### Time handling

The server converts `toffset` to a UNIX epoch, snaps to the region's native cadence boundary, and probes up to 3 cadence steps backward if the exact file is missing. For `toffset=0`, the server looks ~10 minutes back to account for processing delay.

#### Example

```
POST /v6/sattile
GUID=abc123-...&product=TC&z=5&x=28&y=13&toffset=0
```

Response: 24 KB JPEG tile, `X-Sat-Region: APAC`, `X-Sat-Ts: 20260419_0400`.

---

### /weather_tiles – Weather grid tile data {#weather_tiles--weather-grid-tile-data}

**Address:** `https://rtwa.flyrealtraffic.com/v6/weather_tiles`

Provides GFS weather data as grid tiles for weather visualization. Supports multiple zoom levels and layer types. **New in v6.**

#### POST parameters

| Parameter | Description |
|-----------|-------------|
| `GUID` | the GUID obtained from the auth call |

#### GET parameters

The request type and parameters are passed as GET (query string) parameters:

| Parameter | Description |
|-----------|-------------|
| `t` | request type: `summary`, `tiles`, `grid`, or `layer` |

##### t=summary — Available forecast times

Returns available forecast time slots. No additional parameters required.

```json
{
    "times": ["2026040800", "2026040806", "2026040812"],
    "cycle": "2026040800"
}
```

##### t=tiles — Tile resolution for bounding box

| Parameter | Description |
|-----------|-------------|
| `bbox` | bounding box as `latS,lonW,latN,lonE` |

Returns the zoom level and tile boundaries appropriate for the requested area:

```json
{
    "zoom": "z1",
    "resolution": 0.25,
    "tiles": ["0_0", "0_1", "1_0", "1_1"],
    "bbox": [-40, 140, -30, 160]
}
```

Zoom levels:
- `z0`: 0.5° resolution (for spans > 90°)
- `z1`: 0.25° resolution (for spans > 45°)
- `z2`: 0.25° resolution (for smaller spans)

##### t=grid — Grid metadata

| Parameter | Description |
|-----------|-------------|
| `time` | forecast time as `YYYYMMDDHH` |
| `z` | zoom level: `z0`, `z1`, or `z2` (default: z0) |
| `tile` | tile identifier as `X_Y` (optional) |

Returns the grid metadata JSON for the specified time and zoom level.

##### t=layer — Weather layer data

| Parameter | Description |
|-----------|-------------|
| `layer` | layer name (see below) |
| `time` | forecast time as `YYYYMMDDHH` |
| `z` | zoom level: `z0`, `z1`, or `z2` (default: z0) |
| `tile` | tile identifier as `X_Y` (optional) |
| `level` | pressure level in hPa (required for altitude-dependent layers) |
| `bbox` | alternative to z/tile: bounding box as `latS,lonW,latN,lonE` |

Returns binary data (`application/octet-stream`).

**Available layers:**

| Layer | Description | Altitude-dependent |
|-------|-------------|-------------------|
| `stemp` | Surface temperature | No |
| `pressure` | Surface pressure | No |
| `visibility` | Surface visibility | No |
| `cape` | Convective available potential energy | No |
| `freezing` | Freezing level | No |
| `tropo` | Tropopause height | No |
| `ceiling` | Cloud ceiling | No |
| `precip` | Precipitation | No |
| `cloud` | Cloud cover | No |
| `wind` | Wind speed and direction | Yes |
| `temp` | Temperature | Yes |
| `turb` | Turbulence | Yes |
| `dewpt` | Dew point temperature | Yes |

**Valid pressure levels (hPa):** 1000, 975, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 350, 300, 250, 200, 150, 100

---

## Getting the API example scripts to work

The API documentation download includes an example call for each of the APIs. In order to get the python-based examples to work, you will need to install some packages.

### Windows

**Step 1: Download Python Installer**
- Go to https://www.python.org/downloads/windows/
- Click on "Download Python X.X.X"

**Step 2: Run the Installer**
- **Important:** Check the box that says "Add Python X.X to PATH"
- Click "Install Now"

**Step 3: Verify the Installation**
```bash
python --version
pip --version
```

**Step 4: Upgrade pip (Optional but Recommended)**
```bash
python -m pip install --upgrade pip
```

**Step 5: Install required python modules**
```bash
pip install matplotlib requests textalloc cartopy
```

### MacOS/Linux

Python comes preinstalled for these platforms, or is available as a standard package from the distribution channels.

```bash
pip install matplotlib requests textalloc cartopy
```

### Examples

**Show a map of parked aircraft at Sydney:**
```bash
python API_traffic.py --airport YSSY --traffictype parkedtraffic --plot --radius 3
```

**Show a map of live traffic in a 20km radius around Los Angeles:**
```bash
python API_traffic.py --airport KLAX --traffictype locationtraffic --plot plot.jpg
```

**Tying it all together with API_tester.py:**
```bash
./API_tester.py --nummetars 3 -a YSSY
```

---

## Indirect API connections via RT application

If you have multiple data consumers for RT data in your LAN, it is preferable to use the RT App to fetch traffic, as that will broadcast the traffic and weather information in your LAN to any clients without requiring additional licenses for concurrent RT access.

Since version 10, RT has evolved into both a traffic and weather source. Flying with real air traffic in the vicinity is only realistic if the weather experienced by the traffic around you is mirrored in the simulator you are flying.

MSFS 2024 unfortunately does not allow weather injection, but they are using global real-time weather from Meteoblue, so when flying in real-time, the weather will generally match. When flying with historical offsets however, the weather may not match.

Both X-Plane and PSX fully support weather injection including historical weather.

RealTraffic obtains traffic and weather information for the location desired, either by tracking the flight simulator's location (information which you have to provide or is already provided by the plugin in use), or by using the spotter location.

---

### Integrating your own flight simulator plugin

You need to provide your location, and ideally attitude, in regular intervals to the RT application. The RT application will transmit weather and traffic as UDP packets in approximately 2 second intervals, traffic is limited to approximately 100 NM of range around the center of the position provided, and weather is given for the 7 nearest airports providing METARs as well as actual conditions at your present altitude, to include winds and temperatures aloft, turbulence, and cloud information.

---

### Providing your simulator position to RealTraffic

Your simulator plugin needs to provide a **TCP socket server connection**. By default, RealTraffic expects **port 10747** (configurable in RT Settings).

The RT application will attempt to connect to your plugin by opening a TCP connection and will start providing data once established.

Once your plugin detects that RealTraffic has connected to it, transmit the following parameters ideally at **5 Hz** (5 times per second):

| Parameter | Unit/Format |
|-----------|-------------|
| Pitch | radians * 100000 |
| Bank | radians * 100000 * -1 |
| Heading (or Track) | radians |
| Altitude | feet * 1000 |
| True air speed | meters per second |
| Latitude | radians |
| Longitude | radians |

All preceded by the characters `Qs121=`

**Example string:**
```
Qs121=6747;289;5.449771266137578;37988724;501908;0.6564195830703577;-2.1443275933742236
```

**Java code example:**
```java
message = String.format(Locale.US, "Qs121=%d;%d;%.15f;%d;%d;%.15f;%.15f",
    (int)(pitch_in_degs * 100000 * d2r),
    (int)(bank_in_degs * 100000 * d2r) * -1,
    track_in_degs * d2r,
    (int)(altitude_in_m * 3028),
    TAS_in_mps,
    latitude * d2r,
    longitude * d2r);
```

If you want Foreflight and/or Garmin Pilot apps to be supported correctly, you must inject position and attitude updates at 5 Hz.

---

### Using the Destination Traffic/Weather feature

To receive destination traffic and weather on ports 49005/49006, send:

```
Qs376=YSSY;KLAX
```

This sets the destination to KLAX and starts broadcasting destination traffic and weather. This feature is only available for professional license holders. The first airport (origin airport) is disregarded.

---

### How to find out license and version information

Send the string `Qs999=version` to RT and you'll receive:

```json
{ "version":"10.0.240", "level": 2 }
```

Where:
- `version` is the current version in format major.minor.build
- `level`: 0 = pre-v9-release standard license, 1 = post-v9-release standard license, 2 = professional license

---

### Controlling the time offset from the simulator

**Query who's in control:**
```
Qs999=timeoffsetcontrol=?
```

Response:
```json
{ "timeoffsetcontrol": "Simulator" }
```
or
```json
{ "timeoffsetcontrol": "RealTraffic" }
```

**Set control:**
```
Qs999=timeoffsetcontrol=Simulator
```
or
```
Qs999=timeoffsetcontrol=RealTraffic
```

**Set the time:**
```
Qs123=1674956315329
```

Send the UTC time formatted as epoch milliseconds with a `Qs123` message. This only works for professional licenses.

---

### Reading weather and traffic information

RealTraffic broadcasts all traffic and weather information via UDP on the local network, but can provide much more detailed weather via the TCP connection. The broadcast weather information pertains to the nearest 7 airports. ADS-B altitudes for traffic are already pressure corrected.

---

### UDP Weather Broadcasts

Weather messages are broadcast as UDP packets once every 10 seconds on **port 49004** containing a JSON string.

```json
{
    "ICAO": "KMCE",
    "QNH": 1019.7,
    "METAR": "KMCE 130453Z AUTO 14005KT 6SM -RA BR OVC043 13/12 A3011 RMK AO2 RAB0354E08B11E21B37 SLP197 P0003 T01330117",
    "TA": 18000,
    "locWX": {
        "Info": "2023-03-13_0558Z",
        "ST": 11.4,
        "SWSPD": 9.59,
        "SWDIR": 146.29,
        "SVis": 18224,
        "LLCC": 17,
        "MLCC": 49.7,
        "HLCC": 0,
        "DZDT": -0.0302,
        "PRR": 0.55,
        "T": -52.57,
        "WDIR": 268.4,
        "WSPD": 137.27,
        "TPP": 10084.52,
        "SLP": 1019.73,
        "Profiles": "RTFX1 ^N3737.2 ^W12034.8 ^FL381 265/071 -51 ^FL361 267/075 -52 ^FL341 269/078 -53 ^FL321 269/082 -51 ^FL301 268/086 -48 ^^"
    },
    "AM": [
        "KMER 130535Z AUTO 17007KT 10SM SCT028 OVC035 13/13 A3012 RMK AO1",
        "KCVH 130535Z AUTO 00000KT 10SM OVC012 13/12 A3013 RMK A01"
    ]
}
```

| Field | Description |
|-------|-------------|
| `ICAO` | the ICAO code of the nearest airport |
| `QNH` | the reported pressure in hPa |
| `METAR` | the full METAR received |
| `TA` | the transition altitude in ft |
| `locWX` | the location weather at the present position |
| `AM` | additional METARs (up to 6 nearest METARs in forward looking direction) |

**locWX fields (simplified for UDP broadcast):**
- `ST`: surface temperature in C
- `SWSPD`: surface wind speed in km/h
- `SWDIR`: surface wind direction in degrees
- `SVis`: surface visibility in meters
- `PRR`: precipitation rate in mm/h
- `LLCC`: low level cloud cover in percent
- `MLCC`: medium level cloud cover in percent
- `HLCC`: high level cloud cover in percent
- `DZDT`: turbulence indicator
- `T`: OAT/SAT in C
- `WDIR`: wind direction in degrees
- `WSPD`: wind speed in km/h
- `TPP`: tropopause height in meters
- `SLP`: sea level pressure in hPa
- `Profiles`: vertical cross section in Aerowinx Format D

---

### Traffic data formats

Traffic data is broadcast as UDP packets:

| Format | Port | Description |
|--------|------|-------------|
| XTRAFFICPSX | 49002 | Foreflight format |
| RTTFC | 49005 | RT Traffic format |
| RTDEST | 49006 | Destination Traffic |

Additionally, the simulator position is re-distributed as XGPS and XATT messages on port 49002.

---

### XTRAFFIC format

Broadcast on UDP port 49002:

```
XTRAFFICPSX,hexid,lat,lon,alt,vs,airborne,hdg,spd,cs,type
```

| Field | Description |
|-------|-------------|
| `hexid` | transponder's unique hexadecimal ID |
| `lat` | latitude in degrees |
| `lon` | longitude in degrees |
| `alt` | altitude in feet |
| `vs` | vertical speed in ft/min |
| `airborne` | 1 or 0 |
| `hdg` | track (actually true track) |
| `spd` | speed in knots |
| `cs` | ICAO callsign |
| `type` | ICAO aircraft type |

**GPS message:**
```
XGPSPSX,lon,lat,alt,track,gsp
```
- `alt` in meters, `gsp` in meters per second

**Attitude message:**
```
XATTPSX,hdg,pitch,roll
```
- `hdg` = true heading, `pitch` positive = pitch up, `roll` positive = right roll

---

### RTTFC/RTDEST format

This format contains almost all information available from the data sources. The broadcast is 43 comma-separated fields (positions 0–42), one packet per aircraft, UDP to port 49005 for RTTFC.

```
RTTFC,hexid,lat,lon,baro_alt,baro_rate,airborne,track,gsp,cs_icao,ac_type,ac_tailno,from_iata,to_iata,timestamp,source,cs_iata,msg_type,alt_geom,IAS,TAS,Mach,track_rate,roll,mag_heading,true_heading,geom_rate,emergency,category,nav_qnh,nav_altitude_mcp,nav_altitude_fms,nav_heading,nav_modes,seen,rssi,winddir,windspd,OAT,TAT,isICAOhex,baro_alt_uncorrected,authentication
```

| Index | Field | Type | Description |
|-------|-------|------|-------------|
| 0 | Format | string | `RTTFC` = location traffic, `RTDEST` = destination traffic, `RTPARK` = parked traffic, `RTBUF=N` = buffer-fill snapshot index N |
| 1 | hexid | int | transponder's unique ICAO 24-bit address, transmitted as **decimal** (not hex) |
| 2 | lat | float (5dp) | latitude in degrees, south negative |
| 3 | lon | float (5dp) | longitude in degrees, west negative |
| 4 | baro_alt | int | barometric altitude in feet, **corrected for local QNH** (raw value at field 41) |
| 5 | baro_rate | int | barometric vertical rate in feet per minute |
| 6 | airborne | int | airborne flag: **1 = airborne, 0 = on ground** (inverted from the server's ground flag) |
| 7 | track | float (2dp) | true track in degrees |
| 8 | gsp | float (2dp) | ground speed in knots |
| 9 | cs_icao | string | ICAO call sign |
| 10 | ac_type | string | aircraft type (ICAO code) |
| 11 | ac_tailno | string | aircraft registration |
| 12 | from_iata | string | origin IATA code |
| 13 | to_iata | string | destination IATA code |
| 14 | timestamp | float (1dp) | unix epoch timestamp (seconds with one decimal) |
| 15 | source | string | data provider letter (e.g. `X2`, `V`, `F`) — see also field 17 |
| 16 | cs_iata | string | IATA call sign (flight number) |
| 17 | msg_type | string | message-source type, prefixed with the provider letter and an underscore (see Message source types below) |
| 18 | alt_geom | int | geometric altitude in feet (WGS84 GPS altitude) |
| 19 | IAS | int | indicated air speed in knots |
| 20 | TAS | int | true air speed in knots |
| 21 | Mach | float (3dp) | Mach number |
| 22 | track_rate | float (1dp) | rate of change of track in deg/sec |
| 23 | roll | float (1dp) | roll in degrees (negative = left) |
| 24 | mag_heading | float (2dp) | magnetic heading in degrees |
| 25 | true_heading | float (2dp) | true heading in degrees |
| 26 | geom_rate | int | geometric vertical rate in feet per minute |
| 27 | emergency | string | emergency status (`none` if no emergency) |
| 28 | category | string | aircraft transmitter category (see Transmitter categories) |
| 29 | nav_qnh | float (1dp) | QNH setting in the MCP/FCU, hPa |
| 30 | nav_altitude_mcp | int | altitude dialed into the MCP/FCU, feet |
| 31 | nav_altitude_fms | int | altitude programmed in the FMS, feet |
| 32 | nav_heading | float (2dp) | heading set in the MCP, degrees |
| 33 | nav_modes | string | autopilot modes pipe-separated (e.g. `autopilot\|vnav\|lnav\|tcas`), or `null` |
| 34 | seen | float (1dp) | seconds since the last position update |
| 35 | rssi | float (1dp) | signal strength at the receiver, dBm |
| 36 | winddir | int | wind direction in degrees true |
| 37 | windspd | int | wind speed in knots |
| 38 | OAT | int | outside air temperature / SAT, °C |
| 39 | TAT | int | total air temperature, °C |
| 40 | isICAOhex | int | 1 if the hexid is ICAO-assigned, 0 otherwise |
| 41 | baro_alt_uncorrected | int | raw ADS-B barometric altitude (1013.25 hPa reference) in feet, before the QNH correction applied to field 4 |
| 42 | authentication | int | checksum (safe to ignore) |

**Fields not currently included in the broadcast:** the server traffic feed also carries `nic`, `rc`, `nic_baro`, `nac_p`, `nac_v`, `alert`, `spi`, and (as of the v6.x schema update) the 3-letter ICAO `operator` code. These are present in the upstream `/traffic` response but are not emitted by the RTTFC packet.

**Source field values:**
- `adsb`: reduced data ADS-B field
- `adsb_icao`: messages from Mode S or ADS-B transponder
- `adsb_icao_nt`: ADS-B equipped "non-transponder" emitter
- `adsr_icao`: rebroadcast ADS-B message
- `tisb_icao`: traffic information about non-ADS-B target
- `adsc`: ADS-C (satellite downlink)
- `mlat`: MLAT position
- `other`: quality/source unknown
- `mode_s`: ModeS data only
- `adsb_other`: anonymized ICAO address
- `adsr_other`: rebroadcast of adsb_other
- `est`: estimated position

All source fields are preceded by `?_` where `?` is a letter identifying the data provider. If preceded by `ID_`, the data is interpolated.

**Example** (airborne aircraft — note field 6 = 1):
```
RTTFC,10750303,-33.7964,152.3938,20375,1376,1,66.77,484.30,UAL842,B789,N35953,SYD,LAX,1645144889.8,X2,UA842,F_adsb_icao,21350,343,466,0.744,-0.0,0.5,54.49,67.59,1280,none,A5,1012.8,35008,-1,54.84,autopilot|vnav|lnav|tcas,0.0,-20.8,227,19,-15,14,1,26235,268697
```

Field-by-field for this example:

| Pos | Value | Field |
|-----|-------|-------|
| 0 | `RTTFC` | format label |
| 1 | `10750303` | hexid (decimal of `A4179F`) |
| 2 | `-33.7964` | lat |
| 3 | `152.3938` | lon |
| 4 | `20375` | baro_alt (QNH-corrected) |
| 5 | `1376` | baro_rate (ft/min, climbing) |
| 6 | `1` | airborne |
| 7 | `66.77` | track |
| 8 | `484.30` | gsp |
| 9 | `UAL842` | cs_icao |
| 10 | `B789` | ac_type |
| 11 | `N35953` | ac_tailno |
| 12 | `SYD` | from_iata |
| 13 | `LAX` | to_iata |
| 14 | `1645144889.8` | timestamp |
| 15 | `X2` | source provider |
| 16 | `UA842` | cs_iata |
| 17 | `F_adsb_icao` | msg_type |
| 18 | `21350` | alt_geom |
| 19 | `343` | IAS |
| 20 | `466` | TAS |
| 21 | `0.744` | Mach |
| 22 | `-0.0` | track_rate |
| 23 | `0.5` | roll |
| 24 | `54.49` | mag_heading |
| 25 | `67.59` | true_heading |
| 26 | `1280` | geom_rate |
| 27 | `none` | emergency |
| 28 | `A5` | category (heavy jet) |
| 29 | `1012.8` | nav_qnh |
| 30 | `35008` | nav_altitude_mcp |
| 31 | `-1` | nav_altitude_fms (unknown) |
| 32 | `54.84` | nav_heading |
| 33 | `autopilot\|vnav\|lnav\|tcas` | nav_modes |
| 34 | `0.0` | seen |
| 35 | `-20.8` | rssi |
| 36 | `227` | winddir |
| 37 | `19` | windspd |
| 38 | `-15` | OAT |
| 39 | `14` | TAT |
| 40 | `1` | isICAOhex |
| 41 | `26235` | baro_alt_uncorrected |
| 42 | `268697` | authentication |

---

### Requesting Parked Traffic

**Request parked traffic (one-time broadcast):**
```
Qs999=sendparked[,bottom,left,top,right]
```

**Start periodic parked traffic broadcasts (every 60 seconds):**
```
Qs999=startparked[,bottom,left,top,right]
```

**Stop periodic broadcasts:**
```
Qs999=stopparked
```

**Query status:**
```
Qs999=statusparked
```

The `bottom,left,top,right` parameters specify the latitude box within which parked traffic is retrieved. If omitted, assumes a 6 NM radius around the present position.

**RTPARK format (broadcast via UDP on port 49005):**
```
RTPARK,hexid,lat,lon,callsign,type,registration,gate,timestamp
```

| Index | Field |
|-------|-------|
| 0 | RTPARK (format descriptor) |
| 1 | hexid |
| 2 | latitude |
| 3 | longitude |
| 4 | callsign |
| 5 | aircraft type |
| 6 | registration |
| 7 | gate ID (airport ICAO code and gate number separated by underscore) |
| 8 | timestamp (epoch seconds) |

**Example:**
```
RTPARK,76cd72,-33.940487,151.163958,SIA231,A388,9V-SKR,YSSY_I61,1768005636.7
```

---

### Using Satellite Imagery

As of RT version 8, global real-time satellite coverage is available. Access by creating an HTTP connection to the host where RT is running on **port 60888**.

**Metadata endpoint (GET /):**
```json
{ "timestamp": 1766530200, "lower_left_latitude": -40, "lower_left_longitude": 140, "product": "TC" }
```

**Image endpoint (GET /data):** Returns 1600x1600 pixels PNG image

**Raw radar endpoint (GET /rdw):** Always available regardless of selected overlay

#### Image types

| Type | Description |
|------|-------------|
| `TC` | True color (with IR merged for nighttime) |
| `B13` | Channel 13 (thermal infrared) |
| `PWV` | Precipitable water vapour |
| `RDR` | Artificial radar image |

#### Geostationary satellites

| Satellite | Position |
|-----------|----------|
| GOES17 | 137.2°W |
| GOES16 | 75.2°W |
| Meteosat 10 | 0° |
| Meteosat 8 | 45°E |
| Himawari 9 | 140.7°E |

Meteosat updates every 15 minutes, others every 10 minutes. Best resolution: Meteosat 1km/pixel, others 500m/pixel.

Processing time is approximately 8 minutes, so lag behind real-time is between 8 and 18 minutes.

Images are 1600 x 1600 pixels, spanning 10 x 10 degrees in a Mercator projection.

#### Image descriptions

- **True color image:** Color enhanced rendition of the earth with all clouds. Native resolution 500m/pixel at sub-satellite point.

- **False color infrared (B13):** 10.4 micrometer thermal infrared band. Cloud top temperatures of -40C and less are rendered in color, useful for identifying convective activity.

- **PWV (Precipitable Water Vapour):** False color composite of three water vapor channels (blue=9km, green=5km, red=3km altitude). Useful for Jetstream locations and clear air turbulence areas.

- **RDR (Radar image):** Estimated radar returns as they would appear on an on-board radar system.

- **RDW (Raw radar image):** Grayscale version for plugin developers to implement gain control. Full white = strongest returns.

---

*End of documentation*
