import bittensor as bt
import asyncio
import sys
from datetime import datetime, timedelta, timezone

if len(sys.argv) != 2:
    print("Usage: python test_subnet_price_vs_ema.py <subnet_id>")
    sys.exit(1)

subnet_id = int(sys.argv[1])

async def main():
    async with bt.AsyncSubtensor('finney') as sub:
        subnet_info = await sub.subnet(subnet_id)
        
        print("\nSubnet Information:")
        print("-" * 50)
        
        alpha_price = float(subnet_info.price.tao)
        moving_price = float(subnet_info.moving_price) * 1e11

        blocks_since_registration = subnet_info.last_step + subnet_info.blocks_since_last_step - subnet_info.network_registered_at
        seconds_per_block = 12
        seconds_since_registration = blocks_since_registration * seconds_per_block
        
        current_time = datetime.now(timezone.utc)
        registered_time = current_time - timedelta(seconds=seconds_since_registration)
        registered_time_str = registered_time.strftime('%Y-%m-%d %H:%M:%S UTC')

        info_dict = {
            'netuid': subnet_info.netuid,
            'Subnet': subnet_info.subnet_name,
            'Symbol': subnet_info.symbol,
            'Owner Hotkey': subnet_info.owner_hotkey[:10] + "...",
            'Owner Coldkey': subnet_info.owner_coldkey[:10] + "...",
            'Registered': registered_time_str,
            'Is Dynamic': subnet_info.is_dynamic,
            'Tempo': subnet_info.tempo,
            'Last Step': subnet_info.last_step,
            'Blocks Since Last Step': subnet_info.blocks_since_last_step,
            'Subnet Volume (Alpha)': str(subnet_info.subnet_volume),
            'Subnet Volume (Tao)': str(subnet_info.subnet_volume * alpha_price),
            'Emission': f"{float(subnet_info.tao_in_emission * 1e2):.2f}%",
            'Price (Tao)': f"{float(alpha_price):.5f}",
            'Moving Price (Tao)': f"{float(moving_price):.5f}",
        }
        
        for key, value in info_dict.items():
            print(f"{key:25}: {value}")
        print("-" * 50)
        
        if alpha_price > moving_price:
            print("Price is above moving_price!")
        elif alpha_price < moving_price:
            print("Price is below moving_price!")
        else:
            print("Price is equal to moving_price!")

asyncio.run(main())