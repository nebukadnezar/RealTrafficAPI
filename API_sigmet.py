#!/usr/bin/env python3

# API tester for /sigmet API

import requests
import json
import time
import sys
import os
import platform
from datetime import datetime
from argparse import ArgumentParser
import sqlite3
import re
from typing import List, Tuple

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
    # sigmet text indicates the newline with ^.
    result = result.replace("^", "\n")
    return result

#######################################################################################################
#######################################################################################################
if __name__ == '__main__':

    parser = ArgumentParser(description='RealTraffic API Tester')

    # Add optional argument, with given default values if user gives no arg
    parser.add_argument('-l', '--license', help='Your RealTraffic license, e.g. AABBCC-1234-AABBCC-123456')
    parser.add_argument('--toff', default=0, type=float, help="time offset in minutes")
    parser.add_argument('-api', '--api', default="v5", type=str, help="API endpoint to call, default v5")
    parser.add_argument('-d', '--dbdir', type=str, help="database directory where navdb.s3db is located")
    parser.add_argument('--server', default="rtwa", type=str, help="server name to connect to")

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
    software = "API_sigmet_example"
    API_version = args.api
    Server = f"https://{args.server}.flyrealtraffic.com/"

    #######################################################################################################
    #######################################################################################################
    # API constants
    auth_url = "%s/%s/auth" % (Server, API_version)
    deauth_url = "%s/%s/deauth" % (Server, API_version)
    sigmet_url = "%s/%s/sigmet" % (Server, API_version)

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

    time.sleep(traffic_request_rate_limit)

    sigmet_payload = { "GUID": "%s" % GUID,
               "toffset": int(args.toff) }

    try:
      response = requests.post(sigmet_url, sigmet_payload, headers=header)
      json_data = response.json()
    except Exception as e:
      print(e)
      print(response.text)
      # something borked. abort.
      print("error getting sigmet")
      exit(1)

    if json_data["status"] != 200:
      print(json_data["message"])
      exit(1)


    # Print the full response received
    print(json_data)

    # Don't forget to deauth after you're done
    payload = { "GUID": "%s" % GUID }
    data = requests.post(deauth_url, payload, headers=header).text
    print(data)


