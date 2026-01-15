#!/usr/bin/env python3

# RTAPI_example.py v2.0 22/7/2024 balt@inside.net
# Illustrates the full API functionality available for RealTraffic.
# Also broadcasts the retrieved that on the local network via UDP

import requests
import json
import time
import sys
import os
import signal
import psutil
import platform
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.img_tiles as cimgt
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
import textalloc as ta
from datetime import datetime, timezone
from argparse import ArgumentParser
from socket import SO_REUSEADDR, SOCK_STREAM, socket, SOL_SOCKET, AF_INET, SOCK_DGRAM, IPPROTO_UDP, SO_BROADCAST
from math import acos, cos, sin, radians, sqrt, atan2, degrees

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
# Fetch the database directory
def get_dbdir():
    # Determine the operating system
    is_windows = platform.system().lower() == "windows"

    # Set the appropriate file path based on the operating system
    if is_windows:
        dir_path = os.path.expanduser("~/AppData/Roaming/InsideSystems")
    else:
        dir_path = os.path.expanduser("~/Documents/.InsideSystems")

    # Check if the file exists
    if os.path.exists(dir_path):
        return dir_path

    return None

#######################################################################################################
# determine the open streetmap zoom level appropriate for the plot
def zoomlevel_from_deg(deg):
    "Calculate OSM zoom level from a span in degrees.  Adjust +/-1 as desired"
    from numpy import log2, clip, floor
    zoomlevel = int(clip(floor(log2(360) - log2(deg)),0,20 ))
    return zoomlevel

#######################################################################################################
# Terminal color class
class ANSIColors:
    RESET = '\033[0m'

    # Foreground colors
    FG_BLACK = '\033[30m'
    FG_RED = '\033[31m'
    FG_GREEN = '\033[32m'
    FG_YELLOW = '\033[33m'
    FG_BLUE = '\033[34m'
    FG_MAGENTA = '\033[35m'
    FG_CYAN = '\033[36m'
    FG_WHITE = '\033[37m'
    FG_DEFAULT = '\033[39m'

    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
    BG_DEFAULT = '\033[49m'

    # Text styles
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    BLINK = '\033[5m'
    REVERSE = '\033[7m'
    HIDDEN = '\033[8m'

#######################################################################################################
# Handles pressing ctrl-c gracefully, and allows us to deauth before the session is closed
def sighandler(signum, frame):
  if signum == signal.SIGINT:
    move_cursor_to_position(terminal_cols, terminal_rows)
    print("\rCtrl-C captured. Exiting.")

    # death
    payload = { "GUID": "%s" % GUID }
    data = requests.post(deauth_url, payload, headers=header).text
    print(data)
    exit()

#######################################################################################################
# the worker function to broadcast the traffic and weather data via UDP
def UDPbcast(ip, bcast, port, data):
  try:
      sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)  # UDP
      sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
      sock.bind((ip,0))
      sock.sendto(data, (bcast, port))
      sock.close()
      return True
  except Exception as ex:
      print("Error sending UDP brodcast:")
      print(ex)
      return False

#######################################################################################################
# gets the size of the terminal
def get_terminal_size():
    columns, rows = os.get_terminal_size()
    return columns, rows

#######################################################################################################
# hide the cursor
def hide_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

#######################################################################################################
# show the cursor
def show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()

#######################################################################################################
# move cursor to position
def move_cursor_to_position(row, col):
    # Move cursor to the specified row and column
    sys.stdout.write(f"\033[{row};{col}H")
    sys.stdout.flush()

#######################################################################################################
# fetch the nearest airport to the given location
def nearest_airport():
  # find the nearest airport to the given coordinates
  con.create_function('radians', 1, radians)
  con.create_function('acos', 1, acos)
  con.create_function('cos', 1, cos)
  con.create_function('sin', 1, sin)
  sqlite3.enable_callback_tracebacks(True)
  try:
      apt_cur.execute("SELECT airport_identifier, airport_ref_latitude, airport_ref_longitude, elevation, (3959 * acos(cos(radians(%f)) * cos(radians(airport_ref_latitude)) * cos(radians(airport_ref_longitude) - radians(%f)) + sin(radians(%f)) * sin(radians(airport_ref_latitude)))) AS distance FROM tbl_airports ORDER BY distance LIMIT 1;" % (args.lat, args.lon, args.lat))
  except Exception as e:
      con.execute('select error()')

  apt = apt_cur.fetchall()

  return apt[0][0]

#######################################################################################################
# Haversine function to calculate distance and bearing
def calculate_distance_and_bearing(own_lat, own_lon, own_track, target_lat, target_lon, target_track):
    def haversine_distance(lat1, lon1, lat2, lon2):
        R = 3440  # Earth's radius in kilometers

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c

    def calculate_bearing(lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlon = lon2 - lon1

        y = sin(dlon) * cos(lat2)
        x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)

        initial_bearing = atan2(y, x)
        initial_bearing = degrees(initial_bearing)
        compass_bearing = (initial_bearing + 360) % 360

        return compass_bearing

    distance = haversine_distance(own_lat, own_lon, target_lat, target_lon)
    absolute_bearing = calculate_bearing(own_lat, own_lon, target_lat, target_lon)

    relative_bearing = (absolute_bearing - own_track + 360) % 360

    return {
        'distance': distance,
        'relative_bearing': relative_bearing,
        'absolute_bearing': absolute_bearing
    }

#######################################################################################################
# LivePlot class definition
class LivePlot:
    def __init__(self):
        self.fig, self.ax = plt.subplots(figsize=(12, 12), subplot_kw={'projection': ccrs.PlateCarree()})
        self.texts = None
        self.lines = None
        self.aircraft_patches = []
        self._setup_map_features()

    def _setup_map_features(self):
        self.ax.add_feature(cfeature.LAND)
        self.ax.add_feature(cfeature.OCEAN)
        self.ax.add_feature(cfeature.COASTLINE)
        self.ax.add_feature(cfeature.BORDERS, linestyle=':')
        self.ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)

    def update_plot(self, aircraft_data, map_extent):
        lats, lons, css, types, alts, trks, spds, froms, tos, icss = self._extract_data(aircraft_data)

        if len(lats) == 0 or len(lons) == 0:
            return

        self._update_map_extent(map_extent)
        self._clear_previous_plot()
        self._plot_aircraft(lons, lats, trks, map_extent)
        self._plot_labels(lons, lats, css, types, alts, spds, froms, tos, icss)

        self.ax.set_title('Live Aircraft Positions')
        plt.draw()

    def _extract_data(self, aircraft_data):
        lats, lons, css, types, alts, trks, spds, froms, tos, icss = [], [], [], [], [], [], [], [], [], []
        for key, data in aircraft_data.items():
            lats.append(data[1])
            lons.append(data[2])
            alts.append(data[4])
            types.append(data[8])
            css.append(data[13])
            trks.append(data[3])
            spds.append(data[5])
            froms.append('' if data[11] == 'null' else data[11])
            tos.append('' if data[12] == 'null' else data[12])
            icss.append('' if data[16] == 'null' else data[16])
        return lats, lons, css, types, alts, trks, spds, froms, tos, icss

    def _update_map_extent(self, map_extent):
        self.ax.set_extent(map_extent)
        # Update gridlines
        self.ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)

    def _clear_previous_plot(self):
        for patch in self.aircraft_patches:
            patch.remove()
        self.aircraft_patches = []
        if self.texts:
            [t.remove() for t in self.texts]
        if self.lines:
            [l.remove() for l in self.lines]

    def _plot_aircraft(self, lons, lats, trks, map_extent):
        length = abs(map_extent[0] - map_extent[1]) / 100
        for lon, lat, trk in zip(lons, lats, trks):
            aircraft = FancyArrowPatch(
                (lon - length * sin(radians(trk)), lat - length * cos(radians(trk))),
                (lon + length * sin(radians(trk)), lat + length * cos(radians(trk))),
                mutation_scale=10,
                color='blue',
                transform=ccrs.PlateCarree()
            )
            self.ax.add_patch(aircraft)
            self.aircraft_patches.append(aircraft)

    def _plot_labels(self, lons, lats, css, types, alts, spds, froms, tos, icss):
        labels = [f"{cs} ({ics}) {type} {frm} {to}\n{int(spd)} {alt}" for cs, type, alt, spd, frm, to, ics in zip(css, types, alts, spds, froms, tos, icss)]
        _, _, self.texts, self.lines = ta.allocate(
            self.ax,
            lons,
            lats,
            labels,
            x_scatter=lons,
            y_scatter=lats,
            textsize=6,
            draw_lines=True,
            linewidth=0.5,
            draw_all=False,
            transform=ccrs.PlateCarree(),
            avoid_label_lines_overlap=True,
        )

def plot_live_aircraft_positions(aircraft_data, live_plot, map_extent):
    live_plot.update_plot(aircraft_data, map_extent)


###############################################################
# authenticate
def authenticate(args, software):
  global auth_count
  payload = { "license": "%s" % args.license, "software": "%s" % software }
  data = requests.post(auth_url, payload, headers=header).text
  print(f"Server response: {data}")
  json_data = json.loads(data)
  if json_data["status"] != 200:
    print(json_data["message"])
    exit(1)

  # retrieve our GUID to use for data access as well as the license details
  GUID = json_data["GUID"]
  license_type = json_data["type"]
  expiry = datetime.fromtimestamp(json_data["expiry"])

  # request rate limit (convert from ms to s)
  traffic_request_rate_limit = json_data["rrl"] / 1000.
  weather_request_rate_limit = json_data["wrrl"] / 1000.

  print("Successfully authenticated. %s license valid until %s UTC" % (license_types[license_type], expiry.strftime("%Y-%m-%d %H:%M:%S")))
  print("Sleeping %ds to avoid request rate violation..." % traffic_request_rate_limit)
  auth_count += 1
  time.sleep(traffic_request_rate_limit)
  return GUID, traffic_request_rate_limit, weather_request_rate_limit


#######################################################################################################
#######################################################################################################
if __name__ == '__main__':

    parser = ArgumentParser(description='RealTraffic API Tester')

    # Add optional argument, with given default values if user gives no arg
    parser.add_argument('-p', '--port', default=10747, type=int, help='Server port')
    parser.add_argument('-s', '--host', default="127.0.0.1", type=str, help='Server host')
    parser.add_argument('-l', '--license', help='Your RealTraffic license, e.g. AABBCC-1234-AABBCC-123456')
    parser.add_argument('-a', '--airport', type=str, help='ICAO code of airport to go to, instead of lat/lon')
    parser.add_argument('--lat', type=float, help="center latitude")
    parser.add_argument('--lon', type=float, help="center latitude")
    parser.add_argument('-r', '--radius', type=float, default=100, help="length of box side in km, default 100km")
    parser.add_argument('-z', '--alt', type=float, default=0, help="altitude in feet")
    parser.add_argument('-fcs', '--followatccallsign', type=str, help="ATC callsign to follow")
    parser.add_argument('-ffn', '--followflightnumber', type=str, help="flight number (IATA callsign) to follow")
    parser.add_argument('-fx', '--followhex', type=str, help="hexid to follow")
    parser.add_argument('-d', '--dbdir', type=str, help="database directory where navdb.s3db is located")
    parser.add_argument('--toff', default=0, type=float, help="time offset in minutes")
    parser.add_argument('--nummetars', default=3, type=int, help="The number of nearest airport METARs to display")
    parser.add_argument('-api', '--api', default="v5", type=str, help="API endpoint to call, default v5")
    parser.add_argument('-tw', '--tw', type=str, help="trace weather filename. Writes the aircraft wind/temp alongside the GFS wind/temp for comparison")
    parser.add_argument('--bufcount', type=int, help="The number of buffers to retrieve. This retrieves the buffer and quits. Requires buftime to be set as well.")
    parser.add_argument('--buftime', type=int, help="The number of seconds between the buffers. Must be an even number.")
    parser.add_argument('--livemap', action="store_true", help="opens a window and draws a live map")
    parser.add_argument('--server', default="rtwa", type=str, help="server name to connect to")

    args = parser.parse_args()

    if (args.followatccallsign == None and args.followhex == None and args.followflightnumber == None) and (args.airport == None and (args.lat == None or args.lon == None)):
        print("You either need to follow a flight, or enter an airport location, or give a lat/lon to position yourself at!")
        exit(1)

    if args.license == None:
        args.license = get_license()

    if args.license == None:
        print("Unable to load the license from the RealTraffic.lic file.")
        print("You need to pass your RealTraffic license manually using the -l parameter")
        exit(1)

    if args.dbdir == None:
        args.dbdir = get_dbdir()

    if args.dbdir == None:
        print("Unable to obtain the directory where navdb.s3db lives.")
        print("This database is included in the RealTraffic software installation.")
        print("You will not be able to use airport lookups using the -a parameter")


    first_tw_line = True

    #######################################################################################################
    #######################################################################################################
    # application specific settings
    software = "API_tester_example"
    API_version = args.api
    Server = f"https://{args.server}.flyrealtraffic.com/"

    #######################################################################################################
    #######################################################################################################
    # API constants
    auth_url = "%s/%s/auth" % (Server, API_version)
    deauth_url = "%s/%s/deauth" % (Server, API_version)
    traffic_url = "%s/%s/traffic" % (Server, API_version)
    weather_url = "%s/%s/weather" % (Server, API_version)
    nearestmetar_url = "%s/%s/nearestmetar" % (Server, API_version)
    nearesttaf_url = "%s/%s/nearestmetar" % (Server, API_version)
    search_url = "%s/%s/search" % (Server, API_version)
    airportinfo_url = "%s/%s/airportinfo" % (Server, API_version)

    header = { "Accept-encoding": "gzip" }
    license_types = { 0: "Standard", 1: "Standard", 2: "Professional" }

    last_WDIR = 0
    last_WSPD = 0
    last_TEMP = 0
    last_TPP = 0
    last_DZDT = 0
    last_clouddata = "0,-1,-1,0,-1,-1,0,-1,-1"

    next_weather_request = 0
    next_traffic_request = 0

    follow_param = None

    # set the terminal title to reflect the API version running
    print("\033]0;%s with API %s%s\007" % (software, Server, API_version))

    con = sqlite3.connect('%s/navdb.s3db' % args.dbdir)
    apt_cur = con.cursor()

    # find the airport coordinates
    if args.airport != None:
        apt_cur.execute("SELECT airport_identifier, airport_ref_latitude, airport_ref_longitude, elevation, airport_name FROM tbl_airports WHERE airport_identifier like '%s'" % args.airport)
        apt = apt_cur.fetchall()
        if len(apt) > 1:
            print("More than one airport matches. Found the following results:")
            for a in apt:
                print(a[0], a[-1])
            exit(1)
        elif len(apt) == 1:
            args.lat = apt[0][1]
            args.lon = apt[0][2]
            if args.alt == 0:
                args.alt = apt[0][3]
                print(f"Setting altitude to airport altitude: {args.alt}ft")
        else:
            print("No matching airports found")
            exit(1)

    # convert altitude to meters
    args.alt /= 3.28084

    # capture signals such as ctrl-c in the loop
    signal.signal(signal.SIGINT, sighandler)

    ###############################################################
    # enumerate all network interfaces and get their IPs
    # broadcasting to 255.255.255.255 is bad practice, need to find the correct bcast addr for
    # the local subnet on each interface only
    bcast_addrs = []
    ip_addrs = []
    ifs = psutil.net_if_addrs()
    for key in ifs.keys():
      for intf in ifs[key]:
        if intf.broadcast != None:
          bcast_addrs.append(intf.broadcast)
          ip_addrs.append(intf.address)

    print("Will broadcast to:", bcast_addrs)

    # variables to keep track of the error counts
    nearest_metar_error_count = 0
    weather_error_count = 0
    airportinfo_error_count = 0
    traffic_error_count = 0
    traffic_count_nonzero = 0
    traffic_count_zero = 0
    udp_error_count = 0

    auth_count = 0
    GUID, traffic_request_rate_limit, weather_request_rate_limit = authenticate(args, software)

    # Clear the screen
    sys.stdout.write("\033[2J")
    sys.stdout.flush()

    weatherdata = ""
    weatherstring = ""

    ###################################################################################
    # if following a callsign or hexid, find it first. But only if no location selected
    if (args.followflightnumber != None or args.followatccallsign != None or args.followhex != None):
        if args.followatccallsign != None:
            search_payload = { "GUID": "%s" % GUID,
                     "searchParam": "CallsignExact",
                     "search": args.followatccallsign,
                     "toffset": int(args.toff) }
            # store the follow parameter for use later in this script so we match the correct data field
            follow_param = {'id': args.followatccallsign, 'data_index': 13}
        elif args.followhex != None:
            search_payload = { "GUID": "%s" % GUID,
                   "searchParam": "HexID",
                   "search": args.followhex,
                   "toffset": int(args.toff) }
            # store the follow parameter for use later in this script so we match the correct data field
            follow_param = {'id': args.followhex, 'data_index': 0}
        elif args.followflightnumber != None:
            search_payload = { "GUID": "%s" % GUID,
                   "searchParam": "FlightNumberExact",
                   "search": args.followflightnumber,
                   "toffset": int(args.toff) }
            # store the follow parameter for use later in this script so we match the correct data field
            follow_param = {'id': args.followflightnumber, 'data_index': 16}

        # only try to find it here if no position was given:
        if args.lat == None and args.lon == None:
            try:
              response = requests.post(search_url, search_payload, headers=header)
              json_data = response.json()
            except Exception as e:
              print(e)
              print(response.text)
              # something borked. abort.
              print("search error")
              exit(1)

            if json_data["status"] != 200:
              print(json_data["message"])
              exit(1)

            search_data = json_data["data"]

            if len(search_data) == 0:
                print("Empty search result for callsign or hexid")
                exit(1)
            elif len(search_data) != 1:
                print("Found %d matching search results, can't decide which one to follow!" % len(search_data))
                exit(1)

            # set the lat and lon and alt to the aircraft position 1 2 4
            thisflight = list(search_data.values())[0]
            args.lat, args.lon, args.alt = (thisflight[1], thisflight[2], thisflight[4])
            print(f"Setting position to {args.lat} {args.lon} {args.alt} and will track...")

    # initialise the plot if requested
    live_plot = None
    if args.livemap:
        live_plot = LivePlot()
        plt.ion()  # Turn on interactive mode

    ###############################################################
    # keep fetching traffic forever (or until ctrl-c is pressed)
    while True:

        # calculate the box size to retrieve traffic in
        left = args.lon - 1/cos(radians(args.lat)) * args.radius / 111
        right = args.lon + 1/cos(radians(args.lat)) * args.radius / 111
        top = args.lat + args.radius / 111
        bottom = args.lat - args.radius / 111

        if left < -180: left += 360
        if left > 180: left -= 360
        if right < -180: right += 360
        if right > 180: right -= 360

        # fetch the terminal size, this can change during runtime so do it here
        # instead of once at startup
        terminal_cols, terminal_rows = get_terminal_size()

        #########################################
        # fetch the nearest airport with a METAR
        # note this is rate limited at the same rate as the weather requests
        if time.time() > next_weather_request:
            nearestmetar_payload = { "GUID": "%s" % GUID,
                       "maxcount": args.nummetars,
                       "lat": args.lat,
                       "lon": args.lon,
                       "toffset": int(args.toff) }

            try:
                response = requests.post(nearestmetar_url, nearestmetar_payload, headers=header)
                json_data = response.json()
            except Exception as e:
                with open("nearestmetar_error.txt", "a") as f:
                    f.write("-- Error\n" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                    f.write(str(e) + "\n")
                    f.write(response.text + "\n")
                # something borked. abort.
                print("error getting nearest metar airport code")
                nearest_metar_error_count += 1
                time.sleep(weather_request_rate_limit)
                continue

            if json_data["status"] != 200:
              print(json_data["message"])
              if json_data["status"] == 401:
                # reauthentication
                GUID, traffic_request_rate_limit, weather_request_rate_limit = authenticate(args, software)
              else:
                time.sleep(weather_request_rate_limit)
              continue

              # Example response:
              #  {
              #    "data": [
              #      {
              #        "BrgTo": 0,
              #        "Dist": 0,
              #        "ICAO": "YSSY",
              #        "METAR": "YSSY 212130Z 29009KT CAVOK 09/04 Q1025"
              #      },
              #      {
              #        "BrgTo": 316.3,
              #        "Dist": 28.7,
              #        "ICAO": "YSRI",
              #        "METAR": "YSRI 212130Z AUTO 00000KT 9999 // NCD 02/02 Q1025 RF00.0/000.0"
              #      },
              #      {
              #        "BrgTo": 25.7,
              #        "Dist": 76.6,
              #        "ICAO": "YWLM",
              #        "METAR": "YWLM 212130Z 29010KT CAVOK 08/04 Q1026"
              #      }
              #    ],
              #    "message": "OK",
              #    "status": 200,
              #    "wrrl": 2000
              #  }

            nearest_metar_data = json_data["data"]

            if len(nearest_metar_data) == 0:
                with open("nearestmetar_error.txt", "a") as f:
                    f.write("-- Error nearest METAR length == 0\n" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                    f.write(response.text + "\n")
                # something borked. abort.
                nearest_metar_error_count += 1
                time.sleep(weather_request_rate_limit)
                continue

        #########################################
        # fetch info for this airport
        if time.time() > next_traffic_request:
            airportinfo_payload = { "GUID": "%s" % GUID,
                       "ICAO": nearest_metar_data[0]['ICAO'] }

            try:
                response = requests.post(airportinfo_url, airportinfo_payload, headers=header)
                json_data = response.json()
            except Exception as e:
                with open("airportinfo_error.txt", "a") as f:
                    f.write("-- Error\n" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                    f.write(str(e) + "\n")
                    f.write(response.text + "\n")
                # something borked. abort.
                print("error getting airportinfo")
                print(airportinfo_payload)
                nearest_metar_error_count += 1
                time.sleep(weather_request_rate_limit)
                #continue

            if json_data["status"] != 200:
              print(json_data["message"])
              if json_data["status"] == 401:
                # reauthentication
                GUID, traffic_request_rate_limit, weather_request_rate_limit = authenticate(args, software)
              else:
                time.sleep(weather_request_rate_limit)
              continue

              # Example response
              #  {
              #    "data": {
              #      "MSA": {
              #        "MSA_center": "LSZB",
              #        "MSA_center_lat": 46.91222222,
              #        "MSA_center_lon": 7.49944444,
              #        "MSA_radius_limit": 25,
              #        "MSA_sector1_alt": 15800,
              #        "MSA_sector1_brg": 250,
              #        "MSA_sector2_alt": 10700,
              #        "MSA_sector2_brg": 5,
              #        "MSA_sector3_alt": 7200,
              #        "MSA_sector3_brg": 65
              #      },
              #      "airport": {
              #        "elevation": 1675,
              #        "name": "BELP",
              #        "ref_lat": 46.91222222,
              #        "ref_lon": 7.49944444,
              #        "transition_altitude": 6000,
              #        "transition_level": -1
              #      },
              #      "runways": {
              #        "RW14": {
              #          "declination": 2.0,
              #          "displaced_threshold_distance": 656,
              #          "gradient": 0.123,
              #          "gs_angle": 4.0,
              #          "ils_cat": 1,
              #          "landing_threshold_elevation": 1668,
              #          "lat": 46.91793889,
              #          "length": 5676,
              #          "llz_brg": 138.0,
              #          "llz_freq": 110.1,
              #          "llz_ident": "IBE",
              #          "lon": 7.49249444,
              #          "mag_brg": 138.0,
              #          "surface": "Asphalt",
              #          "threshold_crossing_height": 43,
              #          "true_brg": 140.197,
              #          "width": 98
              #        },
              #        "RW32": {
              #          "declination": -1,
              #          "displaced_threshold_distance": 0,
              #          "gradient": -0.123,
              #          "gs_angle": -1,
              #          "ils_cat": -1,
              #          "landing_threshold_elevation": 1675,
              #          "lat": 46.90738889,
              #          "length": 5676,
              #          "llz_brg": -1,
              #          "llz_freq": -1,
              #          "llz_ident": "",
              #          "lon": 7.50536111,
              #          "mag_brg": 318.0,
              #          "surface": "Asphalt",
              #          "threshold_crossing_height": 50,
              #          "true_brg": 320.206,
              #          "width": 98
              #        }
              #      }
              #    },
              #    "message": "OK",
              #    "rrl": 2000,
              #    "status": 200
              #  }

            airportinfo_data = json_data["data"]

            if len(airportinfo_data) == 0:
                with open("airportinfo_error.txt", "a") as f:
                    f.write("-- Error airportinfo length == 0\n" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                    f.write(str(e) + "\n")
                    f.write(response.text + "\n")
                airportinfo_error_count += 1
                time.sleep(traffic_request_rate_limit)
                continue


        # set up the payload for the queries
        traffic_payload = { "GUID": "%s" % GUID,
                   "querytype": "locationtraffic",
                   "top": top,
                   "bottom": bottom,
                   "left": left,
                   "right": right,
                   "toffset": int(args.toff) }

        # If we're testing the buffering function for the first call at a new location
        # need to add the traffic query payload parameters
        if args.bufcount != None and args.buftime != None:
            traffic_payload['buffertime'] = args.buftime
            traffic_payload['buffercount'] = args.bufcount

        # weather payload has two additional METARs added for illustration: LSZB and KABQ along with the nearest airport
        weather_payload = { "GUID": "%s" % GUID,
                   "querytype": "locwx",
                   "lat": args.lat,
                   "lon": args.lon,
                   "alt": args.alt,
                   "airports": "%s|LSZB|KABQ" % nearest_metar_data[0]['ICAO'],
                   "toffset": int(args.toff) }

        ##############################################################################################
        # Fetch the weather if it is time
        if time.time() > next_weather_request:
            try:
                response = requests.post(weather_url, weather_payload, headers=header)
                json_data = response.json()
            except Exception as e:
                with open("weather_error.txt", "a") as f:
                    f.write("-- Error\n" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                    f.write(str(e) + "\n")
                    f.write(response.text + "\n")
                # something borked. abort.
                print("error getting weather")
                weather_error_count += 1
                time.sleep(weather_request_rate_limit)
                continue

            if json_data["status"] != 200:
                print(json_data["message"])
                if json_data["status"] == 401:
                    # reauthentication
                    GUID, traffic_request_rate_limit, weather_request_rate_limit = authenticate(args, software)
                else:
                    time.sleep(weather_request_rate_limit)
                continue

                # Example response
                #  {
                #      "wrrl": 2000,
                #      "source": "MemoryDB",
                #      "status": 200,
                #      "message": "OK",
                #      "data": {
                #          "ICAO": "YSSY",
                #          "QNH": 1025,
                #          "METAR": "YSSY 212200Z 29008KT CAVOK 10/05 Q1025",
                #          "locWX": {
                #              "Info": "2024-07-21_2220Z",
                #              "SLP": 1025.2,
                #              "WSPD": 22.31,
                #              "WDIR": 283.82,
                #              "T": 9.15,
                #              "ST": 10.04,
                #              "SVis": 24135,
                #              "SWSPD": 22.28,
                #              "SWDIR": 283.94,
                #              "DZDT": -0.019,
                #              "LLC": {
                #                  "cover": 0.0,
                #                  "base": -1,
                #                  "tops": -1,
                #                  "type": -1,
                #                  "confidence": -1
                #              },
                #              "MLC": {
                #                  "cover": 5.0,
                #                  "base": 6106,
                #                  "tops": 6467,
                #                  "type": 1.0,
                #                  "confidence": 0.0
                #              },
                #              "HLC": {
                #                  "cover": 25.34,
                #                  "base": 6483,
                #                  "tops": 9402,
                #                  "type": 1.0,
                #                  "confidence": 0.09
                #              },
                #              "TPP": 9710.79,
                #              "PRR": 0.0,
                #              "CAPE": 0.0,
                #              "DPs": [3.0, 2.24, 1.03, 0.07, -2.46, -8.28, -10.98, -15.94, -18.67, -21.7, -25.64, -26.56, -30.29, -35.63, -43.32, -52.23, -66.71, -75.56, -82.13, -87.27],
                #              "TEMPs": [9.15, 9.86, 7.92, 6.65, 3.35, 1.22, -1.39, -4.27, -7.13, -11.27, -16.62, -21.57, -27.8, -33.92, -41.5, -50.82, -53.3, -49.57, -52.05, -55.02],
                #              "WDIRs": [283.94, 258.87, 226.76, 215.3, 208.77, 232.29, 267.41, 256.35, 247.33, 245.8, 244.63, 246.15, 249.2, 257.98, 257.37, 255.55, 260.51, 264.91, 264.43, 258.41],
                #              "WSPDs": [22.28, 29.31, 39.26, 35.08, 23.81, 8.87, 12.86, 23.84, 36.35, 49.14, 54.16, 58.72, 67.9, 68.22, 79.06, 91.51, 80.26, 94.16, 86.11, 54.38],
                #              "DZDTs": [-0.02, -0.02, 0.01, 0.02, 0.01, -0.0, 0.01, 0.01, 0.01, 0.0, -0.01, -0.02, -0.02, -0.01, -0.01, 0.01, 0.0, -0.01, -0.02, 0.02],
                #              "Profiles": "RTFX1              ^S3356.8            ^E15110.6           ^FL163  245/030 -18 ^FL143  246/027 -13 ^FL123  247/021  -8 ^FL103  254/014  -5 ^ 8364  267/007  -2 ^^"
                #          },
                #          "AM": ["LSZB 212150Z AUTO 16005KT 9999 SCT040 SCT048 BKN055 21/17 Q1016", "KABQ 212152Z 27007KT 10SM SCT070 SCT180 29/13 A3017 RMK AO2 SLP131 CB DSNT N T02890133 $"]
                #      }
                #  }

                weather_request_rate_limit = json_data["wrrl"] / 1000.
                next_weather_request = time.time() + weather_request_rate_limit

            # Move cursor to line 0, column 0
            sys.stdout.write("\033[H")
            sys.stdout.flush()

            weather_data = json_data["data"]

            # build the text information to display
            metarstring = ""
            for i in range(args.nummetars):
                metarstring += f"{ANSIColors.FG_GREEN}METAR {nearest_metar_data[i]['ICAO']} ({nearest_metar_data[i]['Dist']} NM @ {nearest_metar_data[i]['BrgTo']}°):\n{ANSIColors.RESET}{ANSIColors.FG_CYAN}{nearest_metar_data[i]['METAR']}{ANSIColors.RESET}\n"
            metarstring = metarstring[:-1]

            if weather_data["locWX"]['SLP'] != -1:
                weatherdata = "GFS Data: %s\n" % weather_data["locWX"]['Info']
                weatherdata += f"{ANSIColors.FG_GREEN}SFC:   Wind %03d/%d T %0.1fC QNH %0.1fhPa Vis %0.1dkm Tropo FL%03d{ANSIColors.RESET}\n" % (round(weather_data["locWX"]['SWDIR']), round(weather_data["locWX"]['SWSPD']/1.852), weather_data["locWX"]['ST'], weather_data["locWX"]['SLP'], weather_data["locWX"]['SVis'] / 1000, weather_data["locWX"]['TPP'] / 100 * 3.28084)
                weatherdata += f"{ANSIColors.FG_GREEN}FL%03d: Wind %03d/%d T %0.1fC{ANSIColors.RESET}" % (args.alt*3.28084/100, round(weather_data["locWX"]['WDIR']), round(weather_data["locWX"]['WSPD']/1.852), weather_data["locWX"]['T'])
                last_WSPD = weather_data["locWX"]['WSPD']/1.852
                last_WDIR = weather_data["locWX"]['WDIR']
                last_TEMP = weather_data["locWX"]['T']
                last_TPP = weather_data["locWX"]['TPP'] * 3.28084
                last_DZDT = weather_data["locWX"]['DZDT']
                last_clouddata = f"{weather_data['locWX']['LLC']['cover']},{weather_data['locWX']['LLC']['base']},{weather_data['locWX']['LLC']['tops']},{weather_data['locWX']['LLC']['type']}"
                last_clouddata += f",{weather_data['locWX']['MLC']['cover']},{weather_data['locWX']['MLC']['base']},{weather_data['locWX']['MLC']['tops']},{weather_data['locWX']['MLC']['type']}"
                last_clouddata += f",{weather_data['locWX']['HLC']['cover']},{weather_data['locWX']['HLC']['base']},{weather_data['locWX']['HLC']['tops']},{weather_data['locWX']['HLC']['type']}"

                #if 'DPs' in weather_data["locWX"]:
                #    weatherdata += "\nDPs: " + ",".join(str(num) for num in weather_data["locWX"]['DPs'])
                if 'LLC' in weather_data["locWX"]:
                    weatherdata += "\n\nLLC: " + json.dumps(weather_data["locWX"]['LLC'])
                    weatherdata += "\nMLC: " + json.dumps(weather_data["locWX"]['MLC'])
                    weatherdata += "\nHLC: " + json.dumps(weather_data["locWX"]['HLC']) + "\n"
            else:
                weatherstring = "\nGFS Data: " + weather_data["locWX"]['Info'] + "\n"

        ##############################################################################################
        # fetch traffic
        try:
            response = requests.post(traffic_url, traffic_payload, headers=header)
            json_data = response.json()

        except Exception as e:
            # log the error encountered on retrieving the traffic in JSON format
            with open("traffic_error.txt", "a") as f:
                f.write("-- Error\n" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                f.write(str(e) + "\n")
                f.write(response.text + "\n")
            traffic_error_count += 1
            time.sleep(traffic_request_rate_limit)
            continue

        if json_data["status"] != 200:
            print(json_data["message"])
            if json_data["status"] == 401:
                # reauthentication
                GUID, traffic_request_rate_limit, weather_request_rate_limit = authenticate(args, software)
            else:
                time.sleep(traffic_request_rate_limit)
            continue

        if args.bufcount != None and args.buftime != None:
            print(json_data)
            exit()

        # Example response
        #  {
        #      "data": {
        #          "c01c52": ["c01c52", 22.307192, 113.923581, 0, 0, 8.8, "3256", "X", "B789", "C-FKSV", 1721600731.62, "YVR", "HKG", "ACA21", 1, 0, "AC21", "X_adsb_icao", null, null, null, null, null, null, 345.94, 342.55, null, "none", "A5", null, null, null, null, "null", 8, 186, null, 9, 1, 0.8, -16.7, 0, 0, null, null, null, null, 1],
        #          "780a65": ["780a65", 22.312534, 113.931402, 0, 0, 4.2, "2000", "X", "B77W", "B-KQQ", 1721600732.12, "YVR", "HKG", "CPA865", 1, 0, "CX865", "X_adsb_icao", null, null, null, null, null, null, null, null, null, "none", "A5", null, null, null, null, "null", 8, 186, null, 9, 1, 1.4, -8.8, 0, 0, null, null, null, null, 1],
        #          "ff2ae3": ["ff2ae3", 22.307577, 113.917336, 112, 0, 0, "", "T", "GRND", "null", 1721600719.0, "null", "null", "SW5_", 1, 0, "null", "T_adsb", null, null, null, null, null, null, null, null, null, "null", "null", null, null, null, null, "null", null, null, null, null, null, null, null, null, null, null, null, null, null, 1],
        #          "7801cc": ["7801cc", 22.312767, 113.912315, 70, 0, 8, "", "T", "B773", "B-HNP", 1721600725.0, "BKK", "HKG", "CXBHNP", 1, 0, "CX704", "T_adsb", null, null, null, null, null, null, null, null, null, "null", "null", null, null, null, null, "null", null, null, null, null, null, null, null, null, null, null, null, null, null, 1],
        #          "780a0e": ["780a0e", 22.314651, 113.931335, 160, 0, 0, "", "T", "A333", "B-LAQ", 1721600706.0, "CGK", "HKG", "CPA798", 1, 0, "CX798", "T_adsb", null, null, null, null, null, null, null, null, null, "null", "null", null, null, null, null, "null", null, null, null, null, null, null, null, null, null, null, null, null, null, 1]
        #      },
        #      "full_count": 15430,
        #      "source": "MemoryDB",
        #      "rrl": 2000,
        #      "status": 200,
        #      "dataepoch": 1721600736
        #  }

        # update the traffic RRL:
        traffic_request_rate_limit = json_data["rrl"] / 1000.

        next_traffic_request = time.time() + traffic_request_rate_limit

        # plot the traffic if requested:
        if args.livemap:
            plot_live_aircraft_positions(json_data["data"], live_plot, [left, right, bottom, top])
            plt.pause(0.01)  # Shorter pause for more frequent updates


        # Move cursor to line 0, column 0
        sys.stdout.write("\033[H")
        sys.stdout.flush()

        # Clear the screen
        sys.stdout.write("\033[2J")
        sys.stdout.flush()

        # first print the weather information
        print(metarstring)
        print(weatherstring+weatherdata)

        print(f"Present position: {args.lat:.5f} {args.lon:.5f} {args.alt * 3.28084}")

        # Aide memoire for accessing the data fields in the traffic response
        # RealTraffic record format for API access:
        #  0    1     2       3      4     5      6      7       8          9         10       11       12         13    14       15       16        17          18   19   20    21       22       23       24
        # hex, lat, lon, track, alt_baro, gs, squawk, source, ac_type, ac_tailno, seen_pos, from_iata, to_iata, cs_icao, gnd, baro_rate, cs_iata, msg_type, alt_geom, ias, tas, mach, track_rate, roll, mag_heading,
        #        25        26          27      28           29                30               31         32       33        34   35      36     37    38      39    40    41    42   43  44  45    46     47     48
        # true_heading, geom_rate, emergency, category, nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading, nav_modes, nic, rc, nic_baro, nac_p, nac_v, seen, rssi, alert, spi, wd, ws, oat, tat, icaohex, record_augmented

        flights = []
        # manage the error state if the followed flight wasn't found,
        if follow_param == None:
            followOK = True
        else:
            followOK = False

        for key in json_data['data']:
          for ip, bcast in zip(ip_addrs, bcast_addrs):
            if not UDPbcast(ip, bcast, 49005, str.encode(json.dumps(json_data['data'][key]))):
                # bcast returned false, try to re-enumerate the interfaces
                udp_error_count += 1
                bcast_addrs = []
                ip_addrs = []
                ifs = psutil.net_if_addrs()
                for k in ifs.keys():
                  for intf in ifs[k]:
                    if intf.broadcast != None:
                      bcast_addrs.append(intf.broadcast)
                      ip_addrs.append(intf.address)

          # and extract a few data points for show and tell
          winddir = f"{json_data['data'][key][43]:3d}" if json_data['data'][key][43] != None else 0
          windspd = f"{json_data['data'][key][44]:0d}" if json_data['data'][key][44] != None else 0
          oat = f"{json_data['data'][key][45]:.1f}" if json_data['data'][key][45] != None else 0
          windinfo = "%s/%s %s" % (winddir, windspd, oat)

          bcolor = ANSIColors.FG_DEFAULT
          if follow_param != None:
              if follow_param['id'] == json_data['data'][key][follow_param['data_index']]:
                 bcolor = ANSIColors.FG_CYAN
                 if json_data['data'][key][5] > 0:
                     # calculate how long this flight remains within coverage if it is lost, i.e. max recovery time
                     maxrecovery = f"Max LOS til flight lost: {args.radius / 1.852 / json_data['data'][key][5] * 60:.1f} minutes"
                 else:
                     maxrecovery = ""
                 if args.tw != None:
                     with open(f"{args.tw}", "a") as f:
                         if first_tw_line:
                             f.write("Seen_pos, lat, lon, baro_alt, gs, track, ADS_B_winddir, ADS_B_windspd, ADS_B_OAT, GFS_winddir, GFS_windspd, GFS_OAT, turbulence, tropo_height, msg_type, llc_cover, llc_base, llc_tops, llc_type, mlc_cover, mlc_base, mlc_tops, mlc_type, hlc_cover, hlc_base, hlc_tops, hlc_type\n")
                             first_tw_line = False

                         f.write("%s, %0.5f, %0.5f, %s, %s, %s, %0.1f, %0.1f, %0.1f, %s, %s, %s, %0.4f, %d, %s, %s\n" % (json_data['data'][key][10], json_data['data'][key][1], \
                                json_data['data'][key][2], json_data['data'][key][4], json_data['data'][key][5], json_data['data'][key][3], last_WDIR, last_WSPD, last_TEMP, winddir, \
                                windspd, oat, last_DZDT, last_TPP, json_data['data'][key][17], last_clouddata))
              else:
                 bcolor = ANSIColors.FG_DEFAULT

          tfc_relpos = calculate_distance_and_bearing(args.lat, args.lon, 0, json_data['data'][key][1], json_data['data'][key][2], json_data['data'][key][3])

          flights.append(f"{bcolor}%6.2f %3.0f %8.4f %9.4f %08s %08s %04s %08s %05s %3d %03d %5s %5s %11s %08s{ANSIColors.RESET}" % (tfc_relpos['distance'], \
                         tfc_relpos['absolute_bearing'], json_data['data'][key][1], json_data['data'][key][2], json_data['data'][key][13], \
                         '' if json_data['data'][key][16] == 'null' else json_data['data'][key][16], json_data['data'][key][8], json_data['data'][key][9], \
                         json_data['data'][key][4], json_data['data'][key][5], json_data['data'][key][3],
                         '' if json_data['data'][key][11] == 'null' else json_data['data'][key][11], '' if json_data['data'][key][12] == 'null' else json_data['data'][key][12], \
                         json_data['data'][key][17], windinfo))

          if follow_param != None:
              if follow_param['id'] == json_data['data'][key][follow_param['data_index']]:
                  args.lat = float(json_data['data'][key][1])
                  args.lon = float(json_data['data'][key][2])
                  if json_data['data'][key][4] != None:
                      args.alt = float(json_data['data'][key][4]) / 3.28084
                  followOK = True

        if follow_param != None and not followOK and len(json_data) > 0:
            print(f"{ANSIColors.FG_RED}Oopsie daisy: The callsign {ANSIColors.BOLD}{follow_param['id']}{ANSIColors.RESET}{ANSIColors.FG_RED} could not be located{ANSIColors.RESET}")


        print(f"{ANSIColors.FG_CYAN}Current time: %s UTC{ANSIColors.RESET}" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        print(f"{ANSIColors.FG_CYAN}Traffic time: %s UTC{ANSIColors.RESET}" % datetime.fromtimestamp(json_data["dataepoch"], timezone.utc))
        if follow_param != None and followOK:
            follow = f", {ANSIColors.BG_GREEN}{ANSIColors.FG_BLACK}Following {follow_param['id']}{ANSIColors.RESET} {maxrecovery}"
        else:
            follow = ""
        print("Traffic source: %s%s" % (json_data["source"], follow))
        print(f"Request rate limits: Traffic: {traffic_request_rate_limit:.0f}s Weather: {weather_request_rate_limit:.0f}s")
        print("Total flights in the system: %s" % json_data["full_count"])
        print(f"Flights within radius: {args.radius}km")

        if  json_data["full_count"] == 0:
            traffic_count_zero += 1
        else:
            traffic_count_nonzero += 1

        if traffic_count_zero != 0 or auth_count > 1 or nearest_metar_error_count > 0 or weather_error_count > 0 or traffic_error_count > 0:
            dcolor = ANSIColors.BG_RED + ANSIColors.FG_BLACK
        else:
            dcolor = ANSIColors.BG_GREEN + ANSIColors.FG_BLACK

        print(f"{dcolor}DEBUG: TFC zero: {traffic_count_zero} TFC non-zero: {traffic_count_nonzero} ({traffic_count_zero/(traffic_count_zero+traffic_count_nonzero)*100:.2f}% zero) Auth-requests: {auth_count} NM err: {nearest_metar_error_count} WX err: {weather_error_count} TF err: {traffic_error_count} UDP err: {udp_error_count} {ANSIColors.RESET}" )

        print("")
        print("Dist  Brg  Lat       Lon      Callsign   Flight Type     Tail   Alt Gsp Trk  Orig  Dest      Source   Wind SAT")
        rows = 27 + args.nummetars*2
        moredata = False
        for f in sorted(flights):
          if rows > terminal_rows - 1:
              moredata = True
              continue
          print(f)
          rows += 1
        if moredata:
            print(f"{len(flights)-(27 + args.nummetars*2)} more flights not shown. Press ctrl-c to exit.")

        # sleep until next traffic fetch time has arrived
        while time.time() < next_traffic_request:
            time.sleep(0.1)



