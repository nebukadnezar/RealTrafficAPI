#!/usr/bin/env python3
import requests
import json
import time
import sys
import os
import signal
import math
import platform
from datetime import datetime, timezone, timedelta
from argparse import ArgumentParser
from collections import defaultdict, deque
from math import sin, cos, radians

print_callsign = ""
print_debug = False

class ANSIColors:
    def __init__(self):
        self.is_windows = platform.system().lower() == "windows"

        # Initialize Windows console for ANSI support if needed
        if self.is_windows:
            from ctypes import windll
            kernel32 = windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

        # Define the ANSI escape codes
        self.RESET = '\033[0m'
        self.FG_RED = '\033[31m'
        self.FG_GREEN = '\033[32m'
        self.FG_CYAN = '\033[36m'
        self.BOLD = '\033[1m'

    def get_color(self, color_code):
        # Return the appropriate color code
        return color_code if not self.is_windows or os.getenv('TERM') else ''

# Create a global instance of ANSIColors
COLORS = ANSIColors()

def get_license():
    is_windows = platform.system().lower() == "windows"
    file_path = os.path.expanduser("~/AppData/Roaming/InsideSystems/RealTraffic.lic" if is_windows
                                 else "~/Documents/.InsideSystems/RealTraffic.lic")

    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as file:
                return json.load(file)['License']
        except (json.JSONDecodeError, IOError, KeyError):
            print("Error reading license file")
    return None

def calculate_wind_components(runway_heading, wind_direction, wind_speed):
    """Calculate headwind and crosswind components for a runway."""
    wind_angle = radians((runway_heading - wind_direction) % 360)
    headwind = wind_speed * cos(wind_angle)
    crosswind = wind_speed * sin(wind_angle)
    return headwind, crosswind

def parse_metar_wind(metar):
    """Extract wind direction and speed from METAR string."""
    try:
        parts = metar.split()
        for part in parts:
            if part.endswith('Z'):
                continue

            if 'KT' in part or 'MPS' in part:
                units = 'MPS' if 'MPS' in part else 'KT'

                if part.startswith('VRB'):
                    speed_str = part[3:part.find(units)]
                    speed = float(speed_str)
                    if units == 'MPS':
                        speed = speed * 1.94384
                    return 0, speed

                direction = float(part[0:3])
                speed_end = part.find('G') if 'G' in part else part.find(units)
                speed = float(part[3:speed_end])

                if units == 'MPS':
                    speed = speed * 1.94384

                return direction, speed

    except (ValueError, IndexError) as e:
        print(f"Error parsing METAR wind: {e}")

    return -1, -1

class AircraftState:
    def __init__(self, print_debug):
        self.positions = deque(maxlen=10)  # Store last 10 positions
        self.last_update = None
        self.detected_runway = None
        self.print_debug = print_debug

    def update(self, lat, lon, alt, gs, track, timestamp, callsign=None):  # Add callsign parameter
        self.positions.append({
            'lat': lat,
            'lon': lon,
            'alt': alt,
            'gs': gs,
            'track': track,
            'time': timestamp,
            'callsign': callsign  # Store callsign in position data
        })
        self.last_update = timestamp

    def get_altitude_trend(self):
        """Calculate if aircraft is descending over the stored positions."""
        if len(self.positions) < 2:
            return 0

        first_alts = [p['alt'] for p in list(self.positions)[:3]]  # First few positions
        last_alts = [p['alt'] for p in list(self.positions)[-3:]]  # Last few positions

        return sum(last_alts)/len(last_alts) - sum(first_alts)/len(first_alts)

    def get_speed_trend(self):
        """Calculate if aircraft speed is increasing."""
        if len(self.positions) < 2:
            return 0

        first_speeds = [p['gs'] for p in list(self.positions)[:3]]
        last_speeds = [p['gs'] for p in list(self.positions)[-3:]]

        return sum(last_speeds)/len(last_speeds) - sum(first_speeds)/len(first_speeds)

    def analyze_runway_ops(self, runway_data, field_alt):
        """Analyze if aircraft is arriving or departing from any runway."""
        if len(self.positions) < 3:  # Need at least 3 positions for analysis
            return None, None

        latest = self.positions[-1]

        # Check each runway
        for rwy_id, rwy_data in runway_data.items():
            # Calculate position relative to runway
            lat_diff = latest['lat'] - rwy_data['lat']
            lon_diff = latest['lon'] - rwy_data['lon']

            # Convert runway heading to radians
            rwy_rad = math.radians(rwy_data['true_brg'])
            rx = math.sin(rwy_rad)
            ry = math.cos(rwy_rad)

            # Calculate cross track and along track distance
            cross_track = abs(lon_diff * ry - lat_diff * rx) * 60  # NM
            along_track = -(lon_diff * rx + lat_diff * ry) * 60    # NM

            # Check track alignment with runway
            track_diff = abs((latest['track'] - rwy_data['true_brg'] + 180) % 360 - 180)

            # Common criteria
            if cross_track > 0.05:  # Within 0.1 NM of centerline
                continue

            alt_trend = self.get_altitude_trend()
            speed_trend = self.get_speed_trend()

            # Check for arrival
            if (along_track > 0 and  # In front of threshold
                alt_trend < 0 and    # Descending
                speed_trend < 10 and    # decelerating, and not accelerating massively
                track_diff < 5 and   # Aligned with runway
                latest['gs'] > 50 and
                latest['alt'] - field_alt < 3000):

                if self.print_debug:
                    print(f"{latest.get('callsign')} {rwy_id}: XTK: {cross_track:.3f} DTG: {along_track:.3f} BRG: {track_diff:.3f} Alt_trend: {alt_trend:.1f} speed_trend: {speed_trend:.1f}")

                return "arrival", rwy_id

            # Check for departure
            if (along_track < 0 and     # Near the runway
                speed_trend > 10 and          # Accelerating
                latest['gs'] > 40 and        # Moving fast enough
                latest['alt'] - field_alt < 1000 and
                track_diff < 20):            # Roughly aligned with runway
                if self.print_debug:
                    print(f"{latest.get('callsign')} {rwy_id}: XTK: {cross_track:.3f} DTG: {along_track:.3f} BRG: {track_diff:.3f} Alt_trend: {alt_trend:.1f} speed_trend: {speed_trend:.1f}")

                return "departure", rwy_id
        return None, None

class RunwayMonitor:
    def __init__(self, airport, license_key, toff, server, api, print_debug):
        self.airport = airport
        self.license = license_key
        self.server = f"https://{server}.flyrealtraffic.com/"
        self.api_version = api
        self.header = {"Accept-encoding": "gzip"}
        self.toff = toff
        self.print_debug = print_debug

        self.auth_url = f"{self.server}/{api}/auth"
        self.deauth_url = f"{self.server}/{api}/deauth"
        self.airportinfo_url = f"{self.server}/{api}/airportinfo"
        self.traffic_url = f"{self.server}/{api}/traffic"
        self.weather_url = f"{self.server}/{api}/weather"

        self.approach_history = defaultdict(lambda: {})
        self.current_approaches = defaultdict(set)
        self.departure_history = defaultdict(lambda: {})
        self.current_departures = defaultdict(set)
        self.aircraft_states = {}
        self.last_update = datetime.now()

        self.metar = ""
        self.wind_direction = -1
        self.wind_speed = -1

        self.authenticate()
        time.sleep(self.traffic_rate_limit)
        self.get_airport_info()

    def authenticate(self):
        print("Authenticating...")
        payload = {"license": self.license, "software": "RunwayMonitor"}
        response = requests.post(self.auth_url, payload, headers=self.header)
        data = response.json()

        if data["status"] != 200:
            raise Exception(f"Authentication failed: {data['message']}")

        self.guid = data["GUID"]
        self.traffic_rate_limit = data["rrl"] / 1000
        self.weather_rate_limit = data["wrrl"] / 1000

    def get_airport_info(self):
        payload = {"GUID": self.guid, "ICAO": self.airport}
        response = requests.post(self.airportinfo_url, payload, headers=self.header)
        data = response.json()

        if data["status"] != 200:
            raise Exception(f"Failed to get airport info: {data['message']}")

        self.airport_data = data["data"]
        self.airport_position = (
            self.airport_data["airport"]["ref_lat"],
            self.airport_data["airport"]["ref_lon"]
        )

    def get_weather(self):
        print("Fetching weather...")
        payload = {
            "GUID": self.guid,
            "querytype": "locwx",
            "lat": self.airport_position[0],
            "lon": self.airport_position[1],
            "alt": 0,
            "airports": self.airport,
            "toffset": int(self.toff)
        }

        response = requests.post(self.weather_url, payload, headers=self.header)
        data = response.json()

        if data["status"] != 200:
            raise Exception(f"Failed to get weather: {data['message']}")

        self.metar = data["data"]["METAR"]
        self.wind_direction, self.wind_speed = parse_metar_wind(self.metar)

        return data["data"]

    def get_traffic(self):
        print("Fetching traffic...")
        lat_range = 15/60
        lon_range = lat_range/cos(radians(self.airport_position[0]))

        payload = {
            "GUID": self.guid,
            "querytype": "locationtraffic",
            "top": self.airport_position[0] + lat_range,
            "bottom": self.airport_position[0] - lat_range,
            "left": self.airport_position[1] - lon_range,
            "right": self.airport_position[1] + lon_range,
            "toffset": int(self.toff)
        }

        response = requests.post(self.traffic_url, payload, headers=self.header)
        data = response.json()

        if data["status"] != 200:
            raise Exception(f"Failed to get traffic: {data['message']}")

        return data["data"]

    def update_runway_usage(self, traffic_data, runway_data, field_alt):
        """Update both arrivals and departures using aircraft state tracking."""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(minutes=30)

        # Clean old history entries
        for runway in self.approach_history:
            self.approach_history[runway] = {
                callsign: time for callsign, time in self.approach_history[runway].items()
                if time > cutoff_time
            }
        for runway in self.departure_history:
            self.departure_history[runway] = {
                callsign: time for callsign, time in self.departure_history[runway].items()
                if time > cutoff_time
            }

        # Update aircraft states
        for aircraft in traffic_data.values():
            callsign = aircraft[13]
            if any(x is None for x in [aircraft[1], aircraft[2], aircraft[3], aircraft[4], aircraft[5]]):
                continue

            if callsign not in self.aircraft_states:
                self.aircraft_states[callsign] = AircraftState(self.print_debug)

            self.aircraft_states[callsign].update(
                lat=aircraft[1],
                lon=aircraft[2],
                alt=aircraft[4],
                gs=aircraft[5],
                track=aircraft[3],
                timestamp=current_time,
                callsign=callsign  # Add this line
            )

        # Clean old aircraft states
        self.aircraft_states = {
            callsign: state
            for callsign, state in self.aircraft_states.items()
            if (current_time - state.last_update).total_seconds() < 120
        }

        # Reset current operations
        new_approaches = defaultdict(set)
        new_departures = defaultdict(set)

        # Analyze each aircraft
        for callsign, state in self.aircraft_states.items():
            op_type, rwy = state.analyze_runway_ops(runway_data, field_alt)

            if op_type == "arrival":
                new_approaches[rwy].add(callsign)
                if callsign not in self.current_approaches[rwy]:
                    self.approach_history[rwy][callsign] = current_time

            elif op_type == "departure":
                new_departures[rwy].add(callsign)
                if callsign not in self.current_departures[rwy]:
                    self.departure_history[rwy][callsign] = current_time

        self.current_approaches = new_approaches
        self.current_departures = new_departures

    def display_runway_info(self, weather_data, traffic_data):
        if print_callsign == "" and not self.print_debug:
            if platform.system().lower() == "windows":
                os.system('cls')
            else:
                print("\033[2J\033[H")

        print(f"{COLORS.get_color(COLORS.FG_GREEN)}METAR {self.airport}:{COLORS.get_color(COLORS.RESET)}")
        print(f"{COLORS.get_color(COLORS.FG_CYAN)}{self.metar}{COLORS.get_color(COLORS.RESET)}\n")

        if self.wind_direction != -1 and self.wind_speed != -1:
            print(f"Surface wind: {self.wind_direction:03.0f}° at {self.wind_speed:.0f} knots\n")
        else:
            print("Unable to parse wind from METAR\n")

        print("Runway Analysis:")
        print("RWY    HDG(T) HDG(M)  Headwind Crosswind   ARR (30m)    DEP (30m)")
        print("-" * 65)

        for rwy_id, rwy_data in self.airport_data['runways'].items():
            if self.wind_direction != -1 and self.wind_speed != -1:
                headwind, crosswind = calculate_wind_components(
                    rwy_data['true_brg'],
                    self.wind_direction,
                    self.wind_speed
                )
            else:
                headwind, crosswind = 0, 0

            arr_count = len(self.approach_history[rwy_id])
            dep_count = len(self.departure_history[rwy_id])
            current_arr = len(self.current_approaches[rwy_id])
            current_dep = len(self.current_departures[rwy_id])

            # Get current aircraft
            arriving = ",".join(self.current_approaches[rwy_id])
            departing = ",".join(self.current_departures[rwy_id])

            # Format with colors (red for tailwind)
            color = COLORS.get_color(COLORS.FG_RED) if headwind < 0 else COLORS.get_color(COLORS.RESET)
            print(f"{color}{rwy_id:<7} {rwy_data['true_brg']:03.0f}°   {rwy_data['mag_brg']:03.0f}°  "
                  f"{headwind:+6.1f}    {crosswind:+6.1f}    {arr_count:3d} ({current_arr})"
                  f"    {dep_count:3d} ({current_dep}){COLORS.get_color(COLORS.RESET)}")

            # Show active aircraft if any
            if arriving:
                print(f"  Arriving: {arriving}")
            if departing:
                print(f"  Departing: {departing}")

        print("\nTraffic time: %s UTC" % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - self.toff * 60)))

    def run(self):
        """Main loop to continuously monitor and display runway information."""
        try:
            while True:
                weather_data = self.get_weather()
                traffic_data = self.get_traffic()

                self.update_runway_usage(traffic_data, self.airport_data['runways'],
                                       self.airport_data['airport']['elevation'])
                self.display_runway_info(weather_data, traffic_data)

                # Wait for rate limit
                time.sleep(max(self.traffic_rate_limit, self.weather_rate_limit))

        except KeyboardInterrupt:
            print("\nShutting down...")
            # Deauthenticate
            requests.post(self.deauth_url, {"GUID": self.guid}, headers=self.header)

def main():
    global print_callsign
    parser = ArgumentParser(description='Airport Runway Wind and Traffic Monitor')
    parser.add_argument('-a', '--airport', type=str, required=True,
                       help='ICAO code of airport to monitor')
    parser.add_argument('-l', '--license', help='Your RealTraffic license')
    parser.add_argument('-p', '--print_callsign', default="", help='callsign to print for debugging')
    parser.add_argument('-d', '--print_debug', action='store_true', help='print debug info')
    parser.add_argument('--server', default="rtwa", help="Server to connect to")
    parser.add_argument('-api', '--api', default="v5", help="API version to use")
    parser.add_argument('--toff', default=0, type=float, help="time offset in minutes")

    args = parser.parse_args()

    if args.license is None:
        args.license = get_license()
        if args.license is None:
            print("No license found. Please provide a license with -l")
            sys.exit(1)

    print_callsign = args.print_callsign
    print_debug = args.print_debug

    monitor = RunwayMonitor(args.airport, args.license, args.toff, args.server, args.api, print_debug)
    monitor.run()

if __name__ == '__main__':
    main()