import bittensor as bt
import pandas as pd
import websockets
import asyncio
import json




def trust(W, S, threshold=0):
    """Trust vector for subnets with variable threshold"""
    Wn = (W > threshold).float()
    return Wn.T @ S

def rank(W, S):
    """Rank vector for subnets"""
    R = W.T @ S
    return R / R.sum()

def consensus(T, kappa=0.5, rho=10):
    """Yuma Consensus 1"""
    return torch.sigmoid( rho * (T - kappa) )

def emission(C, R):
    """Emission vector for subnets"""
    E = C*R
    return E / E.sum()

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


async def get_burn_regs(netuid, chain_endpoint):
    subnet_hex = hex(netuid)[2:].zfill(2)
    async with websockets.connect(
        chain_endpoint, ping_interval=None
    ) as ws:
        await ws.send(json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "state_subscribeStorage",
                
                # Number of burn registrations
                #"params": [[f"0x658faa385070e074c85bf6b568cf055564b6168414916325e7cb4f3f47691e11{subnet_hex}00"]],
                
                # Burn/Recycle amount
                "params": [[f"0x658faa385070e074c85bf6b568cf055501be1755d08418802946bca51b686325{subnet_hex}00"]],
            }
        ))
        # Ignore the first confirmation response
        await ws.recv()
        response = await ws.recv()
        full_response = json.loads(response)
        changes_list = full_response["params"]["result"]["changes"]
        print(changes_list)

        # Extract and convert the little-endian hex value to an integer
        for changes in changes_list:
            key_hex, value_hex = changes
            int_value = little_endian_hex_to_int(value_hex)
            #print(f"Registration Burn/Recycle => Key Hex: {key_hex}, Value (int): {int_value}")
            return int_value



async def fetch_subnet_info(subtensor_address):

    chain_endpoint = f"ws://{subtensor_address}"

    # Initialize the Subtensor connection
    subtensor = bt.subtensor(network=f"ws://{subtensor_address}")

    # Initialize a list to collect subnet data
    subnets_data = []

    for netuid in subtensor.get_subnets():
    #for netuid in [19]:
        subnet = subtensor.metagraph(netuid)

        # No workey...
        # W = subnet.W
        # Sn = (subnet.S/subnet.S.sum()).clone().float()
        # T = trust(W, Sn)
        # R = rank(W, Sn)
        # C = consensus(T)
        # E = subnet.emission(C, R)

        # get emissions for subnet
        block = subtensor.block
        rao_weight = subtensor.query_subtensor( 'EmissionValues', block, [ netuid ] ).value
        sn_emission_tao = bt.Balance(rao_weight) # type: ignore
        sn_emission = bt.Balance.__float__( sn_emission_tao )

        # get the recycle/burn
        burn = await get_burn_regs(netuid, chain_endpoint)
        
        data = {
        'NETUID': subnet.netuid,
        'N': subnet.n,
        'MAX_N': len(subnet.neurons),
        # perentage representation of weight with % symbol
        'EMISSION': f"{sn_emission * 100:.2f}%",
        'TEMPO': 'TBD',
        'BURN': bt.Balance.__float__(bt.Balance(burn)), # type: ignore
        'POW': 'TBD',
        'SUDO': 'TBD',
        'WEIGHT': sn_emission,
        }
        subnets_data.append(data)
        #print(f"Processed subnet NETUID: {data['NETUID']}")


    subnet_df = pd.DataFrame(subnets_data)

    return subnet_df

    print(subnet_df)

def get_subnet_info(subtensor_address):
    return asyncio.run(fetch_subnet_info(subtensor_address))
    

if __name__ == "__main__":

    # Define the Subtensor network address
    subtensor_address = "127.0.0.1:9944"

    data = get_subnet_info(subtensor_address)
    print(data)