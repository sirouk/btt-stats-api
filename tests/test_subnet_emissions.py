import bittensor as bt
import pandas as pd

def get_subnet_emissions(subtensor_address="127.0.0.1:9944"):
    """
    Get emissions for all subnets in the Bittensor network.
    
    Args:
        subtensor_address (str): The address of the Bittensor network node
        
    Returns:
        pandas.DataFrame: DataFrame containing subnet emissions information
    """
    # Initialize subtensor connection
    try:
        subtensor = bt.subtensor(network=f"ws://{subtensor_address}")
    except Exception as e:
        print(f"Error connecting to subtensor network: {e}")
        return None

    # Get all subnets info
    all_subnets = subtensor.get_all_subnets_info()
    
    # Calculate total emission value across all subnets
    total_emission = 0
    for subnet in all_subnets:
        if subnet is None:
            continue
        metagraph = subtensor.metagraph(netuid=subnet.netuid)
        emission_value = float(metagraph.emission.sum())
        total_emission += emission_value

    # Collect subnet data
    subnets_data = []
    for subnet in all_subnets:
        if subnet is None:
            continue
            
        metagraph = subtensor.metagraph(netuid=subnet.netuid)
        emission_value = float(metagraph.emission.sum())
        emission_pct = (emission_value / total_emission * 100) if total_emission > 0 else 0
        
        data = {
            'netuid': subnet.netuid,
            'emission_value': emission_value,
            'emission_percent': f"{emission_pct:.2f}%",
            'neurons': subnet.subnetwork_n,
            'max_neurons': subnet.max_n,
            'tempo': subnet.tempo,
            'burn': float(subnet.burn),
        }
        subnets_data.append(data)

    # Create DataFrame and sort by emission percentage
    subnet_df = pd.DataFrame(subnets_data)
    subnet_df = subnet_df.sort_values('emission_value', ascending=False)
    
    return subnet_df

if __name__ == "__main__":
    # Get emissions data
    emissions_df = get_subnet_emissions()
    
    if emissions_df is not None:
        print("\nSubnet Emissions:")
        print(emissions_df.to_string(index=False)) 