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
subprocess.run(["python3", "-m", "pip", "install", "portalocker"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) # Ensure pandas is installed
import portalocker
import requests
from dotenv import load_dotenv
from subnet_info import get_subnet_info


BLOCK_TIME = 12
PORT = 41337
subtensor_address = "127.0.0.1:9944"
CACHE_DURATION = timedelta(minutes=3)  # Cache freshness duration
CACHE_KEEP_ALIVE_INTERVAL = 10  # Cache check interval in seconds, adjusted here
CACHE_FILE = "cache_state.json"
PATHS_TO_SKIP = {'/favicon.ico'} # avoid these paths
CACHE_DISABLED_PATHS = ['/sn19_metrics','/sn19_recent']  # Paths with caching disabled

# Load environment variables
load_dotenv()

# Get hotkeys from environment variable
HOTKEYS = os.getenv('HOTKEYS', '').split(',')


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


def prettify_time(seconds):
    delta = timedelta(seconds=seconds)
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = f"{days:02}d:{hours:02}h:{minutes:02}m"
    return time_str

def get_subnet_weight(subnet_id, subtensor):
    return float(subtensor.get_emission_value_by_subnet(netuid=subnet_id))


def handle_request(path, query_params):
    #print(path)
    #quit()

    output = ""

    if path == '/wallet-balance':
        # Run the subnet list command
        command = f"/usr/local/bin/btcli w balance --all --subtensor.network finney --wallet-path ~/.bittensor/wallets/ --subtensor.chain_endpoint ws://{subtensor_address}"
        child = pexpect.spawn(command, dimensions=(500, 500))
        child.expect(pexpect.EOF)
        cmd_output = child.before.decode(errors='ignore')
        cmd_output = clean_chars(cmd_output)
        
        # Find the section starting with the balance table
        cmd_output = trim_output_from_pattern(cmd_output, "Wallet Coldkey Balance")
        
        # Split into lines and filter out header lines and separator lines
        lines = cmd_output.splitlines()
        data_lines = []
        for line in lines:
            # Skip empty lines, headers, and separator lines
            if not line.strip() or 'Network:' in line or 'Wallet Name' in line or '━' in line or 'Total Balance' in line:
                continue
            # Keep only lines that start with 'coldkey-' or have actual balance data
            if line.strip().startswith('coldkey-'):
                data_lines.append(line)

        # Join the filtered lines back together
        cmd_output = '\n'.join(data_lines)
        
        # Parse into DataFrame
        string_io_obj = StringIO(cmd_output)
        df = pd.read_fwf(string_io_obj, colspecs='infer')
        
        print("Initial DataFrame:")
        print(df.head())
        print("\nColumn types:")
        print(df.dtypes)
        
        # Clean up column names if needed
        if not df.empty:
            df.columns = ['Wallet_Name', 'Coldkey_Address', 'Free_Balance', 'Staked_Balance', 'Total_Balance']
            
            # Convert all columns to string first
            for col in df.columns:
                df[col] = df[col].astype(str)
            
            # Remove the 'τ' symbol from balance columns and convert to numeric
            for col in ['Free_Balance', 'Staked_Balance', 'Total_Balance']:
                df[col] = df[col].str.replace('τ', '').str.strip()
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            print("\nFinal DataFrame:")
            print(df.head())
            print("\nFinal column types:")
            print(df.dtypes)

        output += df.to_csv(index=False)


    elif path == '/subnet-list':
        try:
            # Get subnet info using the updated method
            df = get_subnet_info(subtensor_address)
            if df is not None and not df.empty:
                output += df.to_csv(index=False)
                return output
            else:
                print("No subnet data returned")
                return "No subnet data available"
        except Exception as e:
            print(f"Error getting subnet info: {e}")
            return f"Error getting subnet info: {e}"


    elif path == '/metagraph':
        netuids = query_params.get('netuid', [''])[0].split(',')
        sanitized_egrep_keys = [re.escape(key) for key in query_params.get('egrep', []) if re.match(r'^[a-zA-Z0-9]+$', key)]
        pattern = "|".join(sanitized_egrep_keys)

        # Initialize subtensor connection
        subtensor = None
        try:
            subtensor = bt.subtensor(network=f"ws://{subtensor_address}")
            current_block = subtensor.get_current_block()
        except Exception as e:
            print(f"Error connecting to subtensor network: {e}")
            return "Connection Error"

        resulting_lines = []  # Initialize outside the loop

        try:
            for netuid in netuids:
                netuid = netuid.strip()  # Remove any leading/trailing whitespace
                if re.match(r'^\d+$', netuid):
                    netuid_int = int(netuid)
                    try:
                        metagraph = subtensor.metagraph(netuid=netuid_int)
                        
                        # Calculate tempo and daily rewards
                        tempo_blocks: int = metagraph.tempo
                        tempo_seconds: int = tempo_blocks * BLOCK_TIME
                        seconds_in_day: int = 60 * 60 * 24
                        tempos_per_day: int = int(seconds_in_day / tempo_seconds)
                        
                        # Get pool info for alpha token price
                        pool = metagraph.pool
                        alpha_token_price = pool.tao_in / pool.alpha_in
                        
                    except Exception as e:
                        print(f"Error fetching metagraph for netuid {netuid}: {e}")
                        continue  # Skip to the next netuid

                    # Extract the first AxonInfo entry
                    axon_ip, axon_port = None, None
                    if metagraph.axons and len(metagraph.axons) > 0:
                        first_axon = metagraph.axons[0]
                        if hasattr(first_axon, 'ip') and hasattr(first_axon, 'port'):
                            axon_ip = first_axon.ip
                            axon_port = first_axon.port

                    # First get the length of uids for validation
                    n_uids = len(metagraph.uids)
                    
                    data = {
                        'SUBNET': [netuid_int] * n_uids,  # Repeat subnet for each UID
                        'UID': metagraph.uids,
                        'STAKE': metagraph.stake,
                        'RANK': metagraph.ranks,
                        'TRUST': metagraph.trust,
                        'CONSENSUS': metagraph.consensus,
                        'INCENTIVE': metagraph.incentive,
                        'DIVIDENDS': metagraph.dividends,
                        'EMISSION': metagraph.emission,
                        'VTRUST': metagraph.validator_trust,
                        'VPERMIT': metagraph.validator_permit,
                        'UPDATED': metagraph.last_update,
                        'ACTIVE': metagraph.active,
                        'AXON': [f"{axon.ip}:{axon.port}" for axon in metagraph.axons[:n_uids]],  # Ensure same length as uids
                        'HOTKEY': metagraph.hotkeys,
                        'COLDKEY': metagraph.coldkeys,
                        'IMMUNE': ['' for _ in range(n_uids)], # empty list of strings
                        'ALPHA_STAKE': metagraph.alpha_stake,
                        'TAO_STAKE': metagraph.tao_stake,
                        'DAILY_REWARDS_ALPHA': [float(tempos_per_day * emission) for emission in metagraph.emission],
                        'DAILY_REWARDS_TAO': [float(tempos_per_day * emission * alpha_token_price) for emission in metagraph.emission]
                    }
                    
                    # Debug print lengths
                    print(f"Processing netuid: {netuid_int}")
                    print("Array lengths:")
                    for key, value in data.items():
                        print(f"{key}: {len(value) if hasattr(value, '__len__') else 1}")
                    
                    # Convert the dictionary to a DataFrame
                    netuid_lines = pd.DataFrame(data)
                    
                    # Format numeric columns
                    numeric_columns = ['STAKE', 'RANK', 'TRUST', 'CONSENSUS', 'INCENTIVE', 'DIVIDENDS', 'EMISSION', 'VTRUST', 'DAILY_REWARDS_ALPHA', 'DAILY_REWARDS_TAO']
                    for col in numeric_columns:
                        if col in netuid_lines.columns:
                            netuid_lines[col] = netuid_lines[col].apply(lambda x: f"{float(x):.8f}" if pd.notnull(x) else x)

                    # Format boolean columns
                    boolean_columns = ['ACTIVE', 'VPERMIT']
                    for col in boolean_columns:
                        if col in netuid_lines.columns:
                            netuid_lines[col] = netuid_lines[col].astype(bool)

                    # Process each row
                    for index, row in netuid_lines.iterrows():
                        uid = str(row['UID'])

                        # Apply regex search on uid or other fields as needed
                        if uid and (re.search(pattern, str(row)) or (not sanitized_egrep_keys)):
                            try:
                                block_at_registration = subtensor.query_subtensor("BlockAtRegistration", None, [netuid_int, uid])
                                # Extract the value from BittensorScaleType
                                if hasattr(block_at_registration, 'value'):
                                    block_at_registration = block_at_registration.value
                                else:
                                    block_at_registration = int(str(block_at_registration))
                                    
                                immune_until = block_at_registration + subtensor.immunity_period(netuid=netuid_int)
                                immune = immune_until > current_block

                                # Update the DataFrame by adding the immune status
                                netuid_lines.at[index, 'IMMUNE'] = immune_until if immune else ''
                            except Exception as e:
                                print(f"Error processing UID {uid}: {e}")
                                netuid_lines.at[index, 'IMMUNE'] = ''  # Empty string for errors
                        else:
                            # Drop the row if the UID does not match the pattern or is invalid
                            netuid_lines.drop(index, inplace=True)

                    # Append the processed netuid_lines to resulting_lines
                    if not netuid_lines.empty:
                        resulting_lines.append(netuid_lines)
                else:
                    print(f"Invalid netuid format: {netuid}")
                    continue  # Skip invalid netuid

            if resulting_lines:
                # Concatenate all DataFrames in the list
                try:
                    df = pd.concat(resulting_lines, ignore_index=True)
                    # Convert DataFrame to CSV string
                    output += df.to_csv(index=False)
                except Exception as e:
                    print(f"Error concatenating DataFrames: {e}")
        finally:
            if subtensor and hasattr(subtensor, 'close'):
                try:
                    subtensor.close()
                except:
                    pass  # Ignore any errors during close


    elif path == '/registrations':

        unique_entries = []
        log_pattern = re.compile(r'btt_register_sn(\d+)_ck(\d+)-hk(\d+)(?:_\d{4}-\d{2}-\d{2})?\.log')
        log_directory = os.path.expanduser("~/logs/bittensor")
        timestamp_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| \{Attempting SN registration')
        
        # Calculate the cutoff date for log files (90 days ago)
        cutoff_date = datetime.now() - timedelta(days=90)
    
        for filename in os.listdir(log_directory):
            match = log_pattern.match(filename)
            if match:
                subnet, coldkey, hotkey = match.groups()
                filepath = os.path.join(log_directory, filename)
                
                # Skip files modified before the cutoff date
                file_stats = os.stat(filepath)
                modified_time = datetime.fromtimestamp(file_stats.st_mtime)
                if modified_time < cutoff_date:
                    continue  # Skip this file
                
                with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                    lines = file.readlines()
                    
                #cleaned_lines = [ansi_escape.sub('', line) for line in lines]

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
                            if "The cost to register by recycle is" in lines[j]:
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


    elif path == '/sn19_metrics':
        
        # Parse URL parameters
        fetch_file_date = query_params.get('fetchFileDate', [None])[0]
        date_from = query_params.get('dateFrom', [None])[0]
        date_to = query_params.get('dateTo', [None])[0]
        data_source = query_params.get('dataSource', [None])[0]
    
        # Construct the URL to fetch the CSV file
        csv_url = f"https://data.tauvision.ai/{fetch_file_date}_{data_source}.csv"
        print(f"Fetching CSV from: {csv_url}")
    
        # Fetch the CSV file from the URL
        try:
            response = requests.get(csv_url + f"?r={int(time.time())}")
            response.raise_for_status()  # Raise an error for bad status codes
        except requests.exceptions.RequestException as e:
            return f"Error fetching CSV: {e}"
    
        # Read the CSV data into a DataFrame
        csv_data = response.content.decode('utf-8')
        df = pd.read_csv(StringIO(csv_data))
    
        # Print the top and bottom of the DataFrame for debugging
        print("Top of the DataFrame:")
        print(df.head())
        print("Bottom of the DataFrame:")
        print(df.tail())
    
        # Convert date strings to datetime objects
        date_from = datetime.strptime(date_from, '%Y-%m-%d')
        date_to = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1) - timedelta(microseconds=1)
    
        # Ensure the 'created_at' column is parsed as datetime
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
    
        # Print the DataFrame after parsing dates for debugging
        print("DataFrame after parsing 'created_at' as datetime:")
        print(df.head())
    
        # Debug: Print date range and min/max of created_at
        print(f"Filtering from {date_from} to {date_to}")
        print(f"Min created_at: {df['created_at'].min()}")
        print(f"Max created_at: {df['created_at'].max()}")
    
        # Filter the DataFrame by the date range
        filtered_df = df[(df['created_at'] >= date_from) & (df['created_at'] <= date_to)]
    
        # Filter the DataFrame to include only the specified hotkeys
        filtered_df = filtered_df[filtered_df['miner_hotkey'].isin(HOTKEYS)]
    
        # Print the filtered DataFrame for debugging
        print("Filtered DataFrame:")
        print(filtered_df.head())
        print("Filtered DataFrame Bottom:")
        print(filtered_df.tail())
    
        # Select only the required columns
        columns = ['id', 'axon_uid', 'miner_hotkey', 'validator_hotkey', 'task', 'declared_volume', 'consumed_volume', 
                   'total_requests_made', 'requests_429', 'requests_500', 'period_score', 'created_at']
        filtered_df = filtered_df[columns]
    
        # Convert the filtered DataFrame back to CSV format
        filtered_csv = filtered_df.to_csv(index=False)


        output += filtered_csv
        

    elif path == '/sn19_recent':

        hist_hours = query_params.get('hours', 72)[0]
        
        skip = 0
        limit = 2500
        all_data = []
        oldest_date = datetime.now()
        target_date = oldest_date - timedelta(hours=int(hist_hours))
        
        while oldest_date > target_date:
            url = f"https://tauvision.ai/api/get-reward-data?skip={skip}&limit={limit}&sort_by=created_at&sort_order=desc"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            all_data.extend(data)
            oldest_date = datetime.fromisoformat(data[-1]['created_at'].replace('Z', '+00:00'))
            skip += limit
            time.sleep(1)  # To avoid hitting rate limits
        
        # Process the collected data
        date_to = datetime.now()
        date_from = date_to - timedelta(hours=int(hist_hours))
        df = pd.DataFrame(all_data)
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
        filtered_df = df[(df['created_at'] >= date_from) & (df['created_at'] <= date_to)]
        
        # Print debug information
        print("Top of the DataFrame:")
        print(filtered_df.head())
        print("Bottom of the DataFrame:")
        print(filtered_df.tail())
        print(f"Filtering from {date_from} to {date_to}")
        print(f"Min created_at: {filtered_df['created_at'].min()}")
        print(f"Max created_at: {filtered_df['created_at'].max()}")
        
        # Convert the filtered DataFrame back to CSV format
        filtered_csv = filtered_df.to_csv(index=False)
        print("Filtered CSV (first 500 characters):")
        print(filtered_csv[:500])
        
        # Instead of returning, you can assign the result to a variable or process it further as needed
        output += filtered_csv


    else:
        return False


    return output


class CommandHandler(http.server.SimpleHTTPRequestHandler):

    @staticmethod
    def get_file_lock(file_name, mode='r+'):
        # Open the file directly in the desired mode
        file = open(file_name, mode, encoding='utf-8', errors='replace')
        # Lock the file with portalocker
        portalocker.lock(file, portalocker.LOCK_EX)
        return file


    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parsed_url.query
        query_params = parse_qs(query)


        # Bypass caching for any specified paths
        if path in CACHE_DISABLED_PATHS:
            output = handle_request(path, query_params)
            if output:
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(output.encode())
            else:
                self.send_response(404)
            return

        if path in PATHS_TO_SKIP:
            return
        

        # Handle w/cache
        current_time = datetime.now()
        hash_key = get_hash_key(path, query_params)
        file_name = f"cache_{hash_key}.csv"
        last_req_file = f"last_{hash_key}.json"

        try:
            # Use a context manager to handle the file with the lock
            with self.get_file_lock(file_name, 'r+') as file:
                output = file.read()
                if not output.strip() or (current_time - datetime.fromtimestamp(os.path.getmtime(file_name))) > CACHE_DURATION:
                    raise ValueError("Cache is outdated or invalid")
        except (IOError, ValueError):
            print(f"Cache for {path} is outdated or invalid, updating...")
            output = handle_request(path, query_params)
            with self.get_file_lock(file_name, 'w') as file:
                file.write(output)
                file.truncate()
            with open(last_req_file, 'w', encoding='utf-8', errors='replace') as file:
                json.dump({'path': path, 'query_params': query_params}, file)

        if output:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(output.encode())
        else:
            self.send_response(404)


def refresh_cache_file(path, query_params, file_name):
    output = handle_request(path, query_params)
    try:
        with CommandHandler.get_file_lock(file_name, 'w') as file:
            file.write(output)
            file.truncate()  # Ensure to clear any excess if new output is shorter
    except IOError as e:
        print(f"Error writing to cache file {file_name}: {e}")


def continuously_update_cache():
    while True:
        try:
            last_files = [f for f in os.listdir('.') if f.startswith('last_')]
            for last_file in last_files:
                with open(last_file, 'r', encoding='utf-8', errors='replace') as file:
                    data = json.load(file)
                
                path = data['path']
                query_params = data['query_params']
                hash_key = get_hash_key(path, query_params)
                file_name = f"cache_{hash_key}.csv"

                try:
                    # Check if the file exists and its modification time
                    if os.path.exists(file_name):
                        file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_name))
                        current_time = datetime.now()

                        # Update cache if it is outdated
                        if (current_time - file_mod_time) > CACHE_DURATION:
                            print(f"Cache for {path} is outdated, refreshing...")
                            refresh_cache_file(path, query_params, file_name)
                        else:
                            print(f"Cache for {path} is still fresh, skipping...")
                    else:
                        # If the file does not exist, regenerate it
                        print(f"Cache file {file_name} not found, generating new cache...")
                        refresh_cache_file(path, query_params, file_name)
                except Exception as e:
                    print(f"Failed to update cache for {path}: {e}")

        except Exception as e:
            print(f"Error during cache update loop: {e}")
        time.sleep(CACHE_KEEP_ALIVE_INTERVAL)


if __name__ == "__main__":
    threading.Thread(target=continuously_update_cache, daemon=True).start()
    with Server(("", PORT), CommandHandler) as httpd:
        print(f"Serving at port {PORT}")
        httpd.serve_forever()
