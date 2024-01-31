import bittensor as bt
subtensor = bt.subtensor(network="ws://37.27.53.131:9944")

subnet_id = 13
wallet_hotkey = "5D9v2GHS3qDwvGwBRoY2cNbYbhU2PFNPrkNhiQX9hJStZ1yn"

# Returns the current percent emissions of the given subnet.
def get_subnet_weight(subnet_id):
    return float(subtensor.get_emission_value_by_subnet(netuid=subnet_id))

def get_wallet_uid(hotkey, subnet_id):
    metagraph = subtensor.metagraph(subnet_id)
    axons = metagraph.axons
    uid = 0
    for axon in axons:
        if axon.hotkey == hotkey:
            return uid
        uid += 1
    print("Wallet is not registered on this subnet.")
    return None

metagraph = subtensor.metagraph(subnet_id)
subnet_tao_per_day = get_subnet_weight(subnet_id)*7200

print(subnet_tao_per_day)

incentives = metagraph.incentive.tolist()
wallet_uid = get_wallet_uid(wallet_hotkey, subnet_id)
wallet_incentive = incentives[wallet_uid]
print(wallet_incentive*subnet_tao_per_day * 0.41) # 41% goes to miners
