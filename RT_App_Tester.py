#!/usr/bin/env python3
"""
RealTraffic Application Tester
==============================
Tests the indirect API functionality of the RealTraffic application.

This script:
1. Acts as a TCP server that RT connects to (simulating a flight simulator)
2. Sends position updates to RT (Qs121 messages)
3. Queries RT for version, time offset control settings
4. Requests parked traffic once (Qs999=sendparked) - one-time broadcast via UDP as RTPARK
5. Starts parked traffic (Qs999=startparked) - enables periodic 60s broadcasts
6. Stops parked traffic (Qs999=stopparked) - disables periodic broadcasts
7. Queries parked status (Qs999=statusparked) - returns current broadcast state
8. Sets a destination for destination traffic/weather (Qs376)
9. Listens for UDP broadcasts on ports 49004 (weather), 49005 (traffic/parked), 49006 (dest traffic)

Usage:
    python RT_App_Tester.py [--port 10747] [--lat -33.9461] [--lon 151.1772] [--alt 35000]
                           [--dest KLAX] [--duration 60]

Author: RealTraffic Development
Version: 1.6
"""

import socket
import threading
import json
import time
import argparse
import math
import sys
from datetime import datetime
from collections import defaultdict

# Conversion constants
D2R = math.pi / 180.0
R2D = 180.0 / math.pi

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class UDPListener(threading.Thread):
    """Thread to listen for UDP broadcasts from RT"""
    
    def __init__(self, port, name, callback):
        super().__init__(daemon=True)
        self.port = port
        self.name = name
        self.callback = callback
        self.running = True
        self.sock = None
        
    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('', self.port))
            self.sock.settimeout(1.0)
            
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(65535)
                    self.callback(self.name, self.port, data.decode('utf-8', errors='replace'), addr)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"{Colors.RED}UDP {self.name} error: {e}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}Failed to bind UDP port {self.port}: {e}{Colors.ENDC}")
        finally:
            if self.sock:
                self.sock.close()
                
    def stop(self):
        self.running = False


class RTAppTester:
    """Main tester class for RealTraffic Application"""
    
    def __init__(self, port=10747, lat=-33.9461, lon=151.1772, alt=1000, 
                 dest="KLAX", origin="YSSY", duration=60, parked_bounds=None):
        self.port = port
        self.lat = lat
        self.lon = lon
        self.alt = alt  # feet
        self.dest = dest
        self.origin = origin
        self.duration = duration
        self.parked_bounds = parked_bounds  # (bottom, left, top, right)
        
        # Aircraft parameters (stationary on ground)
        self.pitch = 0.0  # degrees
        self.bank = 0.0   # degrees
        self.track = 0.0  # degrees
        self.tas = 0      # m/s
        
        # Connection state
        self.client_socket = None
        self.connected = False
        self.running = True
        
        # Data storage
        self.weather_data = []
        self.traffic_data = []
        self.dest_traffic_data = []
        self.version_info = None
        self.timeoffset_info = None
        
        # Statistics
        self.stats = defaultdict(int)
        
        # UDP listeners
        self.udp_listeners = []
        
    def format_qs121_message(self):
        """Format the position message according to RT protocol"""
        # Qs121=pitch;bank;heading;alt;TAS;lat;lon
        # pitch: radians * 100000
        # bank: radians * 100000 * -1
        # heading/track: radians
        # alt: feet * 1000
        # TAS: m/s
        # lat: radians
        # lon: radians
        
        pitch_val = int(self.pitch * D2R * 100000)
        bank_val = int(self.bank * D2R * 100000) * -1
        track_val = self.track * D2R
        alt_val = int(self.alt * 1000)
        tas_val = self.tas
        lat_val = self.lat * D2R
        lon_val = self.lon * D2R
        
        msg = f"Qs121={pitch_val};{bank_val};{track_val:.15f};{alt_val};{tas_val};{lat_val:.15f};{lon_val:.15f}"
        return msg
    
    def udp_callback(self, name, port, data, addr):
        """Callback for UDP data received"""
        self.stats[f"udp_{name}"] += 1
        
        if port == 49004:  # Weather
            self.weather_data.append(data)
        elif port == 49005:  # Traffic (RTTFC, RTPARK)
            self.traffic_data.append(data)
            # Track parked traffic separately
            if data.startswith("RTPARK,"):
                self.stats["rtpark_count"] += 1
        elif port == 49006:  # Destination traffic
            self.dest_traffic_data.append(data)
            
    def start_udp_listeners(self):
        """Start UDP listener threads"""
        ports = [
            (49004, "Weather"),
            (49005, "Traffic"),
            (49006, "DestTraffic"),
        ]
        
        for port, name in ports:
            listener = UDPListener(port, name, self.udp_callback)
            listener.start()
            self.udp_listeners.append(listener)
            print(f"{Colors.CYAN}Started UDP listener on port {port} ({name}){Colors.ENDC}")
            
    def stop_udp_listeners(self):
        """Stop all UDP listeners"""
        for listener in self.udp_listeners:
            listener.stop()
            
    def send_message(self, msg):
        """Send a message to RT"""
        if self.client_socket and self.connected:
            try:
                self.client_socket.sendall((msg + "\n").encode('utf-8'))
                return True
            except Exception as e:
                print(f"{Colors.RED}Send error: {e}{Colors.ENDC}")
                return False
        return False
    
    def receive_response(self, timeout=2.0, expect_key=None):
        """Receive a response from RT
        
        Args:
            timeout: How long to wait for response
            expect_key: If set, keep reading until we get a response containing this key
        """
        if self.client_socket and self.connected:
            try:
                self.client_socket.settimeout(timeout)
                start_time = time.time()
                
                while (time.time() - start_time) < timeout:
                    try:
                        data = self.client_socket.recv(65535)
                        response = data.decode('utf-8', errors='replace').strip()
                        
                        if not response:
                            continue
                            
                        # If we're looking for a specific response type, check for it
                        if expect_key:
                            if expect_key in response:
                                return response
                            else:
                                # Got a different response, store it if it's useful
                                print(f"{Colors.YELLOW}  (Received other response: {response[:60]}...){Colors.ENDC}")
                                continue
                        else:
                            return response
                            
                    except socket.timeout:
                        if expect_key:
                            continue  # Keep trying if we're waiting for specific response
                        return None
                        
                return None
            except socket.timeout:
                return None
            except Exception as e:
                print(f"{Colors.RED}Receive error: {e}{Colors.ENDC}")
                return None
        return None
    
    def flush_receive_buffer(self):
        """Flush any pending data in the receive buffer"""
        if self.client_socket and self.connected:
            self.client_socket.setblocking(False)
            try:
                while True:
                    data = self.client_socket.recv(65535)
                    if not data:
                        break
            except BlockingIOError:
                pass  # No more data
            except Exception:
                pass
            finally:
                self.client_socket.setblocking(True)
    
    def query_version(self):
        """Query RT version information"""
        print(f"\n{Colors.BOLD}Querying version...{Colors.ENDC}")
        self.flush_receive_buffer()
        if self.send_message("Qs999=version"):
            response = self.receive_response(timeout=3.0, expect_key="version")
            if response:
                try:
                    self.version_info = json.loads(response)
                    print(f"{Colors.GREEN}Version: {self.version_info}{Colors.ENDC}")
                except json.JSONDecodeError:
                    print(f"{Colors.YELLOW}Version response (raw): {response}{Colors.ENDC}")
                    self.version_info = response
                    
    def query_timeoffset_control(self):
        """Query time offset control setting"""
        print(f"\n{Colors.BOLD}Querying time offset control...{Colors.ENDC}")
        self.flush_receive_buffer()
        if self.send_message("Qs999=timeoffsetcontrol=?"):
            response = self.receive_response(timeout=3.0, expect_key="timeoffsetcontrol")
            if response:
                try:
                    self.timeoffset_info = json.loads(response)
                    print(f"{Colors.GREEN}Time offset control: {self.timeoffset_info}{Colors.ENDC}")
                except json.JSONDecodeError:
                    print(f"{Colors.YELLOW}Time offset response (raw): {response}{Colors.ENDC}")
                    self.timeoffset_info = response
                    
    def request_parked_traffic(self, bounds=None):
        """Request parked traffic data ONE TIME (will be broadcast via UDP on port 49005)
        Does NOT enable periodic broadcasts.
        
        Args:
            bounds: Optional tuple of (bottom, left, top, right) in degrees
        """
        if bounds:
            print(f"\n{Colors.BOLD}Requesting parked traffic (one-time) with bounds {bounds}...{Colors.ENDC}")
            msg = f"Qs999=sendparked,{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
        else:
            print(f"\n{Colors.BOLD}Requesting parked traffic (one-time, default 6NM radius)...{Colors.ENDC}")
            msg = "Qs999=sendparked"
            
        if self.send_message(msg):
            print(f"{Colors.GREEN}Parked traffic request sent (one-time broadcast){Colors.ENDC}")
            print(f"{Colors.GREEN}Will be received via UDP (port 49005, RTPARK format){Colors.ENDC}")
    
    def start_parked_traffic(self, bounds=None):
        """Start periodic parked traffic broadcasts (every 60s)
        
        Args:
            bounds: Optional tuple of (bottom, left, top, right) in degrees
        """
        if bounds:
            print(f"\n{Colors.BOLD}Starting parked traffic broadcasts with bounds {bounds}...{Colors.ENDC}")
            msg = f"Qs999=startparked,{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
        else:
            print(f"\n{Colors.BOLD}Starting parked traffic broadcasts (default 6NM radius)...{Colors.ENDC}")
            msg = "Qs999=startparked"
            
        if self.send_message(msg):
            print(f"{Colors.GREEN}Parked traffic broadcasts started (60s interval){Colors.ENDC}")
            print(f"{Colors.GREEN}Will be received via UDP (port 49005, RTPARK format){Colors.ENDC}")
    
    def stop_parked_traffic(self):
        """Stop periodic parked traffic broadcasts"""
        print(f"\n{Colors.BOLD}Stopping parked traffic broadcasts...{Colors.ENDC}")
        msg = "Qs999=stopparked"
        if self.send_message(msg):
            print(f"{Colors.GREEN}Parked traffic broadcasts stopped{Colors.ENDC}")
    
    def status_parked_traffic(self):
        """Query parked traffic broadcast status"""
        print(f"\n{Colors.BOLD}Querying parked traffic status...{Colors.ENDC}")
        msg = "Qs999=statusparked"
        self.flush_receive_buffer()
        if self.send_message(msg):
            response = self.receive_response(timeout=2.0, expect_key="parkedBroadcast")
            if response:
                try:
                    data = json.loads(response)
                    status = data.get('parkedBroadcast', False)
                    print(f"{Colors.GREEN}Parked broadcast status: {status}{Colors.ENDC}")
                    return status
                except json.JSONDecodeError:
                    print(f"{Colors.YELLOW}Unexpected response: {response}{Colors.ENDC}")
            else:
                print(f"{Colors.YELLOW}No response received{Colors.ENDC}")
        return None
                    
    def set_destination(self):
        """Set destination airport for destination traffic/weather"""
        print(f"\n{Colors.BOLD}Setting destination to {self.dest}...{Colors.ENDC}")
        msg = f"Qs376={self.origin};{self.dest}"
        if self.send_message(msg):
            print(f"{Colors.GREEN}Destination set: {self.origin} -> {self.dest}{Colors.ENDC}")
            
    def handle_client(self, client_socket, addr):
        """Handle the connection from RT"""
        print(f"\n{Colors.GREEN}RT connected from {addr}{Colors.ENDC}")
        self.client_socket = client_socket
        self.connected = True
        
        # Send initial position
        time.sleep(0.5)
        pos_msg = self.format_qs121_message()
        print(f"{Colors.CYAN}Sending position: {pos_msg}{Colors.ENDC}")
        self.send_message(pos_msg)
        
        # Wait a bit for RT to process and start sending data
        time.sleep(3)
        
        # Query version
        self.query_version()
        time.sleep(1.0)
        
        # Query time offset control
        self.query_timeoffset_control()
        time.sleep(1.0)
        
        # Set destination
        self.set_destination()
        time.sleep(1.0)
        
        # Start parked traffic periodic broadcasts (default 6NM)
        self.start_parked_traffic()
        
        # Also test with custom bounds if provided
        if self.parked_bounds:
            time.sleep(1.0)
            self.start_parked_traffic(bounds=self.parked_bounds)
        
        # Continue sending position updates
        start_time = time.time()
        update_count = 0
        
        print(f"\n{Colors.BOLD}Sending position updates for {self.duration} seconds...{Colors.ENDC}")
        print(f"{Colors.CYAN}Position: {self.lat:.4f}, {self.lon:.4f} @ {self.alt}ft{Colors.ENDC}")
        print(f"{Colors.CYAN}Listening for UDP broadcasts...{Colors.ENDC}\n")
        
        while self.running and (time.time() - start_time) < self.duration:
            # Send position at ~5Hz
            pos_msg = self.format_qs121_message()
            self.send_message(pos_msg)
            update_count += 1
            
            # Print status every 10 seconds
            elapsed = time.time() - start_time
            if update_count % 50 == 0:  # Every 10 seconds at 5Hz
                rtpark_count = self.stats.get("rtpark_count", 0)
                print(f"{Colors.YELLOW}[{elapsed:.0f}s] Sent {update_count} position updates | "
                      f"Weather: {len(self.weather_data)} | Traffic: {len(self.traffic_data)} "
                      f"(RTPARK: {rtpark_count}) | DestTraffic: {len(self.dest_traffic_data)}{Colors.ENDC}")
            
            time.sleep(0.2)  # 5Hz
            
        self.connected = False
        print(f"\n{Colors.BOLD}Test duration complete.{Colors.ENDC}")
        
    def run_server(self):
        """Run the TCP server that RT connects to"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind(('0.0.0.0', self.port))
            server_socket.listen(1)
            server_socket.settimeout(1.0)
            
            print(f"\n{Colors.BOLD}{'='*60}{Colors.ENDC}")
            print(f"{Colors.BOLD}RealTraffic Application Tester{Colors.ENDC}")
            print(f"{Colors.BOLD}{'='*60}{Colors.ENDC}")
            print(f"\n{Colors.GREEN}TCP Server listening on port {self.port}{Colors.ENDC}")
            print(f"{Colors.CYAN}Configure RT to connect to this host on port {self.port}{Colors.ENDC}")
            print(f"{Colors.CYAN}Waiting for RT to connect...{Colors.ENDC}\n")
            
            # Start UDP listeners
            self.start_udp_listeners()
            
            while self.running:
                try:
                    client_socket, addr = server_socket.accept()
                    self.handle_client(client_socket, addr)
                    break  # Only handle one connection for this test
                except socket.timeout:
                    continue
                    
        except Exception as e:
            print(f"{Colors.RED}Server error: {e}{Colors.ENDC}")
        finally:
            server_socket.close()
            self.stop_udp_listeners()
            
    def print_summary(self):
        """Print summary of collected data"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}TEST SUMMARY{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*60}{Colors.ENDC}")
        
        # Version info
        print(f"\n{Colors.BOLD}--- RT Application Info ---{Colors.ENDC}")
        if self.version_info:
            if isinstance(self.version_info, dict):
                print(f"  Version: {self.version_info.get('version', 'N/A')}")
                print(f"  License Level: {self.version_info.get('level', 'N/A')}")
            else:
                print(f"  Response: {self.version_info}")
        else:
            print(f"  {Colors.RED}No version info received{Colors.ENDC}")
            
        if self.timeoffset_info:
            if isinstance(self.timeoffset_info, dict):
                print(f"  Time Offset Control: {self.timeoffset_info.get('timeoffsetcontrol', 'N/A')}")
            else:
                print(f"  Time Offset: {self.timeoffset_info}")
                
        # Weather summary
        print(f"\n{Colors.BOLD}--- Weather Data (Port 49004) ---{Colors.ENDC}")
        print(f"  Total packets received: {len(self.weather_data)}")
        if self.weather_data:
            try:
                latest_wx = json.loads(self.weather_data[-1])
                print(f"  Latest weather sample:")
                print(f"    ICAO: {latest_wx.get('ICAO', 'N/A')}")
                print(f"    QNH: {latest_wx.get('QNH', 'N/A')} hPa")
                print(f"    METAR: {latest_wx.get('METAR', 'N/A')[:80]}...")
                if 'AM' in latest_wx:
                    print(f"    Adjacent METARs: {len(latest_wx['AM'])} stations")
                if 'locWX' in latest_wx:
                    locwx = latest_wx['locWX']
                    print(f"    Local Weather:")
                    print(f"      Temperature: {locwx.get('T', 'N/A')}C")
                    print(f"      Wind: {locwx.get('WDIR', 'N/A')}@{locwx.get('WSPD', 'N/A')}kt")
                    print(f"      SLP: {locwx.get('SLP', 'N/A')} hPa")
            except json.JSONDecodeError:
                print(f"  Latest (raw): {self.weather_data[-1][:100]}...")
        
        # Traffic summary (RTTFC format)
        print(f"\n{Colors.BOLD}--- Location Traffic Data (Port 49005) ---{Colors.ENDC}")
        print(f"  Total packets received: {len(self.traffic_data)}")
        if self.traffic_data:
            # Parse RTTFC and RTPARK records
            rttfc_records = []
            rtpark_records = []
            for packet in self.traffic_data:
                if packet.startswith("RTTFC,"):
                    rttfc_records.append(packet)
                elif packet.startswith("RTPARK,"):
                    rtpark_records.append(packet)
                    
            print(f"  RTTFC records (flying/taxiing): {len(rttfc_records)}")
            print(f"  RTPARK records (parked): {len(rtpark_records)}")
            
            if rttfc_records:
                # Show first example
                parts = rttfc_records[0].split(',')
                if len(parts) >= 15:
                    print(f"  Example RTTFC record:")
                    print(f"    Hex ID: {parts[1]}")
                    print(f"    Position: {parts[2]}, {parts[3]}")
                    print(f"    Altitude: {parts[4]} ft")
                    print(f"    VS: {parts[5]} fpm")
                    print(f"    Track: {parts[7]} deg")
                    print(f"    Speed: {parts[8]} kt")
                    print(f"    Callsign: {parts[9]}")
                    print(f"    Type: {parts[10]}")
                    print(f"    Rego: {parts[11]}")
                    print(f"    Route: {parts[12]} -> {parts[13]}")
                    
            if rtpark_records:
                # Show first RTPARK example
                # Format: RTPARK,hexid,lat,lon,callsign,type,registration,gate,timestamp
                parts = rtpark_records[0].split(',')
                if len(parts) >= 9:
                    print(f"  Example RTPARK record:")
                    print(f"    Hex ID: {parts[1]}")
                    print(f"    Position: {parts[2]}, {parts[3]}")
                    print(f"    Callsign: {parts[4]}")
                    print(f"    Type: {parts[5]}")
                    print(f"    Rego: {parts[6]}")
                    print(f"    Gate: {parts[7]}")
                    
        # Destination traffic
        print(f"\n{Colors.BOLD}--- Destination Traffic Data (Port 49006) ---{Colors.ENDC}")
        print(f"  Total packets received: {len(self.dest_traffic_data)}")
        if self.dest_traffic_data:
            # Check if it's weather or traffic
            for packet in self.dest_traffic_data[-1:]:
                if packet.startswith("RTTFC,") or packet.startswith("RTDEST,"):
                    parts = packet.split(',')
                    if len(parts) >= 10:
                        print(f"  Example destination traffic:")
                        print(f"    Callsign: {parts[9] if len(parts) > 9 else 'N/A'}")
                        print(f"    Position: {parts[2]}, {parts[3]}")
                else:
                    try:
                        dest_data = json.loads(packet)
                        print(f"  Destination weather sample:")
                        print(f"    ICAO: {dest_data.get('ICAO', 'N/A')}")
                        print(f"    QNH: {dest_data.get('QNH', 'N/A')} hPa")
                        print(f"    METAR: {dest_data.get('METAR', 'N/A')[:60]}...")
                    except:
                        print(f"  Latest (raw): {packet[:100]}...")
                        
        # Parked traffic (received via UDP as RTPARK packets)
        print(f"\n{Colors.BOLD}--- Parked Traffic (RTPARK via UDP 49005) ---{Colors.ENDC}")
        rtpark_count = self.stats.get("rtpark_count", 0)
        print(f"  RTPARK packets received: {rtpark_count}")
        if rtpark_count > 0:
            # Find and show an example RTPARK record
            # Format: RTPARK,hexid,lat,lon,callsign,type,registration,gate,timestamp
            for packet in self.traffic_data:
                if packet.startswith("RTPARK,"):
                    parts = packet.split(',')
                    if len(parts) >= 9:
                        print(f"  Example parked aircraft:")
                        print(f"    Hex ID: {parts[1]}")
                        print(f"    Position: {parts[2]}, {parts[3]}")
                        print(f"    Callsign: {parts[4]}")
                        print(f"    Type: {parts[5]}")
                        print(f"    Rego: {parts[6]}")
                        print(f"    Gate: {parts[7]}")
                    break
        else:
            print(f"  {Colors.YELLOW}No parked traffic received (requires Professional license or Spotter Mode){Colors.ENDC}")
            
        print(f"\n{Colors.BOLD}{'='*60}{Colors.ENDC}")


def main():
    parser = argparse.ArgumentParser(
        description='RealTraffic Application Tester - Tests indirect API functionality',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python RT_App_Tester.py
      Run with defaults (YSSY, port 10747, 60 seconds)
      
  python RT_App_Tester.py --lat 34.0522 --lon -118.2437 --alt 0 --dest KSFO
      Test at LAX position with destination SFO
      
  python RT_App_Tester.py --port 10748 --duration 120
      Use different port and run for 2 minutes
      
  python RT_App_Tester.py --parked-bounds "-34.0,151.0,-33.8,151.3"
      Request parked traffic with custom bounds (bottom,left,top,right)
        """
    )
    
    parser.add_argument('--port', type=int, default=10747,
                        help='TCP port to listen on (default: 10747)')
    parser.add_argument('--lat', type=float, default=-33.9461,
                        help='Latitude in degrees (default: -33.9461 = YSSY)')
    parser.add_argument('--lon', type=float, default=151.1772,
                        help='Longitude in degrees (default: 151.1772 = YSSY)')
    parser.add_argument('--alt', type=float, default=1000,
                        help='Altitude in feet (default: 1000)')
    parser.add_argument('--origin', type=str, default='YSSY',
                        help='Origin airport ICAO (default: YSSY)')
    parser.add_argument('--dest', type=str, default='KLAX',
                        help='Destination airport ICAO (default: KLAX)')
    parser.add_argument('--duration', type=int, default=60,
                        help='Test duration in seconds (default: 60)')
    parser.add_argument('--parked-bounds', type=str, default=None,
                        help='Custom parked traffic bounds: bottom,left,top,right (e.g. "-34.0,151.0,-33.8,151.3")')
    
    args = parser.parse_args()
    
    # Parse parked bounds if provided
    parked_bounds = None
    if args.parked_bounds:
        try:
            parts = [float(x.strip()) for x in args.parked_bounds.split(',')]
            if len(parts) == 4:
                parked_bounds = tuple(parts)
            else:
                print(f"Warning: Invalid parked-bounds format, ignoring")
        except ValueError:
            print(f"Warning: Could not parse parked-bounds, ignoring")
    
    tester = RTAppTester(
        port=args.port,
        lat=args.lat,
        lon=args.lon,
        alt=args.alt,
        origin=args.origin,
        dest=args.dest,
        duration=args.duration,
        parked_bounds=parked_bounds
    )
    
    try:
        tester.run_server()
        tester.print_summary()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.ENDC}")
        tester.running = False
        tester.print_summary()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
