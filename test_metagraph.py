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






# mock query_params from /metagraph?netuid=4%2C8%2C18%2C19%2C23%2C34%2C35&egrep=TRUST&egrep=5CqSeSc&egrep=5FjacWn&egrep=5FW5SqG&egrep=5DNn9ZM&egrep=5CAXk8H&egrep=5CqichJ
query_params = {
    'netuid': ['4,8,18,19,23,34,35'],
    'egrep': ['5CqSeSc', '5FjacWn', '5FW5SqG', '5DNn9ZM', '5CAXk8H', '5CqichJ']
}


def test_metagraph(query_params):
    output = ""
    
    netuids = query_params.get('netuid', [''])[0].split(',')
    sanitized_egrep_keys = [re.escape(key) for key in query_params.get('egrep', []) if re.match(r'^[a-zA-Z0-9]+$', key)]
    pattern = "|".join(sanitized_egrep_keys)
    # print(pattern)
    # quit()

    # Initialize subtensor connection
    try:
        subtensor = bt.subtensor(network=f"ws://{subtensor_address}")
        current_block = subtensor.get_current_block()
    except Exception as e:
        print(f"Error connecting to subtensor network: {e}")
        return "Connection Error"

    resulting_lines = []  # Initialize outside the loop

    for netuid in netuids:
        netuid = netuid.strip()  # Remove any leading/trailing whitespace
        if re.match(r'^\d+$', netuid):
            netuid_int = int(netuid)
            try:
                metagraph = subtensor.metagraph(netuid=netuid_int)
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

            data = {
                'SUBNET': netuid_int,
                'UID': metagraph.uids,
                'STAKE()': metagraph.stake,
                'RANK': metagraph.ranks,
                'TRUST': metagraph.trust,
                'CONSENSUS': metagraph.consensus,
                'INCENTIVE': metagraph.incentive,
                'DIVIDENDS': metagraph.dividends,
                'EMISSION(ρ)': metagraph.emission,
                'VTRUST': metagraph.validator_trust,
                'VAL': metagraph.validator_permit,
                'UPDATED': metagraph.last_update,
                'ACTIVE': metagraph.active,
                # 'AXON_IP': [axon_ip] * len(metagraph.uids),
                # 'AXON_PORT': [axon_port] * len(metagraph.uids),
                'AXON': [f"{ip}:{port}" for ip, port in zip([axon_ip] * len(metagraph.uids), [axon_port] * len(metagraph.uids))],
                'HOTKEY': metagraph.hotkeys,
                'COLDKEY': metagraph.coldkeys
            }

            # Convert the dictionary to a DataFrame
            netuid_lines = pd.DataFrame(data)
            #print(netuid_lines)

            # Process each row
            for index, row in netuid_lines.iterrows():
                uid = str(row['UID'])

                # Apply regex search on uid or other fields as needed
                if uid and (re.search(pattern, str(row)) or (not sanitized_egrep_keys)):
                    #print(f"Processing UID: {uid}")
                    try:
                        block_at_registration = int(str(subtensor.query_subtensor("BlockAtRegistration", None, [netuid_int, uid])))
                        immune_until = block_at_registration + subtensor.immunity_period(netuid=netuid_int)
                        immune = immune_until > current_block

                        # Update the DataFrame by adding the immune status
                        netuid_lines.at[index, 'IMMUNE'] = immune
                    except Exception as e:
                        print(f"Error processing UID {uid}: {e}")
                        netuid_lines.at[index, 'IMMUNE'] = False  # Or handle as appropriate
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

    return output

results = test_metagraph(query_params)
print(results)
