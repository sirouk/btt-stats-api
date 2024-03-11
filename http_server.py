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
from datetime import datetime
import os

PORT = 41337
subtensor_address = "127.0.0.1:9944"


class Server(socketserver.TCPServer):
    allow_reuse_address = True


def clean_chars(str_data):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|τ')
    return ansi_escape.sub('', str_data)


def trim_output_from_pattern(output, start_pattern):
    """Trim the output starting from the line that contains the start_pattern."""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        # trim the line for whitespace and check to see if the start_pattern matches the start of the line for the same length
        if len(start_pattern) > 0 and line.strip()[:len(start_pattern)] == start_pattern:
            return '\n'.join(lines[i:])
    return ''  # Return an empty string if the pattern is not found


def get_subnet_weight(subnet_id, subtensor):
    return float(subtensor.get_emission_value_by_subnet(netuid=subnet_id))


class CommandHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

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
                    self.send_error(400, f"Invalid netuid: {netuid}")
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
            self.send_error(404, "File not found")
            return

        #processed_lines = [','.join(re.split(r'\s{2,}', line)) for line in lines]
        #output = '\n'.join(processed_lines)

        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

with Server(("", PORT), CommandHandler) as httpd:
    print(f"Serving at port {PORT}")
    httpd.serve_forever()
