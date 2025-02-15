import bittensor as bt
import sys
import json

if len(sys.argv) != 2:
    print("Usage: python test_meta_mini.py <hotkey>")
    print("Please provide a hotkey as a command line argument")
    sys.exit(1)

HOTKEY = sys.argv[1]
NETUID = 19
BLOCKTIME = 12
subtensor_address = "finney" # or try locally via ws://127.0.0.1:9944

subtensor = bt.subtensor(network=f"{subtensor_address}")
metagraph = subtensor.metagraph(netuid=NETUID)

daily_blocks = (60 * 60 * 24) / BLOCKTIME  # Number of blocks per day
tempo_multiplier = daily_blocks / metagraph.tempo
pool = metagraph.pool
alpha_token_price = pool.tao_in / pool.alpha_in

data = {}
for uid, hotkey in enumerate(metagraph.hotkeys):
    data[hotkey] = {
        'alpha_stake': float(metagraph.alpha_stake[uid]),
        'tao_stake': float(metagraph.tao_stake[uid]),
        'emission': float(metagraph.emission[uid]),
        'daily_rewards_alpha': float(metagraph.emission[uid] * tempo_multiplier),
        'daily_rewards_tao': float(metagraph.emission[uid] * tempo_multiplier * alpha_token_price)
    }

if HOTKEY in data:
    # pretty print the data
    print(json.dumps(data[HOTKEY], indent=4))
else:
    print(f"Hotkey {HOTKEY} not found in the metagraph")