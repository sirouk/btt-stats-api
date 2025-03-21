import bittensor as bt
import asyncio
import sys
from datetime import datetime, timedelta, timezone

BLOCK_TIME_SECONDS = 12   
SLIPPAGE_PRECISION = 0.0001  # Precision of 0.0001 tao


if len(sys.argv) < 2:
    print("Usage: python test_subnet_chase_ema.py <netuid>")
    sys.exit(1)
netuid = int(sys.argv[1])

if len(sys.argv) < 3:
    print("Usage: python test_subnet_chase_ema.py <netuid> <wallet_name>")
    sys.exit(1)
wallet_name = sys.argv[2]

if len(sys.argv) < 4:
    print("Usage: python test_subnet_chase_ema.py <netuid> <wallet_name> <slippage_target>")
    sys.exit(1)
slippage_target = float(sys.argv[3])

if len(sys.argv) < 5:
    print("Usage: python test_subnet_chase_ema.py <netuid> <wallet_name> <slippage_target> <max_tao_budget>")
    sys.exit(1)
max_tao_budget = float(sys.argv[4])


try:
    wallet = bt.wallet(name=wallet_name)
    wallet.unlock_coldkey()
except Exception as e:
    print(f"Error getting wallet: {e}")
    sys.exit(1)


async def chase_ema(netuid, wallet):
    remaining_budget = max_tao_budget  # Initialize remaining budget
    
    async with bt.AsyncSubtensor('finney') as sub:
        while remaining_budget > 0:  # Continue only if we have budget left
            subnet_info = await sub.subnet(netuid)
            
            print("\nSubnet Information:")
            print("-" * 50)
            
            alpha_price = float(subnet_info.price.tao)
            moving_price = float(subnet_info.moving_price) * 1e11

            blocks_since_registration = subnet_info.last_step + subnet_info.blocks_since_last_step - subnet_info.network_registered_at
            seconds_since_registration = blocks_since_registration * BLOCK_TIME_SECONDS
            
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

            # Binary search with remaining budget as max
            target_slippage = slippage_target  # in tao
            min_increment = 0.0
            max_increment = min(1.0, remaining_budget)
            best_increment = 0.0
            closest_slippage = float('inf')
            
            while (max_increment - min_increment) > 1e-6:
                current_increment = (min_increment + max_increment) / 2
                slippage_tuple = subnet_info.slippage(current_increment)
                slippage = float(slippage_tuple[1].tao)
                print(f"DEBUG - increment: {current_increment:.6f}, slippage: {slippage:.6f}, raw: {slippage_tuple}")
                
                if abs(slippage - target_slippage) < abs(closest_slippage - target_slippage):
                    closest_slippage = slippage
                    best_increment = current_increment
                
                if abs(slippage - target_slippage) < SLIPPAGE_PRECISION:
                    break
                elif slippage < target_slippage:
                    min_increment = current_increment
                else:
                    max_increment = current_increment

            increment = best_increment
            print(f"Final increment: {increment:.6f} (slippage: {float(subnet_info.slippage(increment)[1].tao):.6f})")
            print(f"Remaining budget: {remaining_budget:.6f}")

            if increment > remaining_budget:
                print("Insufficient remaining budget")
                break

            # Decrement budget by the amount used
            remaining_budget -= abs(increment)
            
            quit()
            
            if alpha_price > moving_price:
                print("Price is above moving_price! SELL ALPHA TOKENS!")
                # SELL ALPHA TOKENS!

                print(f"slippage for subnet {netuid}", subnet_info.slippage(increment))
                sub.unstake( 
                    wallet = wallet, 
                    netuid = netuid, 
                    hotkey = subnet_info.owner_hotkey, 
                    tao_amount = increment, 
                )

                print (f'netuid {netuid} stake added: increment {increment} @ price {alpha_price}')

            elif alpha_price < moving_price:
                print("Price is below moving_price! STAKE TAO TO SUBNET!")
                # STAKE TAO TO SUBNET!

                print(f"slippage for subnet {netuid}", subnet_info.slippage(increment))
                sub.add_stake( 
                    wallet = wallet, 
                    netuid = netuid, 
                    hotkey = subnet_info.owner_hotkey, 
                    tao_amount = increment, 
                )

                print (f'netuid {netuid} stake added: increment {increment} @ price {alpha_price}')

            else:
                print("Price is equal to moving_price! DO NOTHING!")
                continue  # Don't decrement budget if no action taken

            current_stake = sub.get_stake(
                coldkey_ss58 = wallet.coldkeypub.ss58_address,
                hotkey_ss58 = subnet_info.owner_hotkey,
                netuid = netuid,
            )

            print(f'netuid {netuid} stake: {current_stake}')

            # wait for block before next iteration
            await sub.wait_for_block()

        print(f"Budget exhausted. Total used: {max_tao_budget - remaining_budget:.6f}")

async def main():
    # continue loop perpetually
    while True:
        await chase_ema(netuid, wallet)

asyncio.run(main())