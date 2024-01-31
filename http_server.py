import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import pexpect
import re
import pandas as pd
from io import StringIO
import bittensor as bt

PORT = 41337


class Server(socketserver.TCPServer):
    allow_reuse_address = True


def clean_chars(str_data):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', str_data)


def get_subnet_weight(subnet_id, subtensor):
    return float(subtensor.get_emission_value_by_subnet(netuid=subnet_id))


class CommandHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

        output = ""
        if path == '/subnet-list':
            # Run the subnet list command
            command = "/usr/local/bin/btcli s list --subtensor.chain_endpoint ws://37.27.53.131:9944"
            child = pexpect.spawn(command, dimensions=(500, 500))
            child.expect(pexpect.EOF)
            cmd_output = child.before.decode()
            cmd_output = clean_chars(cmd_output)
            lines = cmd_output.splitlines()[1:-1]

            # add a column to the end of the first line
            lines[0] += "  WEIGHT"

            # connect to the subtensor chain
            subtensor = bt.subtensor(network="ws://37.27.53.131:9944")

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
                    command = f"/usr/local/bin/btcli s metagraph --netuid={netuid} --subtensor.chain_endpoint ws://37.27.53.131:9944"
                    child = pexpect.spawn(command, dimensions=(500, 500))
                    child.expect(pexpect.EOF)
                    netuid_output = child.before.decode()
                    netuid_output = clean_chars(netuid_output)

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
