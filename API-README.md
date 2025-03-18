# Bittensor Stats HTTP API

This document provides details on using the HTTP API server component of the Bittensor Stats API.

## Overview

The HTTP API server provides endpoints that return Bittensor data in CSV format. It's designed for integration with custom applications or for users who prefer to work with raw data rather than using Google Sheets.

## Starting the Server

To start the HTTP API server:

```bash
# Install required packages
pip install pandas bittensor pexpect requests python-dotenv portalocker

# Start the server
python http_server.py
```

By default, the server runs on port 41337. You can access it at `http://localhost:41337/`.

## Available Endpoints

### Wallet Balance

```
GET /wallet-balance
```

Returns a CSV with balance information for all coldkeys.

#### Output Columns:
- Wallet_Name: Name of the wallet
- Coldkey_Address: Bittensor coldkey address
- Free_Balance: Available balance (τ)
- Staked_Balance: Currently staked balance (τ)
- Total_Balance: Sum of free and staked balance (τ)

### Subnet List

```
GET /subnet-list
```

Returns a CSV with information about all available subnets.

#### Output Columns:
- NETUID: Subnet ID
- EMISSION: Emission value for the subnet
- TEMPO: Blocks per epoch
- NAME: Subnet name
- FOUNDER: Subnet founder address
- LOCK_COST: Cost to register on the subnet (τ)
- POW_THRESHOLD: Proof of work threshold
- MIN_DIFFICULTY: Minimum difficulty
- SUDO: Whether the subnet has sudo capabilities
- N_VALIDATORS: Number of validators
- MAX_ALLOWED_VALIDATORS: Maximum validators allowed
- [+ additional subnet parameters]

### Metagraph Data

```
GET /metagraph?netuid=1,19&egrep=hotkey1,hotkey2
```

Returns a CSV with detailed metagraph information for the specified subnet(s).

#### Parameters:
- netuid: Comma-separated list of subnet IDs (required)
- egrep: Comma-separated list of hotkeys to filter by (optional)

#### Output Columns:
- SUBNET: Subnet ID
- UID: Neuron UID
- STAKE: Amount of stake
- RANK: Rank value
- TRUST: Trust value
- CONSENSUS: Consensus value
- INCENTIVE: Incentive value
- DIVIDENDS: Dividends value
- EMISSION: Emission value
- VTRUST: Validator trust
- VPERMIT: Validator permit status
- UPDATED: Last update block
- ACTIVE: Activity status
- AXON: Axon IP:port
- HOTKEY: Hotkey address
- COLDKEY: Coldkey address
- IMMUNE: Immunity status
- ALPHA_STAKE: Alpha token stake
- TAO_STAKE: TAO token stake
- DAILY_REWARDS_ALPHA: Estimated daily rewards in Alpha
- DAILY_REWARDS_TAO: Estimated daily rewards in TAO

### Registration History

```
GET /registrations
```

Returns a CSV with recent registration history from log files.

#### Output Columns:
- Subnet: Subnet ID
- ColdKey: Coldkey index
- HotKey: Hotkey index
- Cost: Registration cost in τ
- Line: Line number in log file
- Timestamp: Registration timestamp
- Filename: Log filename

### Subnet 19 (TauVision) Metrics

```
GET /sn19_metrics?fetchFileDate=YYYY-MM-DD&dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD&dataSource=source
```

Returns a CSV with SN19-specific metrics.

#### Parameters:
- fetchFileDate: Date of the data file (YYYY-MM-DD format)
- dateFrom: Start date for filtering (YYYY-MM-DD format)
- dateTo: End date for filtering (YYYY-MM-DD format)
- dataSource: Data source identifier

#### Output Columns:
- id: Record ID
- axon_uid: Axon UID
- miner_hotkey: Miner hotkey
- validator_hotkey: Validator hotkey
- task: Task name
- declared_volume: Declared data volume
- consumed_volume: Consumed data volume
- total_requests_made: Total requests
- requests_429: Number of 429 errors
- requests_500: Number of 500 errors
- period_score: Score for the period
- created_at: Timestamp

### Recent Subnet 19 Activity

```
GET /sn19_recent?hours=72
```

Returns a CSV with recent SN19 activity.

#### Parameters:
- hours: Number of hours to look back (default: 72)

## Caching

The API server implements caching to improve performance:

- Most requests are cached for 3 minutes by default
- Cache is stored in the `cache/` directory
- SN19 endpoints (`/sn19_metrics` and `/sn19_recent`) bypass the cache to ensure fresh data

## Environment Variables

- HOTKEYS: Comma-separated list of hotkeys to filter SN19 data

## Integration Examples

### Curl

```bash
# Get wallet balance
curl http://localhost:41337/wallet-balance > wallet_balance.csv

# Get metagraph for subnet 1
curl "http://localhost:41337/metagraph?netuid=1" > subnet1_metagraph.csv

# Get recent SN19 data for last 24 hours
curl "http://localhost:41337/sn19_recent?hours=24" > recent_sn19.csv
```

### Python

```python
import requests
import pandas as pd
from io import StringIO

# Get metagraph data
response = requests.get("http://localhost:41337/metagraph?netuid=1,19")
df = pd.read_csv(StringIO(response.text))

# Process data
df_filtered = df[df['STAKE'] > 1.0]
print(f"Found {len(df_filtered)} neurons with >1.0 stake")
```

## Troubleshooting

If you encounter issues:

1. Check if the subtensor node is running and accessible (default: 127.0.0.1:9944)
2. Ensure required Python packages are installed
3. Check access permissions for the logs directory if using registration endpoint
4. Verify network connectivity for SN19 endpoints

## Advanced Configuration

You can modify the following constants in `http_server.py`:

- PORT: Server port (default: 41337)
- CACHE_DURATION: How long to cache responses (default: 3 minutes)
- subtensor_address: Address of the subtensor node (default: 127.0.0.1:9944) 