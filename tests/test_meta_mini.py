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

all_sn_dynamic_info_list = subtensor.all_subnets()
all_sn_dynamic_info = {info.netuid: info for info in all_sn_dynamic_info_list}
subnet_info = all_sn_dynamic_info.get(NETUID)

daily_blocks = (60 * 60 * 24) / BLOCKTIME  # Number of blocks per day
tempo_multiplier = daily_blocks / metagraph.tempo
pool = metagraph.pool
alpha_token_price = pool.tao_in / pool.alpha_in


if HOTKEY not in metagraph.hotkeys:
    print(f"Hotkey {HOTKEY} not found in the metagraph")
    sys.exit(1)

for uid in metagraph.uids:
    if HOTKEY in metagraph.hotkeys[uid]:
        daily_rewards_alpha = float(metagraph.emission[uid] * tempo_multiplier)
        daily_rewards_tao = float(daily_rewards_alpha * alpha_token_price)
        alpha_to_tao_with_slippage = subnet_info.alpha_to_tao_with_slippage(alpha=daily_rewards_alpha)

        print(f"Hotkey: {HOTKEY}")
        print(f"UID: {uid}")
        print(f"Daily Rewards Alpha: {daily_rewards_alpha}")
        print(f"Daily Rewards Tao: {daily_rewards_tao}")
        print(f"Alpha to Tao with Slippage: {alpha_to_tao_with_slippage}")