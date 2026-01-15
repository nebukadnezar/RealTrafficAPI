#!/usr/bin/env python3

# API tester for RealTraffic /traffic API

import requests
import json
import time
import sys
import os
import platform
import signal
from datetime import datetime
from argparse import ArgumentParser
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.img_tiles as cimgt
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
import textalloc as ta
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
# plot parket aircraft positions
def plot_parked_aircraft_positions(aircraft_data, filename):

    lats = []
    lons = []
    css = []
    types = []
    gates = []

    #{"7c48c8": [-33.928745, 151.168274, 0.0, "B733", "VH-ONU", 1721679694.3, "TFX404"]
    for key in aircraft_data:
        lats.append(aircraft_data[key][0])
        lons.append(aircraft_data[key][1])
        gates.append(aircraft_data[key][2])
        types.append(aircraft_data[key][3])
        css.append(aircraft_data[key][6])


    # Determine map extent
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # Add some padding
    lat_padding = (max_lat - min_lat) * 0.1
    lon_padding = (max_lon - min_lon) * 0.1
    map_extent = [min_lon - lon_padding, max_lon + lon_padding,
                  min_lat - lat_padding, max_lat + lat_padding]

    # Create the map
    plt.figure(figsize=(15, 10))
    #ax = plt.axes(projection=ccrs.PlateCarree())
    #ax.set_extent(map_extent, crs=ccrs.PlateCarree())

    zoom = zoomlevel_from_deg((max_lon-min_lon)/6) # 10 #  0-19
    print(f"Zoom Level: {zoom}")

    request = cimgt.OSM(desired_tile_form="L")
    ax = plt.axes(projection=request.crs)
    ax.set_extent(map_extent)
    ax.add_image(request, zoom, alpha=0.3, cmap='gray')    # 6 = zoom level

    # Add map features
    #ax.add_feature(cfeature.LAND)
    #ax.add_feature(cfeature.OCEAN)
    #ax.add_feature(cfeature.COASTLINE)
    #ax.add_feature(cfeature.BORDERS, linestyle=':')

    # Add gridlines
    ax.gridlines(draw_labels=True)

    # Plot each aircraft
    labels = []
    for lat, lon, cs, type, gate in zip(lats, lons, css, types, gates):
        labels.append(f"{cs} {type}\n{gate}")
        ax.plot(lon, lat, 'ro', markersize=5, transform=ccrs.PlateCarree())

        # Plot aircraft
        ax.scatter

    text_list = labels
    ta.allocate(ax,lons, lats,
                text_list,
                x_scatter=lons, y_scatter=lats,
                textsize=6,
                draw_lines=True,
                linewidth=0.5,
                draw_all=True,
                transform=ccrs.PlateCarree(),
                avoid_label_lines_overlap=True)
    # Set title
    plt.title('Aircraft Positions for parkedtraffic')

    # Show the plot
    if filename == True:
        plt.show()
    else:
        plt.savefig(filename, bbox_inches='tight')

#######################################################################################################
# plot flying aircraft
def plot_flying_aircraft_positions(aircraft_data, filename):

    #   0    1     2       3      4     5    6      7        8         9         10        11        12      13   14         15       16         17       18  19   20     21          22     23               24        25         26          27        28         29               30               31          32      33    34   35      36      37       38  39    40     41   42  43  44    45   46       47
    # (hex, lat, lon, track, alt_baro, gs, squawk, "X2", ac_type, ac_tailno, seen_pos, from_iata, to_iata, cs_icao, gnd, baro_rate, cs_iata, msg_type, alt_geom, ias, tas, mach, track_rate, roll, mag_heading, true_heading, geom_rate, emergency, category, nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading, nav_modes, nic, rc, nic_baro, nac_p, nac_v, seen, rssi, alert, spi, wd, ws, oat, tat, icaohex, record_augmented)

    lats = []
    lons = []
    css = []
    types = []
    alts = []
    trks = []
    spds = []

    for key in aircraft_data:
        lats.append(aircraft_data[key][1])
        lons.append(aircraft_data[key][2])
        alts.append(aircraft_data[key][4])
        types.append(aircraft_data[key][8])
        css.append(aircraft_data[key][13])
        trks.append(aircraft_data[key][3])
        spds.append(aircraft_data[key][5])

    # Determine map extent
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # Add some padding
    lat_padding = (max_lat - min_lat) * 0.1
    lon_padding = (max_lon - min_lon) * 0.1
    map_extent = [min_lon - lon_padding, max_lon + lon_padding,
                  min_lat - lat_padding, max_lat + lat_padding]

    # Create the map
    plt.figure(figsize=(15, 10))
    #ax = plt.axes(projection=ccrs.PlateCarree())
    #ax.set_extent(map_extent, crs=ccrs.PlateCarree())

    zoom = zoomlevel_from_deg((max_lon-min_lon)/5) # 10 #  0-19
    print(f"Zoom Level: {zoom}")

    request = cimgt.OSM(desired_tile_form="L")
    ax = plt.axes(projection=request.crs)
    ax.set_extent(map_extent)
    ax.add_image(request, zoom, alpha=0.3, cmap='gray')    # 6 = zoom level

    # Add map features
    #ax.add_feature(cfeature.LAND)
    #ax.add_feature(cfeature.OCEAN)
    #ax.add_feature(cfeature.COASTLINE)
    #ax.add_feature(cfeature.BORDERS, linestyle=':')

    # Add gridlines
    ax.gridlines(draw_labels=True)

    # Plot each aircraft
    labels = []
    for lat, lon, cs, type, trk, spd, alt in zip(lats, lons, css, types, trks, spds, alts):
        labels.append(f"{cs} {type}\n{spd} {alt}")

        # Plot aircraft with orientation
        length = abs(map_extent[0] - map_extent[1]) / 100
        for lon, lat, trk in zip(lons, lats, trks):
            aircraft = FancyArrowPatch(
                (lon - length * sin(radians(trk)), lat - length * cos(radians(trk))),
                (lon + length * sin(radians(trk)), lat + length * cos(radians(trk))),
                mutation_scale=10,
                color='blue',
                transform=ccrs.PlateCarree()
            )
            ax.add_patch(aircraft)


    text_list = labels
    ta.allocate(ax,lons, lats,
                text_list,
                x_scatter=lons, y_scatter=lats,
                textsize=6,
                draw_lines=True,
                linewidth=0.5,
                draw_all=False,
                transform=ccrs.PlateCarree(),
                avoid_label_lines_overlap=True)
    # Set title
    plt.title('Aircraft Positions for locationtraffic')

    # Show the plot
    if filename == True:
        plt.show()
    else:
        plt.savefig(filename, bbox_inches='tight')

#######################################################################################################
# Custom formatter to pretty print the weather data
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

    parser = ArgumentParser(description='RealTraffic API Tester')

    # Add optional argument, with given default values if user gives no arg
    parser.add_argument('-l', '--license', help='Your RealTraffic license, e.g. AABBCC-1234-AABBCC-123456')
    parser.add_argument('-a', '--airport', type=str, help='ICAO code of airport to go to, instead of lat/lon')
    parser.add_argument('-t', '--traffictype', type=str, required=True,
                        choices=['locationtraffic', 'destinationtraffic', 'parkedtraffic'],
                        help="Specify the type of traffic: locationtraffic, destinationtraffic, or parkedtraffic")
    parser.add_argument('--plot', type=str,  nargs='?', const=True, default=False, help="If passed without parameter, shows the plot in a window. If parameter is given, uses the parameter as filename")
    parser.add_argument('--lat', type=float, help="center latitude")
    parser.add_argument('--lon', type=float, help="center latitude")
    parser.add_argument('--alt', default=0, type=float, help="altitude")
    parser.add_argument('-d', '--dbdir', type=str, help="database directory where navdb.s3db is located")
    parser.add_argument('--toff', default=0, type=float, help="time offset in minutes")
    parser.add_argument('-api', '--api', default="v5", type=str, help="API endpoint to call, default v5")
    parser.add_argument('-r', '--radius', type=float, default=100, help="length of box side in km, default 100km")
    parser.add_argument('--server', default="rtwa", type=str, help="server name to connect to. Defaults to rtw, don't change this unless asked to.")

    args = parser.parse_args()

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

    #######################################################################################################
    #######################################################################################################
    # application specific settings
    software = "API_traffic_example"
    API_version = args.api
    Server = f"https://{args.server}.flyrealtraffic.com/"

    #######################################################################################################
    #######################################################################################################
    # API constants
    auth_url = "%s/%s/auth" % (Server, API_version)
    deauth_url = "%s/%s/deauth" % (Server, API_version)
    traffic_url = "%s/%s/traffic" % (Server, API_version)

    header = { "Accept-encoding": "gzip" }
    license_types = { 0: "Standard", 1: "Standard", 2: "Professional" }

    if args.dbdir != None:
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
                if args.alt == None:
                    args.alt = apt[0][3]
            else:
                print("No matching airports found")
                exit(1)

    # convert altitude to meters
    args.alt /= 3.28084

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

    # wait to avoid request rate violation
    time.sleep(traffic_request_rate_limit)

    left = args.lon - 1/cos(radians(args.lat)) * args.radius / 111
    right = args.lon + 1/cos(radians(args.lat)) * args.radius / 111
    top = args.lat + args.radius / 111
    bottom = args.lat - args.radius / 111

    if left < -180: left += 360
    if left > 180: left -= 360
    if right < -180: right += 360
    if right > 180: right -= 360

    traffic_payload = { "GUID": "%s" % GUID,
               "querytype": args.traffictype,
               "top": top,
               "bottom": bottom,
               "left": left,
               "right": right,
               "toffset": int(args.toff) }


    try:
      response = requests.post(traffic_url, traffic_payload, headers=header)
      json_data = response.json()
    except Exception as e:
      print(e)
      print(response.text)
      # something borked. abort.
      print("error getting traffic")
      exit(1)

    if json_data["status"] != 200:
      print(json_data["message"])
      exit(1)


    if 'dataepoch' in json_data:
        print("Traffic date:", datetime.fromtimestamp(json_data['dataepoch']).strftime("%Y-%m-%d %H:%M:%S"))

    # Print the full response received
    print(custom_json_formatter(json_data))

    if len(json_data["data"]) == 0:
        print("No aicraft returned")


    if args.plot and len(json_data["data"]) != 0:
        print("plotting...")
        if args.traffictype == "parkedtraffic":
            plot_parked_aircraft_positions(json_data["data"], args.plot)
        else:
            plot_flying_aircraft_positions(json_data["data"], args.plot)

    # Don't forget to deauth after you're done
    payload = { "GUID": "%s" % GUID }
    data = requests.post(deauth_url, payload, headers=header).text
    print(data)

