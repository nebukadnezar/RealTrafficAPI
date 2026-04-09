#!/usr/bin/env python3

# API tester for /active_runway API

import requests
import json
import time
import sys
import os
import platform
from datetime import datetime
from argparse import ArgumentParser

class ANSIColors:
    def __init__(self):
        self.is_windows = platform.system().lower() == "windows"
        if self.is_windows:
            from ctypes import windll
            kernel32 = windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

        self.RESET = '\033[0m'
        self.FG_RED = '\033[31m'
        self.FG_GREEN = '\033[32m'
        self.FG_BLUE = '\033[34m'
        self.FG_MAGENTA = '\033[35m'
        self.FG_CYAN = '\033[36m'

    def get_color(self, color_code):
        return color_code if not self.is_windows or os.getenv('TERM') else ''

COLORS = ANSIColors()

#######################################################################################################
# Fetch the license information
def get_license():
    # Determine the operating system
    is_windows = platform.system().lower() == "windows"

    # Set the appropriate file path based on the operating system
    if is_windows:
        file_path = os.path.expanduser("~/AppData/Roaming/InsideSystems/RealTraffic.lic")
    else:
        file_path = os.path.expanduser("~/Documents/.InsideSystems/RealTraffic.lic")

    # Check if the file exists
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as file:
                json_data = json.load(file)
            # return the license
            return json_data['License']
        except json.JSONDecodeError:
            print("Error: The license file is not valid JSON.")
        except IOError:
            print("Error: Unable to read the license file.")

    return None


#######################################################################################################
# Custom formatter to pretty print the data
def custom_json_formatter(obj, indent=0, dont_expand=['data']):
    if isinstance(obj, dict):
        result = "{\n"
        for key, value in obj.items():
            result += ' ' * (indent + 4) + f'"{key}": '
            if key in dont_expand:
                result += json.dumps(value)
            else:
                result += custom_json_formatter(value, indent + 4, dont_expand)
            result += ",\n"
        result = result.rstrip(",\n") + "\n" + ' ' * indent + "}"
    elif isinstance(obj, list):
        result = "[\n"
        for item in obj:
            result += ' ' * (indent + 4) + custom_json_formatter(item, indent + 4, dont_expand) + ",\n"
        result = result.rstrip(",\n") + "\n" + ' ' * indent + "]"
    else:
        result = json.dumps(obj)
    return result


#######################################################################################################
#######################################################################################################
if __name__ == '__main__':

    parser = ArgumentParser(description='RealTraffic /active_runway API Tester')

    # Add optional argument, with given default values if user gives no arg
    parser.add_argument('-l', '--license', help='Your RealTraffic license, e.g. AABBCC-1234-AABBCC-123456')
    parser.add_argument('-a', '--airport', type=str, default='YSSY', help='ICAO code of airport. Default: YSSY')
    parser.add_argument('--toff', default=0, type=float, help="time offset in minutes")
    parser.add_argument('-api', '--api', default="v6", type=str, help="API endpoint to call, default v6")
    parser.add_argument('--server', default="rtwa", type=str, help="server name to connect to")

    args = parser.parse_args()

    if args.license == None:
        args.license = get_license()

    if args.license == None:
        print("Unable to load the license from the RealTraffic.lic file.")
        print("You need to pass your RealTraffic license manually using the -l parameter")
        exit(1)


    #######################################################################################################
    #######################################################################################################
    # application specific settings
    software = "API_active_runway_example"
    API_version = args.api
    Server = f"https://{args.server}.flyrealtraffic.com/"

    #######################################################################################################
    #######################################################################################################
    # API constants
    auth_url = "%s/%s/auth" % (Server, API_version)
    deauth_url = "%s/%s/deauth" % (Server, API_version)
    active_runway_url = "%s/%s/active_runway" % (Server, API_version)

    header = { "Accept-encoding": "gzip" }
    license_types = { 0: "Standard", 1: "Standard", 2: "Professional" }

    ###############################################################
    # authenticate
    payload = { "license": "%s" % args.license, "software": "%s" % software }
    data = requests.post(auth_url, payload, headers=header).text
    print(data)
    json_data = json.loads(data)
    if json_data["status"] != 200:
      print(json_data["message"])
      exit(1)

    ###############################################################
    # retrieve our GUID to use for data access as well as the license details
    GUID = json_data["GUID"]
    license_type = json_data["type"]
    expiry = datetime.fromtimestamp(json_data["expiry"])

    # request rate limit (convert from ms to s)
    traffic_request_rate_limit = json_data["rrl"] / 1000.
    weather_request_rate_limit = json_data["wrrl"] / 1000.

    print("Successfully authenticated. %s license valid until %s UTC" % (license_types[license_type], expiry.strftime("%Y-%m-%d %H:%M:%S")))
    print("Sleeping %ds to avoid request rate violation..." % traffic_request_rate_limit)

    # set up rate limitation
    time.sleep(traffic_request_rate_limit)

    try:
        active_runway_payload = { "GUID": "%s" % GUID,
                   "ICAO": args.airport,
                   "toffset": int(args.toff) }

        try:
          response = requests.post(active_runway_url, active_runway_payload, headers=header)
          if not response.text:
              print(f"Server returned HTTP {response.status_code} with empty response")
              print("error getting active runway data")
          else:
              json_data = response.json()
              if json_data["status"] != 200:
                  print(json_data)
              else:
                  d = json_data["data"]

                  # METAR
                  print(f"\n{COLORS.get_color(COLORS.FG_GREEN)}METAR {d['icao']}:{COLORS.get_color(COLORS.RESET)}")
                  print(f"{COLORS.get_color(COLORS.FG_CYAN)}{d['metar']}{COLORS.get_color(COLORS.RESET)}\n")

                  # Wind
                  if d['wind_dir'] >= 0 and d['wind_speed'] >= 0:
                      print(f"Surface wind: {d['wind_dir']:03d}° at {d['wind_speed']} knots\n")
                  else:
                      print("Unable to parse wind from METAR\n")

                  # Legend
                  R = COLORS.get_color(COLORS.RESET)
                  print(f"Runway Analysis: "
                        f"{COLORS.get_color(COLORS.FG_GREEN)}ARR{R} "
                        f"{COLORS.get_color(COLORS.FG_BLUE)}DEP{R} "
                        f"{COLORS.get_color(COLORS.FG_MAGENTA)}ARR+DEP{R} "
                        f"{COLORS.get_color(COLORS.FG_RED)}TAILWIND{R}")
                  print("RWY    HDG(T) HDG(M)  Headwind XWnd(+L)    ARR (30m)  DEP (30m)  ARR (24h)  DEP (24h)")
                  print("-" * 85)

                  for rwy_id, rwy in d['runways'].items():
                      headwind = rwy['headwind']
                      crosswind = rwy['crosswind']
                      arr_count = rwy['arrivals_30m']
                      dep_count = rwy['departures_30m']
                      arr_24h = rwy.get('arrivals_24h', 0)
                      dep_24h = rwy.get('departures_24h', 0)

                      # Color: red=tailwind (no traffic), green=arrivals, blue=departures, magenta=both
                      if arr_count > 0 and dep_count > 0:
                          color = COLORS.get_color(COLORS.FG_MAGENTA)
                      elif arr_count > 0:
                          color = COLORS.get_color(COLORS.FG_GREEN)
                      elif dep_count > 0:
                          color = COLORS.get_color(COLORS.FG_BLUE)
                      elif headwind < 0:
                          color = COLORS.get_color(COLORS.FG_RED)
                      else:
                          color = COLORS.get_color(COLORS.RESET)

                      print(f"{color}{rwy_id:<7} {rwy['true_brg']:03d}°   {rwy['mag_brg']:03d}°  "
                            f"{headwind:+6.1f}    {crosswind:+6.1f}    {arr_count:3d}"
                            f"        {dep_count:3d}        {arr_24h:3d}        {dep_24h:3d}{COLORS.get_color(COLORS.RESET)}")

                  print(f"\nData time: {d['timestamp']}")
        except Exception as e:
          print(e)
          print("error getting active runway data")
    finally:
        # Always deauth before exiting
        payload = { "GUID": "%s" % GUID }
        data = requests.post(deauth_url, payload, headers=header).text
        print(data)
