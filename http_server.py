import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import pexpect
import re
import subprocess
subprocess.run(["python3", "-m", "pip", "install", "pandas"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) # Ensure pandas is installed
import pandas as pd
from io import StringIO
import bittensor as bt
from datetime import datetime, timedelta
import os
import hashlib
import threading
import time
import json


PORT = 41337
subtensor_address = "127.0.0.1:9944"
CACHE_DURATION = timedelta(minutes=7)  # Cache freshness duration
CACHE_KEEP_ALIVE_INTERVAL = 30  # Cache check interval in seconds, adjusted here
CACHE_FILE = "cache_state.json"
CACHE_PATHS_TO_SKIP = {'/favicon.ico'}


class Server(socketserver.TCPServer):
    allow_reuse_address = True


def clean_chars(str_data):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|τ')
    return ansi_escape.sub('', str_data)


def get_hash_key(path, query_params):
    return hashlib.md5((str(path) + str(query_params)).encode()).hexdigest()


def trim_output_from_pattern(output, start_pattern):
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if len(start_pattern) > 0 and line.strip()[:len(start_pattern)] == start_pattern:
            return '\n'.join(lines[i:])
    return ''


def get_subnet_weight(subnet_id, subtensor):
    return float(subtensor.get_emission_value_by_subnet(netuid=subnet_id))


def handle_request(path, query_params):
    #print(path)
    #quit()

    output = ""

    if path == '/wallet-balance':
        # Run the subnet list command
        command = f"/usr/local/bin/btcli w balance --all --subtensor.network finney --subtensor.chain_endpoint ws://{subtensor_address}"
        child = pexpect.spawn(command, dimensions=(500, 500))
        child.expect(pexpect.EOF)
        cmd_output = child.before.decode(errors='ignore')
        cmd_output = clean_chars(cmd_output)
        cmd_output = trim_output_from_pattern(cmd_output, "Wallet Coldkey Balances")
        lines = cmd_output.splitlines()[1:-1]

        cmd_output = '\n'.join(lines)
        string_io_obj = StringIO(cmd_output)
        df = pd.read_fwf(string_io_obj, colspecs='infer')
        output += df.to_csv(index=False)

    elif path == '/subnet-list':
        # Run the subnet list command
        command = f"/usr/local/bin/btcli s list --subtensor.chain_endpoint ws://{subtensor_address}"
        child = pexpect.spawn(command, dimensions=(500, 500))
        child.expect(pexpect.EOF)
        cmd_output = child.before.decode(errors='ignore')
        cmd_output = clean_chars(cmd_output)
        cmd_output = trim_output_from_pattern(cmd_output, "Subnets")
        lines = cmd_output.splitlines()[1:-1]

        # add a column to the end of the first line
        lines[0] += "  WEIGHT"

        # connect to the subtensor chain
        subtensor = bt.subtensor(network=f"ws://{subtensor_address}")

        #  for each line, take the first column and look up the subnet emission, using the key as the index
        for i, line in enumerate(lines):
            # skip the first row, since it's the header
            if i > 0:
                subnet_id = line.split()[0]
                weight = get_subnet_weight(subnet_id, subtensor)
                lines[i] += f"  {weight}"

        cmd_output = '\n'.join(lines)
        string_io_obj = StringIO(cmd_output)
        df = pd.read_fwf(string_io_obj, colspecs='infer')
        output += df.to_csv(index=False)

    elif path == '/metagraph':
        netuids = query_params.get('netuid', [''])[0].split(',')
        sanitized_egrep_keys = [re.escape(key) for key in query_params.get('egrep', []) if re.match(r'^[a-zA-Z0-9]+$', key)]
        pattern = "|".join(sanitized_egrep_keys)

        
        for netuid in netuids:
            lines = []
            if re.match(r'^\d+$', netuid):
                command = f"/usr/local/bin/btcli s metagraph --netuid={netuid} --subtensor.chain_endpoint ws://{subtensor_address}"
                child = pexpect.spawn(command, dimensions=(500, 500))
                child.expect(pexpect.EOF)
                netuid_output = child.before.decode(errors='ignore')
                netuid_output = clean_chars(netuid_output)
                netuid_output = trim_output_from_pattern(netuid_output, "Metagraph")

                netuid_lines = netuid_output.splitlines()
                for line in netuid_lines:
                    if sanitized_egrep_keys and re.search(pattern, line):
                        lines.append(f"{netuid}  {line}")
                    elif not sanitized_egrep_keys:
                        lines.append(f"{netuid}  {line}")
            else:
                return

            netuid_output = '\n'.join(lines)
            string_io_obj = StringIO(netuid_output)

            df = pd.read_fwf(string_io_obj, colspecs='infer')

            # Convert DataFrame to CSV string
            output += df.to_csv(index=False)

    elif path == '/registrations':

        unique_entries = []
        log_pattern = re.compile(r'btt_register_sn(\d+)_ck(\d+)-hk(\d+)(?:_\d{4}-\d{2}-\d{2})?\.log')
        log_directory = os.path.expanduser("~/logs/bittensor")
        timestamp_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| \{Attempting SN registration')


        for filename in os.listdir(log_directory):
            match = log_pattern.match(filename)
            if match:
                subnet, coldkey, hotkey = match.groups()
                filepath = os.path.join(log_directory, filename)
                
                with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                    lines = file.readlines()

                for i, line in enumerate(lines):
                    if '[32mRegistered' in line:

                        timestamp = None
                        cost = "N/A"

                        # Search backwards for cost and timestamp
                        for j in range(i-1, -1, -1):
                            if not timestamp:
                                timestamp_match = timestamp_pattern.search(lines[j])
                                if timestamp_match:
                                    timestamp = timestamp_match.group(1)
                            if "to register on subnet:" in lines[j]:
                                cost_match = re.search(r'τ([\d.]+)', lines[j])
                                if cost_match:
                                    cost = cost_match.group(1)
                                    break

                        file_stats = os.stat(filepath)
                        modified_time = datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        base_filename = os.path.basename(filepath)

                        new_entry = {
                            'Subnet': subnet, 
                            'ColdKey': coldkey, 
                            'HotKey': hotkey,
                            'Cost': cost, 
                            'Line': str(i + 1), 
                            'Timestamp': timestamp or modified_time,  # Use discovered timestamp or file modified time
                            'Filename': base_filename
                        }
                        unique_entries.append(new_entry)

        df = pd.DataFrame(unique_entries)  # Create DataFrame directly from the list of dictionaries

        df = df.sort_values(by=['Timestamp', 'Subnet', 'ColdKey', 'HotKey', 'Line'], ascending=[False, True, True, True, False])

        # Convert DataFrame to CSV string
        output += df.to_csv(index=False)

    else:
        return False

    return output


class CommandHandler(http.server.SimpleHTTPRequestHandler):
    cache = {}
    cache_lock = threading.Lock()  # Create a lock for cache operations


    @classmethod
    def load_cache(cls):
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as file:
                cls.cache = json.load(file)
                # Convert the saved timestamps back to datetime objects
                for key, value in cls.cache.items():
                    value['time'] = datetime.fromisoformat(value['time'])


    @classmethod
    def save_cache(cls):
        with cls.cache_lock:
            # Convert datetime objects to string for JSON serialization
            temp_cache = {key: {'time': value['time'].isoformat()} for key, value in cls.cache.items()}
            with open(CACHE_FILE, 'w') as file:
                json.dump(temp_cache, file)


    def do_GET(self):
        with self.cache_lock: # Lock the cache for reading

            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query = parsed_url.query
            query_params = parse_qs(query)

            if path in CACHE_PATHS_TO_SKIP:
                return

            current_time = datetime.now()
            hash_key = get_hash_key(path, query_params)
            file_name = f"cache_{hash_key}.csv"
            last_req_file = f"last_{hash_key}.json"  # JSON file to store request parameters

            try:
                # Check if the cache is fresh
                #if hash_key in self.cache and (current_time - self.cache[hash_key]['time'] <= CACHE_DURATION):
                if hash_key in self.cache:
                    print(f"Loading from cache for {path}")
                    with open(file_name, 'r', encoding='utf-8', errors='replace') as file:
                        output = file.read()
                        if not output.strip():
                            raise ValueError("Cache file is empty or invalid")  # Treat empty cache as an error
                else:
                    raise ValueError("Cache is outdated or does not exist")  # Force a cache refresh if outdated or missing
            except (IOError, ValueError) as e:
                # Handle any kind of error by refreshing data
                print(f"Cache miss or error ({e}): Refreshing data for {path}")
                output = handle_request(path, query_params)

                if output:
                    self.cache[hash_key] = {'time': current_time}
                    with open(file_name, 'w', encoding='utf-8', errors='replace') as file:
                        file.write(output)
                    with open(last_req_file, 'w') as file:
                        json.dump({'path': path, 'query_params': query_params}, file)  # Save the parameters

                else:
                    self.send_response(404)
                    return


            # Send response
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(output.encode())

            pass

        self.save_cache()


def continuously_update_cache():
    while True:
       
        try:
            last_files = [f for f in os.listdir('.') if f.startswith('last_')]
            for last_file in last_files:

                with open(last_file, 'r') as file:
                    data = json.load(file)                
                path = data['path']
                query_params = data['query_params']                             
                
                current_time = datetime.now()
                hash_key = get_hash_key(path, query_params)
                file_name = f"cache_{hash_key}.csv"

                # Determine cache file state
                cached_but_aged = hash_key in CommandHandler.cache and (current_time - CommandHandler.cache[hash_key]['time'] > CACHE_DURATION)
                cache_file_issue = not os.path.exists(file_name) or os.path.getsize(file_name) == 0

                if cached_but_aged or cache_file_issue:
                    with CommandHandler.cache_lock:  # Lock the cache for writing
                        print(f"Refreshing cache for {path}")
                        output = handle_request(path, query_params)  

                        
                        with open(file_name, 'w', encoding='utf-8', errors='replace') as file:
                            file.write(output)
                        CommandHandler.cache[hash_key] = {'time': current_time}
                        
                        CommandHandler.save_cache()
                        pass
                    
        except Exception as e:
            print(f"Error updating cache: {e}")        
        
        time.sleep(CACHE_KEEP_ALIVE_INTERVAL)            


if __name__ == "__main__":
    CommandHandler.load_cache()
    threading.Thread(target=continuously_update_cache, daemon=True).start()
    with Server(("", PORT), CommandHandler) as httpd:
        print(f"Serving at port {PORT}")
        httpd.serve_forever()