import bittensor as bt
import pandas as pd

subtensor_address = "127.0.0.1:9944"
hotkey_to_check = "5DvcNTacjrX1Zq8oCSnABUa3U8gcTwYDwqxhZA4kKscNzk23"
# netuid_int range from 0 to 64
netuid_ints = list(range(64))


# Initialize subtensor connection
try:
    subtensor = bt.subtensor(network=f"ws://{subtensor_address}")
    current_block = subtensor.get_current_block()
except Exception as e:
    print(f"Error connecting to subtensor network: {e}")


def get_child_hotkey_stake(
    hotkey_ss58: str, subtensor: "bittensor.subtensor", netuid: int
) -> float:
    # Retrieve the initial total stake for the hotkey without any child/parent adjustments.
    initial_stake: int = subtensor.substrate.query(
        "SubtensorModule", "TotalHotkeyStake", [hotkey_ss58]
    ).value
    print(f"initial_stake: {initial_stake}")

    stake_to_children: int = 0
    stake_from_parents: int = 0
    # Retrieve lists of parents and children from storage, based on the hotkey and network ID.
    parents: list[tuple[int, str]] = subtensor.substrate.query(
        "SubtensorModule", "ParentKeys", [hotkey_ss58, netuid]
    )
    children: list[tuple[int, str]] = subtensor.substrate.query(
        "SubtensorModule", "ChildKeys", [hotkey_ss58, netuid]
    )

    # Iterate over children to calculate the total stake allocated to them.
    for proportion, _ in children:
        proportion = proportion.value
        print(f"child proportion: {proportion}")

        # Calculate the stake proportion allocated to the child based on the initial stake.
        normalized_proportion: float = proportion / (2**64 - 1)
        stake_proportion_to_child: float = initial_stake * normalized_proportion
        print(f"stake_proportion_to_child: {stake_proportion_to_child}")

        # Accumulate the total stake given to children.
        stake_to_children += stake_proportion_to_child

    # Iterate over parents to calculate the total stake received from them.
    for proportion, parent in parents:
        proportion = proportion.value
        print(f"parent proportion: {proportion}")

        parent = parent.value
        print(f"parent: {parent}")

        # Retrieve the parent's total stake.
        parent_stake: int = subtensor.substrate.query(
            "SubtensorModule", "TotalHotkeyStake", [parent]
        ).value

        # Calculate the stake proportion received from the parent.
        normalized_proportion: float = proportion / (2**64 - 1)
        stake_proportion_from_parent: float = parent_stake * normalized_proportion
        print(f"stake_proportion_from_parent: {stake_proportion_from_parent}")

        # Accumulate the total stake received from parents.
        stake_from_parents += stake_proportion_from_parent

    # Calculate the final stake for the hotkey by adjusting the initial stake with the stakes
    # to/from children and parents.
    finalized_stake: int = initial_stake - stake_to_children + stake_from_parents

    # get the max stake for the network
    max_stake: int = subtensor.substrate.query(
        "SubtensorModule", "NetworkMaxStake", [netuid]
    ).value
    print(f"max_stake: {max_stake} for netuid: {netuid}")

    # Return the finalized stake value for the hotkey, but capped at the max stake.
    finalized_stake = min(finalized_stake, max_stake)
    print(f"finalized_stake: {finalized_stake}")

    # Return the finalized stake value for the hotkey.
    return finalized_stake / 1e9


for netuid_int in netuid_ints:
    print(f"Processing netuid: {netuid_int}")

    child_hotkey_stake = get_child_hotkey_stake(hotkey_to_check, subtensor, netuid_int)
    print(f"child_hotkey_stake: {child_hotkey_stake}")

    # Retrieve the metagraph for the specified network ID.
    try:
        metagraph = subtensor.metagraph(netuid=netuid_int)
    except Exception as e:
        print(f"Error fetching metagraph for netuid {netuid}: {e}")

    # Extract the first AxonInfo entry
    axon_ip, axon_port = None, None
    if metagraph.axons and len(metagraph.axons) > 0:
        first_axon = metagraph.axons[0]
        if hasattr(first_axon, "ip") and hasattr(first_axon, "port"):
            axon_ip = first_axon.ip
            axon_port = first_axon.port

    data = {
        "SUBNET": netuid_int,
        "UID": metagraph.uids,
        "STAKE()": metagraph.stake,
        "RANK": metagraph.ranks,
        "TRUST": metagraph.trust,
        "CONSENSUS": metagraph.consensus,
        "INCENTIVE": metagraph.incentive,
        "DIVIDENDS": metagraph.dividends,
        "EMISSION(ρ)": metagraph.emission,
        "VTRUST": metagraph.validator_trust,
        "VAL": metagraph.validator_permit,
        "UPDATED": metagraph.last_update,
        "ACTIVE": metagraph.active,
        # 'AXON_IP': [axon_ip] * len(metagraph.uids),
        # 'AXON_PORT': [axon_port] * len(metagraph.uids),
        "AXON": [
            f"{ip}:{port}"
            for ip, port in zip(
                [axon_ip] * len(metagraph.uids), [axon_port] * len(metagraph.uids)
            )
        ],
        "HOTKEY": metagraph.hotkeys,
        "COLDKEY": metagraph.coldkeys,
    }

    # Convert the dictionary to a DataFrame
    subnet_axons = pd.DataFrame(data)

    # get the values from the dataframe with the matching hotkey
    hotkey_row = subnet_axons[subnet_axons["HOTKEY"] == hotkey_to_check]

    # print out all the values for the hotkey
    if not hotkey_row.empty:
        for hotkey_attr in hotkey_row:
            print(f"{hotkey_attr}: {hotkey_row[hotkey_attr].values[0]}")
