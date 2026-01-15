#!/usr/bin/env python3

# API tester for /nearestmetar API

import requests
import json
import time
import sys
import os
import platform
from datetime import datetime
from argparse import ArgumentParser
import sqlite3

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
    parser.add_argument('--lat', type=float, help="center latitude")
    parser.add_argument('--lon', type=float, help="center latitude")
    parser.add_argument('--alt', default=0, type=float, help="altitude")
    parser.add_argument('-d', '--dbdir', default="/Users/balt/Documents/.InsideSystems", type=str, help="database directory where navdb.s3db is located")
    parser.add_argument('--toff', default=0, type=float, help="time offset in minutes")
    parser.add_argument('--nummetars', default=3, type=int, help="The number of nearest airport METARs to display. Default is 3")
    parser.add_argument('-api', '--api', default="v5", type=str, help="API endpoint to call, default v5")
    parser.add_argument('--server', default="rtwa", type=str, help="server name to connect to")

    args = parser.parse_args()

    if (args.lat == None and args.lon == None) and args.airport == None:
        print("You need to indicate either a lat/lon, or an airport code for the location")
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

    #######################################################################################################
    #######################################################################################################
    # application specific settings
    software = "API_nearestmetar_example"
    API_version = args.api
    Server = f"https://{args.server}.flyrealtraffic.com/"

    #######################################################################################################
    #######################################################################################################
    # API constants
    auth_url = "%s/%s/auth" % (Server, API_version)
    deauth_url = "%s/%s/deauth" % (Server, API_version)
    nearestmetar_url = "%s/%s/nearestmetar" % (Server, API_version)

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

    # set up rate limitation
    time.sleep(weather_request_rate_limit)

    nearestmetar_payload = { "GUID": "%s" % GUID,
               "maxcount": args.nummetars,
               "lat": args.lat,
               "lon": args.lon,
               "toffset": int(args.toff) }

    try:
      response = requests.post(nearestmetar_url, nearestmetar_payload, headers=header)
      json_data = response.json()
    except Exception as e:
      print(e)
      print(response.text)
      # something borked. abort.
      print("error getting nearest metar airport code")
      exit(1)

    if json_data["status"] != 200:
      print(json_data["message"])
      exit(1)

    print(custom_json_formatter(json_data))

    # Don't forget to deauth after you're done
    payload = { "GUID": "%s" % GUID }
    data = requests.post(deauth_url, payload, headers=header).text
    print(data)

