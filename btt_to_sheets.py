#!/usr/bin/env python3
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
import time
import json
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
#subtensor_address = "ws://127.0.0.1:9944"
subtensor_address = "wss://entrypoint-finney.opentensor.ai:443"
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
    command = f"/usr/local/bin/btcli w balance --all --subtensor.network finney --wallet-path ~/.bittensor/wallets/ --subtensor.chain_endpoint {subtensor_address}"
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
        logger.error("No netuids provided")
        return pd.DataFrame()
        
    if isinstance(netuids, str):
        netuids = netuids.split(',')
        
    if egrep_keys is None:
        egrep_keys = []
    
    logger.info(f"Processing netuids: {netuids}")
    sanitized_egrep_keys = [re.escape(key) for key in egrep_keys if re.match(r'^[a-zA-Z0-9]+$', key)]
    pattern = "|".join(sanitized_egrep_keys)
    logger.info(f"Using pattern: {pattern[:100]}..." if len(pattern) > 100 else f"Using pattern: {pattern}")

    # Initialize subtensor connection
    subtensor = None
    try:
        logger.info(f"Connecting to subtensor at {subtensor_address}")
        subtensor = bt.subtensor(network=f"{subtensor_address}")
        current_block = subtensor.get_current_block()
        logger.info(f"Connected to subtensor, current block: {current_block}")
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
                    logger.info(f"Fetching metagraph for netuid {netuid_int}")
                    metagraph = subtensor.metagraph(netuid=netuid_int)
                    logger.info(f"Metagraph for netuid {netuid_int} has {len(metagraph.uids)} UIDs")
                    
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

def get_sn19_metrics_data(fetch_file_date, date_from, date_to, data_source, egrep_keys=None):
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

    # Determine which hotkeys to use
    hotkeys_to_use = egrep_keys if egrep_keys else HOTKEYS
    
    # Convert to list if it's a string
    if isinstance(hotkeys_to_use, str):
        hotkeys_to_use = hotkeys_to_use.split(',')
        
    logger.info(f"Filtering SN19 metrics by {len(hotkeys_to_use)} hotkeys")
    
    # Filter the DataFrame to include only the specified hotkeys
    filtered_df = filtered_df[filtered_df['miner_hotkey'].isin(hotkeys_to_use)]

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

def get_asset_price(symbol):
    """Get asset price from Kucoin API
    
    Args:
        symbol (str): Trading pair symbol, e.g., 'TAO-USDT'
        
    Returns:
        pandas.DataFrame: DataFrame with price data
    """
    try:
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}"
        logger.info(f"Fetching price data for {symbol} from: {url}")
        
        # Add a timestamp to prevent caching (use & for additional parameters)
        timestamp_param = f"&t={int(time.time())}"
        response = requests.get(url + timestamp_param)
        response.raise_for_status()
        
        # Check if response has content before parsing JSON
        if not response.content:
            logger.error(f"Empty response from Kucoin API for {symbol}")
            return pd.DataFrame()
            
        # Try to parse the JSON response
        try:
            data = response.json()
        except Exception as json_error:
            logger.error(f"Failed to parse JSON response: {json_error}, Response content: {response.content[:200]}")
            return pd.DataFrame()
            
        # Validate the response structure
        if not isinstance(data, dict):
            logger.error(f"Unexpected response format from Kucoin API: {type(data)}")
            return pd.DataFrame()
            
        if data.get('code') != '200000' or 'data' not in data:
            logger.error(f"Error response from Kucoin API: {data}")
            return pd.DataFrame()
            
        # Extract price from the response
        price_data = data.get('data', {})
        if not isinstance(price_data, dict):
            logger.error(f"Unexpected price data format: {type(price_data)}")
            return pd.DataFrame()
            
        price = price_data.get('price')
        
        if not price:
            logger.error(f"No price data found in response: {data}")
            return pd.DataFrame()
            
        # Create a DataFrame with a single column for the price
        df = pd.DataFrame([{'price': price}])
        logger.info(f"Retrieved price for {symbol}: {price}")
        
        return df
        
    except requests.exceptions.RequestException as req_error:
        logger.error(f"Request error fetching asset price for {symbol}: {req_error}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Error fetching asset price for {symbol}: {e}")
        return pd.DataFrame()

def update_all_sheets(config, task_name=None):
    """Update all Google Sheets with data from various sources
    
    Args:
        config: Dictionary with configuration for all tasks
        task_name: Optional string with task name to run exclusively
        
    Returns:
        Dictionary with task names as keys and boolean success values
    """
    results = {}
    
    # Filter configuration if specific task is requested
    if task_name:
        if task_name in config:
            config = {task_name: config[task_name]}
            logger.info(f"Running only task: {task_name}")
        else:
            logger.error(f"Task '{task_name}' not found in configuration!")
            return {task_name: False}
    
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
                netuids = params.get('netuids', '').split(',')
                egrep_keys = params.get('egrep_keys', [])
                # Split egrep_keys into a list if it's a comma-separated string
                if isinstance(egrep_keys, str):
                    egrep_keys = egrep_keys.split(',')
                logger.info(f"Calling get_metagraph_data with netuids={netuids}, egrep_keys length={len(egrep_keys)}")
                df = get_metagraph_data(netuids, egrep_keys)
                if df is None or df.empty:
                    logger.error(f"get_metagraph_data returned empty DataFrame with netuids={netuids}")
                
            elif data_type == 'registrations':
                df = get_registrations_data()
                
            elif data_type == 'sn19_metrics':
                fetch_file_date = params.get('fetchFileDate')
                date_from = params.get('dateFrom')
                date_to = params.get('dateTo')
                data_source = params.get('dataSource')
                if all([fetch_file_date, date_from, date_to, data_source]):
                    df = get_sn19_metrics_data(fetch_file_date, date_from, date_to, data_source, params.get('egrep_keys'))
                else:
                    logger.error(f"Missing required parameters for sn19_metrics")
                    results[task_name] = False
                    continue
                    
            elif data_type == 'sn19_recent':
                hist_hours = params.get('hours', 72)
                df = get_sn19_recent_data(hist_hours)
                
            elif data_type == 'asset_price':
                symbol = params.get('symbol')
                if symbol:
                    df = get_asset_price(symbol)
                else:
                    logger.error(f"Missing 'symbol' parameter for asset_price")
                    results[task_name] = False
                    continue
                
            else:
                logger.error(f"Unknown data type: {data_type}")
                results[task_name] = False
                continue
                
            # Check if we got valid data
            if df is None or df.empty:
                logger.error(f"No data returned for {task_name}")
                results[task_name] = False
                continue
                
            # Get formula configuration if present
            formula_config = task_config.get('formula', {})
            formula_text = formula_config.get('text')
            formula_position = formula_config.get('position', 0)
            formula_type = formula_config.get('type', 'formula')  # Default to formula type
            
            # Process formula based on type
            formula = None
            if formula_text:
                if formula_type == 'formula':
                    # Standard formula that will be applied as is
                    formula = formula_text
                elif formula_type == 'python':
                    # Python code to execute for each row
                    try:
                        # First, check if this is a simple formula that doesn't use row data
                        is_simple_formula = 'row' not in formula_text and 'df' not in formula_text and 'df_idx' not in formula_text
                        
                        # For simple formulas that don't reference row data (especially timestamps), 
                        # just evaluate once and use the same value for all rows
                        if is_simple_formula:
                            logger.info(f"Using simple Python formula evaluation for '{formula_text}'")
                            
                            # Set up globals with just datetime and timedelta
                            globals_dict = {
                                'datetime': datetime,
                                'timedelta': timedelta
                            }
                            
                            # Evaluate the formula once
                            result = eval(formula_text, globals_dict)
                            static_result = str(result)
                            
                            # Return a function that always returns this value
                            formula = lambda _: static_result
                        else:
                            # For more complex formulas that need row data, use the original approach
                            logger.info(f"Using row-dependent Python formula for '{formula_text}'")
                            
                            # Create a code object from the Python text
                            code = compile(formula_text, "<string>", "eval")
                            
                            # Determine if we should include the header when calculating row indices
                            include_header = task_config.get('include_header', True)
                            start_row = int(start_cell[1:]) if start_cell[1:].isdigit() else 1
                            
                            # Return a function that will be called for each row
                            def python_formula_wrapper(sheet_row):
                                try:
                                    # Calculate the DataFrame index from the local data position
                                    # In append mode with high row numbers, use a simple relative offset
                                    relative_idx = sheet_row - start_row
                                    if include_header and relative_idx > 0:
                                        relative_idx -= 1
                                        
                                    if relative_idx < 0 or relative_idx >= len(df):
                                        return f"ERROR: Index {relative_idx} out of bounds (max={len(df)-1})"
                                    
                                    # Get the data for this row
                                    row_data = df.iloc[relative_idx]
                                    
                                    # Set up the globals for the evaluation
                                    globals_dict = {
                                        'datetime': datetime,
                                        'timedelta': timedelta,
                                        'row': row_data,
                                        'idx': sheet_row,
                                        'df': df
                                    }
                                    
                                    # Execute the code with access to these globals
                                    result = eval(code, globals_dict)
                                    return str(result)
                                except Exception as e:
                                    logger.error(f"Error executing formula: {e}")
                                    return f"ERROR: {str(e)}"
                            
                            formula = python_formula_wrapper
                    except Exception as e:
                        logger.error(f"Error compiling Python formula: {e}")
                        formula = None
                else:
                    logger.warning(f"Unknown formula type: {formula_type}")
                    formula = None
            
            # Get append mode and max rows limit settings
            append_mode = task_config.get('append_mode', False)
            max_rows_limit = task_config.get('max_rows_limit')
            
            # Update Google Sheet
            update_google_sheet(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                df=df,
                start_cell=start_cell,
                include_header=task_config.get('include_header', True),
                handle_existing_filters=task_config.get('handle_existing_filters', False),
                formula=formula,
                formula_position=formula_position,
                append_mode=append_mode,
                max_rows_limit=max_rows_limit
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
    parser.add_argument('--task', type=str, help='Run a specific task exclusively (e.g., wallet_balance)')
    
    # For backward compatibility
    parser.add_argument('--function', type=str, help='[DEPRECATED] Please use --task instead')
    
    args = parser.parse_args()
    
    # Handle deprecated --function parameter
    if args.function and not args.task:
        logger.warning("The --function parameter is deprecated. Please use --task instead.")
        args.task = args.function
    
    # Check authentication if requested
    if args.check_auth:
        if check_auth():
            logger.info("Google Sheets authentication successful!")
            return 0
        else:
            logger.error("Google Sheets authentication failed!")
            return 1
    
    def load_config():
        """Load configuration from file"""
        try:
            with open(args.config, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading configuration: {e}")
            logger.info("Creating example configuration file...")
            
            # Create example configuration
            example_config = {
                "wallet_balance": {
                    "data_type": "wallet_balance",
                    "spreadsheet_id": "YOUR_SPREADSHEET_ID",
                    "sheet_name": "YOUR_SHEET_NAME",
                    "start_cell": "A1",
                    "include_header": True,
                    "refresh_interval_minutes": 10,
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
                    "refresh_interval_minutes": 10,
                    "params": {
                        "netuids": "1",
                        "egrep_keys": []
                    }
                }
            }
            
            with open(args.config, 'w') as f:
                json.dump(example_config, f, indent=2)
                
            logger.info(f"Example configuration created at {args.config}")
            logger.info("Please edit this file with your Google Sheets information and run again.")
            return None
    
    # Function to run one iteration of updates
    def run_updates(config):
        # Store last update times in a JSON file to persist between restarts
        last_updates_file = 'last_updates.json'
        last_updates = {}
        
        # Load existing last update times if file exists
        if os.path.exists(last_updates_file):
            try:
                with open(last_updates_file, 'r') as f:
                    last_updates = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Error reading {last_updates_file}, starting with empty update times")
        
        current_time = datetime.now()
        results = {}
        tasks_to_update = []
        
        # Check which tasks need to be updated based on refresh interval
        for task_name, task_config in config.items():
            # Get refresh interval with default of 5 minutes if not specified
            refresh_interval = task_config.get('refresh_interval_minutes', 5)
            
            # Convert to timedelta
            refresh_delta = timedelta(minutes=refresh_interval)
            
            # Get last update time
            last_update_str = last_updates.get(task_name)
            needs_update = True
            
            if last_update_str:
                try:
                    last_update = datetime.fromisoformat(last_update_str)
                    time_since_update = current_time - last_update
                    needs_update = time_since_update >= refresh_delta
                    
                    if not needs_update:
                        time_remaining = refresh_delta - time_since_update
                        logger.info(f"Skipping task {task_name}: last updated {time_since_update.total_seconds()/60:.1f} mins ago, "
                                  f"will update in {time_remaining.total_seconds()/60:.1f} mins")
                except (ValueError, TypeError):
                    logger.warning(f"Invalid last update time for {task_name}: {last_update_str}")
            
            if needs_update:
                tasks_to_update.append(task_name)
        
        # If running a specific task, only update that one regardless of refresh interval
        if args.task and args.task in config:
            tasks_to_update = [args.task]
            logger.info(f"Forcing update of specific task: {args.task}")
        
        if not tasks_to_update:
            logger.info("No tasks need updating at this time")
            return True
            
        # Update only tasks that need updating
        filtered_config = {task: config[task] for task in tasks_to_update}
        update_results = update_all_sheets(filtered_config)
        
        # Update last_updates for tasks that were processed
        for task_name, success in update_results.items():
            if success:
                last_updates[task_name] = current_time.isoformat()
        
        # Save updated timestamps
        with open(last_updates_file, 'w') as f:
            json.dump(last_updates, f)
        
        success = all(update_results.values())
        if success and update_results:
            logger.info(f"All sheets updated successfully! Updated: {', '.join(update_results.keys())}")
        elif not update_results:
            logger.info("No sheets were updated in this cycle")
        else:
            logger.warning(f"Some sheets failed to update: {update_results}")
        
        results.update(update_results)
        return success
    
    # Load initial configuration
    config = load_config()
    if config is None:
        return 1
    
    # If a specific task is specified, run once and exit
    if args.task:
        success = run_updates(config)
        return 0 if success else 1
    
    # Otherwise, run continuously with a 5-minute sleep interval
    logger.info("Starting continuous mode with regular check intervals")
    try:
        while True:
            # Reload configuration at the start of each loop
            config = load_config()
            if config is None:
                logger.error("Failed to load configuration, will retry in 1 minute")
                time.sleep(60)
                continue
                
            success = run_updates(config)
            if not success:
                logger.error("Update cycle had errors, will check again in 1 minute")
            
            # Sleep for a shorter interval to check more frequently
            # This allows us to honor shorter refresh intervals more precisely
            logger.info("Sleeping for 1 minute before checking for updates again...")
            time.sleep(60)  # 60 seconds = 1 minute
            
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, stopping continuous updates")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error in continuous mode: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    exit(main()) 
