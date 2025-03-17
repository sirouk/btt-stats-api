import websockets
import asyncio
import json

netuid = 19
subnet_hex = hex(netuid)[2:].zfill(2)
chain_endpoint = "wss://entrypoint-finney.opentensor.ai:443"

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

async def get_burn_regs():
    async with websockets.connect(
        chain_endpoint, ping_interval=None
    ) as ws:
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
        print(changes_list)

        # Extract and convert the little-endian hex value to an integer
        for changes in changes_list:
            key_hex, value_hex = changes
            int_value = little_endian_hex_to_int(value_hex)
            print(f"Key Hex: {key_hex}, Value (int): {int_value}")

asyncio.run(get_burn_regs())
