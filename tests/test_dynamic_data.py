import bittensor as bt

# Define the Subtensor network address
subtensor_address = "127.0.0.1:9944"

subtensor = bt.subtensor(network=f"ws://{subtensor_address}")

# Fetch dynamic subnet info for subnet 19
all_sn_dynamic_info_list = subtensor.all_subnets()
all_sn_dynamic_info = {info.netuid: info for info in all_sn_dynamic_info_list}

try:
    subnet_info = all_sn_dynamic_info.get(19)
    if subnet_info is None:
        print("No dynamic info found for subnet 19")
    else:
        # Extract all values into a dictionary
        info_dict = {
            'netuid': subnet_info.netuid,
            'owner_hotkey': subnet_info.owner_hotkey,
            'owner_coldkey': subnet_info.owner_coldkey,
            'subnet_name': subnet_info.subnet_name,
            'symbol': subnet_info.symbol,
            'tempo': subnet_info.tempo,
            'last_step': subnet_info.last_step,
            'blocks_since_last_step': subnet_info.blocks_since_last_step,
            'emission': str(subnet_info.emission),
            'alpha_in': str(subnet_info.alpha_in),
            'alpha_out': str(subnet_info.alpha_out),
            'tao_in': str(subnet_info.tao_in),
            'price': str(subnet_info.price),
            'k': subnet_info.k,
            'is_dynamic': subnet_info.is_dynamic,
            'alpha_out_emission': str(subnet_info.alpha_out_emission),
            'alpha_in_emission': str(subnet_info.alpha_in_emission),
            'tao_in_emission': str(subnet_info.tao_in_emission),
            'pending_alpha_emission': str(subnet_info.pending_alpha_emission),
            'pending_root_emission': str(subnet_info.pending_root_emission),
            'network_registered_at': subnet_info.network_registered_at,
            'subnet_volume': str(subnet_info.subnet_volume),
            'subnet_identity': subnet_info.subnet_identity,
            'moving_price': subnet_info.moving_price,
            'alpha_token_price': subnet_info.tao_in.tao / subnet_info.alpha_in.tao
        }
        print(info_dict)
except Exception as e:
    print(e)
