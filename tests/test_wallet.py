import bittensor as bt
import pandas as pd
from io import StringIO
import pexpect
import re

# Define constants
subtensor_address = "127.0.0.1:9944"

def clean_chars(str_data):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|τ')
    return ansi_escape.sub('', str_data)

def trim_output_from_pattern(output, start_pattern):
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if len(start_pattern) > 0 and line.strip()[:len(start_pattern)] == start_pattern:
            return '\n'.join(lines[i:])
    return ''

def test_wallet_balance():
    # Run the subnet list command
    command = f"/usr/local/bin/btcli w balance --all --subtensor.network finney --wallet-path ~/.bittensor/wallets/ --subtensor.chain_endpoint ws://{subtensor_address}"
    child = pexpect.spawn(command, dimensions=(500, 500))
    child.expect(pexpect.EOF)
    cmd_output = child.before.decode(errors='ignore')
    cmd_output = clean_chars(cmd_output)
    
    # Find the section starting with the balance table
    cmd_output = trim_output_from_pattern(cmd_output, "Wallet Coldkey Balance")
    
    # Split into lines and filter out header lines and separator lines
    lines = cmd_output.splitlines()
    data_lines = []
    for line in lines:
        # Skip empty lines, headers, and separator lines
        if not line.strip() or 'Network:' in line or 'Wallet Name' in line or '━' in line or 'Total Balance' in line:
            continue
        # Keep only lines that start with 'coldkey-' and have balance data
        if line.strip().startswith('coldkey-'):
            # Clean up the line and extract data
            parts = [p for p in line.strip().split() if p]
            if len(parts) >= 3:  # We need at least wallet name, address, and balance
                wallet_name = parts[0]
                coldkey = parts[1]
                # Convert balance to float, removing any τ symbol
                balance = float(parts[-1].replace('τ', '').strip())
                data_lines.append([wallet_name, coldkey, balance])

    # Create DataFrame from the cleaned data
    df = pd.DataFrame(data_lines, columns=['Wallet_Name', 'Coldkey_Address', 'Balance'])
    
    print("Initial DataFrame:")
    print(df.head())
    print("\nColumn types:")
    print(df.dtypes)

    if not df.empty:
        print("\nFinal DataFrame:")
        print(df.head())
        print("\nFinal column types:")
        print(df.dtypes)

        # Perform assertions to verify the data
        assert not df.empty, "DataFrame should not be empty"
        assert all(col in df.columns for col in ['Wallet_Name', 'Coldkey_Address', 'Balance']), "Missing expected columns"
        assert df['Wallet_Name'].str.startswith('coldkey-').all(), "All wallet names should start with 'coldkey-'"
        assert (df['Balance'] >= 0).all(), "Balance should not be negative"
        
        # Calculate total balance
        total_balance = df['Balance'].sum()
        print(f"\nTotal Balance: {total_balance:.4f}")
        
        print("\nAll tests passed successfully!")
        return df
    else:
        raise ValueError("No wallet data found")

if __name__ == "__main__":
    try:
        df = test_wallet_balance()
    except Exception as e:
        print(f"Test failed: {e}") 