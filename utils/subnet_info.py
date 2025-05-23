import bittensor as bt
import pandas as pd
import websockets
import asyncio
import json
import time

def little_endian_hex_to_int(hex_str):
    # Remove '0x' prefix if present
    if hex_str.startswith('0x'):
        hex_str = hex_str[2:]
    # Ensure even length
    if len(hex_str) % 2 != 0:
        hex_str = '0' + hex_str
    # Convert hex string to bytes
    byte_array = bytes.fromhex(hex_str)
    # Reverse the byte order (little-endian to big-endian)
    reversed_bytes = byte_array[::-1]
    # Convert bytes to integer
    return int.from_bytes(reversed_bytes, byteorder='big')

async def get_burn_regs(netuid, ws):
    subnet_hex = hex(netuid)[2:].zfill(2)
    await ws.send(json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "state_subscribeStorage",
            "params": [[f"0x658faa385070e074c85bf6b568cf055501be1755d08418802946bca51b686325{subnet_hex}00"]],
        }
    ))
    # Ignore the first confirmation response
    await ws.recv()
    response = await ws.recv()
    full_response = json.loads(response)
    changes_list = full_response["params"]["result"]["changes"]

    # Extract and convert the little-endian hex value to an integer
    for changes in changes_list:
        key_hex, value_hex = changes
        int_value = little_endian_hex_to_int(value_hex)
        return int_value

async def fetch_subnet_info(subtensor_address):
    chain_endpoint = f"{subtensor_address}"
    subtensor = None
    ws = None
    try:
        # Initialize the Subtensor connection
        subtensor = bt.subtensor(network=f"{subtensor_address}")

        # Initialize a list to collect subnet data
        subnets_data = []

        # Get all subnets info using the new method
        all_subnets = subtensor.all_subnets()
        all_sn_dynamic_info = {info.netuid: info for info in all_subnets}
        
        # Calculate total emission value across all subnets
        total_emission = 1

        # Establish websocket connection once
        ws = await websockets.connect(chain_endpoint, ping_interval=None)

        for netuid, subnet in all_sn_dynamic_info.items():
            if subnet is None:
                continue
                
            # Get emission value for this subnet using metagraph
            metagraph = subtensor.metagraph(netuid=netuid)
            emission_value = float(metagraph.emission.sum())
            emission_pct = (emission_value / total_emission * 100) if total_emission > 0 else 0
            
            # Get subnet info for max_n and difficulty
            subnet_hyperparams = subtensor.get_subnet_hyperparameters(netuid)

            # get the recycle/burn
            #time.sleep(2) # temporary to avoid 429 on finney
            burn = await get_burn_regs(netuid, ws)
            
            data = {
                'NETUID': subnet.netuid,
                'N': subnet.k,  # k represents the current number of nodes
                'MAX_N': subnet_hyperparams.max_validators,  # Get max_validators from hyperparameters
                'EMISSION': f"{emission_pct:.2f}%",
                'TEMPO': subnet.tempo,
                'BURN': bt.Balance.__float__(bt.Balance(burn)), # type: ignore
                'POW': subnet_hyperparams.difficulty,
                'SUDO': 'Root' if subnet.owner_hotkey == '5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY' else 'None',
                'WEIGHT': emission_pct / 100 if total_emission > 0 else 0,
                'ALPHA_PRICE': subnet.tao_in.tao / subnet.alpha_in.tao if hasattr(subnet, 'tao_in') and hasattr(subnet, 'alpha_in') else 0.0,
            }
            subnets_data.append(data)

        subnet_df = pd.DataFrame(subnets_data)
        # Sort by emission value descending
        subnet_df = subnet_df.sort_values('EMISSION', ascending=False)
        return subnet_df
    finally:
        if ws is not None:
            try:
                await ws.close()
            except:
                pass  # Ignore any errors during close
        if subtensor and hasattr(subtensor, 'close'):
            try:
                subtensor.close()
            except:
                pass  # Ignore any errors during close

def get_subnet_info(subtensor_address):
    return asyncio.run(fetch_subnet_info(subtensor_address))

if __name__ == "__main__":
    # Define the Subtensor network address
    #subtensor_address = "ws://127.0.0.1:9944"
    subtensor_address = "wss://entrypoint-finney.opentensor.ai:443"

    data = get_subnet_info(subtensor_address)
    print(data[['NETUID', 'N', 'MAX_N', 'EMISSION', 'TEMPO', 'BURN', 'POW', 'SUDO', 'WEIGHT', 'ALPHA_PRICE']])
