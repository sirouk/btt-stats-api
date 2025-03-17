#!/usr/bin/env python3
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import pexpect
import re
import subprocess
subprocess.run(["python3", "-m", "pip", "install", "pandas"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
import pandas as pd
from io import StringIO
import bittensor as bt
from datetime import datetime, timedelta
import os
import hashlib
import threading
import time
import json
import portalocker
import requests
from dotenv import load_dotenv
import logging
import argparse
from utils.google_sheets import update_google_sheet, check_auth

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('btt_to_sheets.log')
    ]
)
logger = logging.getLogger('btt_to_sheets')

# Constants
BLOCK_TIME = 12
subtensor_address = "127.0.0.1:9944"
HOTKEYS = os.getenv('HOTKEYS', '').split(',')

# Load environment variables
load_dotenv()

def clean_chars(str_data):
    """Clean ANSI escape characters from string output"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|τ')
    return ansi_escape.sub('', str_data)

def trim_output_from_pattern(output, start_pattern):
    """Trim output to start from a specific pattern"""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if len(start_pattern) > 0 and line.strip()[:len(start_pattern)] == start_pattern:
            return '\n'.join(lines[i:])
    return ''

def prettify_time(seconds):
    """Convert seconds to a pretty time format"""
    delta = timedelta(seconds=seconds)
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = f"{days:02}d:{hours:02}h:{minutes:02}m"
    return time_str

def get_subnet_weight(subnet_id, subtensor):
    """Get the emission weight for a subnet"""
    return float(subtensor.get_emission_value_by_subnet(netuid=subnet_id))

def get_wallet_balance_data():
    """Get wallet balance information"""
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
        # Keep only lines that start with 'coldkey-' and have balance data
        if line.strip().startswith('coldkey-'):
            # Clean up the line and extract data
            parts = [p for p in line.strip().split() if p]
            if len(parts) >= 3:  # We need at least wallet name, address, and balance
                wallet_name = parts[0]
                coldkey = parts[1]
                # Convert balance to float, removing any τ symbol
                free_balance = float(parts[-1].replace('τ', '').strip())
                staked_balance = 0.0  # Set staked balance to 0
                total_balance = free_balance  # Total is same as free balance since staked is 0
                data_lines.append([wallet_name, coldkey, free_balance, staked_balance, total_balance])

    # Create DataFrame from the cleaned data
    df = pd.DataFrame(data_lines, columns=['Wallet_Name', 'Coldkey_Address', 'Free_Balance', 'Staked_Balance', 'Total_Balance'])
    return df

def get_subnet_list_data():
    """Get subnet list information"""
    try:
        # Import this function from the module
        from utils.subnet_info import get_subnet_info
        
        # Get subnet info
        df = get_subnet_info(subtensor_address)
        if df is not None and not df.empty:
            return df
        else:
            logger.error("No subnet data returned")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"Error getting subnet info: {e}")
        return pd.DataFrame()

def get_metagraph_data(netuids, egrep_keys=None):
    """Get metagraph information for specified subnet IDs"""
    if not netuids:
        return pd.DataFrame()
        
    if isinstance(netuids, str):
        netuids = netuids.split(',')
        
    if egrep_keys is None:
        egrep_keys = []
    
    sanitized_egrep_keys = [re.escape(key) for key in egrep_keys if re.match(r'^[a-zA-Z0-9]+$', key)]
    pattern = "|".join(sanitized_egrep_keys)

    # Initialize subtensor connection
    subtensor = None
    try:
        subtensor = bt.subtensor(network=f"ws://{subtensor_address}")
        current_block = subtensor.get_current_block()
    except Exception as e:
        logger.error(f"Error connecting to subtensor network: {e}")
        return pd.DataFrame()

    resulting_lines = []  # Initialize outside the loop

    try:
        for netuid in netuids:
            netuid = netuid.strip()  # Remove any leading/trailing whitespace
            if re.match(r'^\d+$', netuid):
                netuid_int = int(netuid)
                try:
                    metagraph = subtensor.metagraph(netuid=netuid_int)
                    
                    # Calculate daily rewards using new formula
                    # emissions is alpha per 360 blocks, so calculate daily earnings
                    daily_blocks = (60 * 60 * 24) / BLOCK_TIME  # Number of blocks per day
                    tempo_multiplier = daily_blocks / metagraph.tempo
                    
                    # Get pool info for alpha token price
                    pool = metagraph.pool
                    alpha_token_price = pool.tao_in / pool.alpha_in
                    
                except Exception as e:
                    logger.error(f"Error fetching metagraph for netuid {netuid}: {e}")
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
                    'DAILY_REWARDS_ALPHA': [float(emission * tempo_multiplier) for emission in metagraph.emission],
                    'DAILY_REWARDS_TAO': [float(emission * tempo_multiplier * alpha_token_price) for emission in metagraph.emission]
                }
                
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
                            logger.error(f"Error processing UID {uid}: {e}")
                            netuid_lines.at[index, 'IMMUNE'] = ''  # Empty string for errors
                    else:
                        # Drop the row if the UID does not match the pattern or is invalid
                        netuid_lines.drop(index, inplace=True)

                # Append the processed netuid_lines to resulting_lines
                if not netuid_lines.empty:
                    resulting_lines.append(netuid_lines)
            else:
                logger.error(f"Invalid netuid format: {netuid}")
                continue  # Skip invalid netuid

        if resulting_lines:
            # Concatenate all DataFrames in the list
            try:
                df = pd.concat(resulting_lines, ignore_index=True)
                return df
            except Exception as e:
                logger.error(f"Error concatenating DataFrames: {e}")
                return pd.DataFrame()
        else:
            return pd.DataFrame()
    finally:
        if subtensor and hasattr(subtensor, 'close'):
            try:
                subtensor.close()
            except:
                pass  # Ignore any errors during close

def get_registrations_data():
    """Get registration information"""
    unique_entries = []
    log_pattern = re.compile(r'btt_register_sn(\d+)_ck(\d+)-hk(\d+)(?:_\d{4}-\d{2}-\d{2})?\.log')
    log_directory = os.path.expanduser("~/logs/bittensor")
    timestamp_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| \{Attempting SN registration')
    
    # Calculate the cutoff date for log files (90 days ago)
    cutoff_date = datetime.now() - timedelta(days=90)

    # Check if the directory exists before trying to read it
    if not os.path.exists(log_directory):
        logger.error(f"Log directory does not exist: {log_directory}")
        return pd.DataFrame()
    
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
                            cost_match = re.search(r'τ\s*([\d.]+)', lines[j])
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

    if not unique_entries:
        return pd.DataFrame()
        
    df = pd.DataFrame(unique_entries)  # Create DataFrame directly from the list of dictionaries
    df = df.sort_values(by=['Timestamp', 'Subnet', 'ColdKey', 'HotKey', 'Line'], ascending=[False, True, True, True, False])
    return df

def get_sn19_metrics_data(fetch_file_date, date_from, date_to, data_source):
    """Get SN19 metrics data"""
    # Construct the URL to fetch the CSV file
    csv_url = f"https://data.tauvision.ai/{fetch_file_date}_{data_source}.csv"
    logger.info(f"Fetching CSV from: {csv_url}")

    # Fetch the CSV file from the URL
    try:
        response = requests.get(csv_url + f"?r={int(time.time())}")
        response.raise_for_status()  # Raise an error for bad status codes
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching CSV: {e}")
        return pd.DataFrame()

    # Read the CSV data into a DataFrame
    csv_data = response.content.decode('utf-8')
    df = pd.read_csv(StringIO(csv_data))

    # Convert date strings to datetime objects
    try:
        date_from = datetime.strptime(date_from, '%Y-%m-%d')
        date_to = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1) - timedelta(microseconds=1)
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return pd.DataFrame()

    # Ensure the 'created_at' column is parsed as datetime
    df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')

    # Filter the DataFrame by the date range
    filtered_df = df[(df['created_at'] >= date_from) & (df['created_at'] <= date_to)]

    # Filter the DataFrame to include only the specified hotkeys
    filtered_df = filtered_df[filtered_df['miner_hotkey'].isin(HOTKEYS)]

    # Select only the required columns
    columns = ['id', 'axon_uid', 'miner_hotkey', 'validator_hotkey', 'task', 'declared_volume', 'consumed_volume', 
               'total_requests_made', 'requests_429', 'requests_500', 'period_score', 'created_at']
    filtered_df = filtered_df[columns]
    
    return filtered_df

def get_sn19_recent_data(hist_hours=72):
    """Get recent SN19 data"""
    skip = 0
    limit = 2500
    all_data = []
    oldest_date = datetime.now()
    target_date = oldest_date - timedelta(hours=int(hist_hours))
    
    while oldest_date > target_date:
        url = f"https://tauvision.ai/api/get-reward-data?skip={skip}&limit={limit}&sort_by=created_at&sort_order=desc"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            all_data.extend(data)
            oldest_date = datetime.fromisoformat(data[-1]['created_at'].replace('Z', '+00:00'))
            skip += limit
            time.sleep(1)  # To avoid hitting rate limits
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching SN19 recent data: {e}")
            break
    
    # Process the collected data
    if not all_data:
        return pd.DataFrame()
        
    date_to = datetime.now()
    date_from = date_to - timedelta(hours=int(hist_hours))
    df = pd.DataFrame(all_data)
    df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
    filtered_df = df[(df['created_at'] >= date_from) & (df['created_at'] <= date_to)]
    
    return filtered_df

def update_all_sheets(config):
    """Update all Google Sheets with data from various sources"""
    results = {}
    
    for task_name, task_config in config.items():
        logger.info(f"Processing task: {task_name}")
        
        spreadsheet_id = task_config.get('spreadsheet_id')
        sheet_name = task_config.get('sheet_name')
        start_cell = task_config.get('start_cell', 'A1')
        
        if not spreadsheet_id or not sheet_name:
            logger.error(f"Missing spreadsheet_id or sheet_name for {task_name}")
            results[task_name] = False
            continue
            
        data_type = task_config.get('data_type')
        params = task_config.get('params', {})
        
        try:
            # Get data based on type
            df = None
            
            if data_type == 'wallet_balance':
                df = get_wallet_balance_data()
                
            elif data_type == 'subnet_list':
                df = get_subnet_list_data()
                
            elif data_type == 'metagraph':
                netuids = params.get('netuid', '').split(',')
                egrep_keys = params.get('egrep', [])
                df = get_metagraph_data(netuids, egrep_keys)
                
            elif data_type == 'registrations':
                df = get_registrations_data()
                
            elif data_type == 'sn19_metrics':
                fetch_file_date = params.get('fetchFileDate')
                date_from = params.get('dateFrom')
                date_to = params.get('dateTo')
                data_source = params.get('dataSource')
                if all([fetch_file_date, date_from, date_to, data_source]):
                    df = get_sn19_metrics_data(fetch_file_date, date_from, date_to, data_source)
                else:
                    logger.error(f"Missing required parameters for sn19_metrics")
                    results[task_name] = False
                    continue
                    
            elif data_type == 'sn19_recent':
                hist_hours = params.get('hours', 72)
                df = get_sn19_recent_data(hist_hours)
                
            else:
                logger.error(f"Unknown data type: {data_type}")
                results[task_name] = False
                continue
                
            # Check if we got valid data
            if df is None or df.empty:
                logger.error(f"No data returned for {task_name}")
                results[task_name] = False
                continue
                
            # Update Google Sheet
            update_google_sheet(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                df=df,
                start_cell=start_cell,
                include_header=task_config.get('include_header', True),
                handle_existing_filters=task_config.get('handle_existing_filters', False)
            )
            
            logger.info(f"Successfully updated {task_name}")
            results[task_name] = True
            
        except Exception as e:
            logger.error(f"Error processing {task_name}: {e}", exc_info=True)
            results[task_name] = False
            
    return results

def main():
    """Main function to run the script"""
    parser = argparse.ArgumentParser(description='Update Google Sheets with Bittensor data')
    parser.add_argument('--config', type=str, default='.sheets_config.json', help='Path to configuration file')
    parser.add_argument('--check-auth', action='store_true', help='Check Google Sheets authentication')
    args = parser.parse_args()
    
    # Check authentication if requested
    if args.check_auth:
        if check_auth():
            logger.info("Google Sheets authentication successful!")
            return 0
        else:
            logger.error("Google Sheets authentication failed!")
            return 1
    
    # Load configuration
    try:
        with open(args.config, 'r') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading configuration: {e}")
        logger.info("Creating example configuration file...")
        
        # Create example configuration
        example_config = {
            "wallet_balance": {
                "data_type": "wallet_balance",
                "spreadsheet_id": "YOUR_SPREADSHEET_ID",
                "sheet_name": "WalletBalance",
                "start_cell": "A1",
                "include_header": True,
                "handle_existing_filters": False,
                "params": {}
            },
            "subnet_list": {
                "data_type": "subnet_list",
                "spreadsheet_id": "YOUR_SPREADSHEET_ID",
                "sheet_name": "SubnetList",
                "start_cell": "A1",
                "include_header": True,
                "params": {}
            },
            "metagraph_sn1": {
                "data_type": "metagraph",
                "spreadsheet_id": "YOUR_SPREADSHEET_ID",
                "sheet_name": "Metagraph_SN1",
                "start_cell": "A1",
                "include_header": True,
                "params": {
                    "netuid": "1",
                    "egrep": []
                }
            }
        }
        
        with open(args.config, 'w') as f:
            json.dump(example_config, f, indent=2)
            
        logger.info(f"Example configuration created at {args.config}")
        logger.info("Please edit this file with your Google Sheets information and run again.")
        return 1
    
    # Update all sheets
    results = update_all_sheets(config)
    
    # Check results
    success = all(results.values())
    if success:
        logger.info("All sheets updated successfully!")
    else:
        logger.warning(f"Some sheets failed to update: {results}")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main()) 