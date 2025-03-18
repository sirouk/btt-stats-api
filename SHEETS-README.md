# Bittensor to Google Sheets Integration

This document provides detailed instructions for setting up and using the Google Sheets integration component of the Bittensor Stats API.

## Overview

The Google Sheets integration (`btt_to_sheets.py`) automatically exports Bittensor data directly to Google Sheets. This provides several advantages:

- Easy visualization with Google Sheets' charts and formatting
- Scheduled automatic updates
- Data organization across multiple sheets
- No need to run a server continuously

## Prerequisites

- Python 3.11 or higher
- A Google Cloud Platform account with Google Sheets API enabled
- A service account with access to Google Sheets

## Setup Steps

### 1. Installation Requirements

The btt-stats-api requires Python 3.11+ and some system dependencies:

```bash
# Install python 3.11
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv

# Install PM2 if not already installed
if command -v pm2 &> /dev/null
then
    pm2 startup && pm2 save --force
else
    sudo apt install npm -y
    sudo npm install pm2 -g && pm2 update
    npm install pm2@latest -g && pm2 update && pm2 save --force && pm2 startup && pm2 save
fi
```

Then clone the repository:

```bash
cd $HOME
git clone https://github.com/sirouk/btt-stats-api
cd ./btt-stats-api
```

### 2. Setting Up Python Environment

Create a Python virtual environment and install the required dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you need to cleanup and reinstall the environment:

```bash
cd $HOME/btt-stats-api
deactivate
rm -rf .venv
```

### 3. Google Sheets API Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API for your project
4. Create a service account with Editor permissions
5. Create and download a key for the service account as JSON
6. Save the downloaded JSON file as `service-account.json` in the root directory of this project
7. Share your Google Sheets with the service account email address (found in the JSON file)

#### Testing Google Sheets Authentication

Verify that your Google Sheets authentication is set up correctly:

```bash
python utils/google_sheets.py
```

A successful authentication will show:
```
Checking Google Sheets API authentication...
Google Sheets authentication is working correctly!
Service account: your-service-account@your-project.iam.gserviceaccount.com
Make sure to share your Google Sheets with this email address.
Authentication successful!
```

#### Setting Up Sheet Permissions

To allow the script to write to your Google Sheets:

1. Open your Google Sheet
2. Click "Share" in the upper right corner
3. Add the service account email displayed during the authentication test
4. Grant "Editor" access to the service account

If your sheet has protection rules:
1. In Google Sheets, select "Tools" → "Protected sheets & ranges"
2. For each protected range:
   - Select the range in the sidebar
   - Click "Edit permissions"
   - Add the service account email to the list of allowed editors
   - Click "Save"

Without proper permissions, the script will fail with access errors when trying to update protected ranges.

### 4. Configuration

1. Copy the example configuration file:

```bash
cp .sheets_config.json.example .sheets_config.json
```

2. Edit `.sheets_config.json` to:
   - Replace `YOUR_SPREADSHEET_ID` with the ID of your Google Sheet (found in the URL)
   - Configure sheet names and other parameters as needed
   - You can remove any sections you don't need

## Usage

### Check Authentication

First, verify that your Google Sheets authentication is working:

```bash
python btt_to_sheets.py --check-auth
```

If successful, you'll see "Google Sheets authentication successful!"

### Update Google Sheets

Run the script to update all configured sheets:

```bash
python btt_to_sheets.py
```

You can specify a different configuration file:

```bash
python btt_to_sheets.py --config my_custom_config.json
```

### Run a Specific Task Only

To run only one specific task from your configuration:

```bash
python btt_to_sheets.py --task wallet_balance
```

This will only process the "wallet_balance" entry from your configuration file, ignoring all others.

## Setting Up Scheduled Updates

### Setting up PM2 Service

After configuring your `.sheets_config.json` file, set up the btt-stats-api as a PM2 service:

```bash
cd $HOME/btt-stats-api

# Activate the virtual environment first (this needs to be done before each PM2 command)
source .venv/bin/activate

# Start the service with PM2 (main service for all tasks)
pm2 start btt_to_sheets.py --name btt-to-sheets --interpreter python3

# Optional: Set up specific tasks for different update frequencies
pm2 start btt_to_sheets.py --name btt-wallet-balance --interpreter python3 -- --task wallet_balance
pm2 start btt_to_sheets.py --name btt-metagraph --interpreter python3 -- --task metagraph

# Ensure PM2 starts on system boot
pm2 save && pm2 startup
```

### PM2 Log Management

Set up automatic log rotation to prevent logs from consuming too much disk space:

```bash
# Install pm2-logrotate module if not already installed
pm2 install pm2-logrotate

# Set maximum size of logs to 50M before rotation
pm2 set pm2-logrotate:max_size 50M

# Retain 10 rotated log files
pm2 set pm2-logrotate:retain 10

# Enable compression of rotated logs
pm2 set pm2-logrotate:compress true

# Set rotation interval to every day
pm2 set pm2-logrotate:rotateInterval '0 0 * * *'
```

### Useful PM2 Commands

```bash
# View logs
pm2 logs                      # View all logs
pm2 logs btt-to-sheets        # View main service logs
pm2 logs btt-wallet-balance   # View wallet balance task logs

# Monitor processes
pm2 monit

# Restart services
pm2 restart all               # Restart all services
pm2 restart btt-to-sheets     # Restart main service

# Stop services
pm2 stop all                  # Stop all services
pm2 stop btt-to-sheets        # Stop main service

# Check status
pm2 status                    # Check status of all services
```

## Configuration Options

Each entry in the configuration file supports these options:

- `data_type`: Type of data to collect (e.g., "wallet_balance", "subnet_list", "metagraph", etc.)
- `spreadsheet_id`: The ID of your Google Sheet
- `sheet_name`: The name of the specific sheet tab to update
- `start_cell`: Cell where data should start (default: "A1")
- `include_header`: Whether to include column headers (default: true)
- `handle_existing_filters`: Whether to preserve existing filters in the sheet (default: false)
- `refresh_interval_minutes`: How often to update this sheet (default: 5)
- `append_mode`: Whether to append data to existing data (default: false)
- `max_rows_limit`: Maximum number of rows to keep in append mode
- `formula`: Optional configuration for adding a formula column to the sheet:
  - `type`: The type of formula to use ("formula" for Google Sheets formulas or "python" for Python code)
  - `text`: The formula to add (use `{0}` as a placeholder for the row number with formula type, or reference row data with Python type)
  - `position`: Where to place the formula column (0=first column, -1=last column, or specific column number)
- `params`: Additional parameters specific to the data type

### Example Configuration

```json
{
  "wallet_balance": {
    "data_type": "wallet_balance",
    "spreadsheet_id": "1ABC123def456GHI789jkl",
    "sheet_name": "Wallet Balances",
    "start_cell": "A1",
    "include_header": true,
    "refresh_interval_minutes": 60
  },
  "subnet_list": {
    "data_type": "subnet_list",
    "spreadsheet_id": "1ABC123def456GHI789jkl",
    "sheet_name": "Subnet List",
    "refresh_interval_minutes": 360
  },
  "metagraph_sn1": {
    "data_type": "metagraph",
    "spreadsheet_id": "1ABC123def456GHI789jkl",
    "sheet_name": "Subnet 1",
    "params": {
      "netuids": "1",
      "egrep_keys": "your_hotkey1,your_hotkey2"
    },
    "formula": {
      "type": "python",
      "text": "f\"{float(row['DAILY_REWARDS_TAO']):.4f} τ/day\"",
      "position": -1
    },
    "refresh_interval_minutes": 30
  }
}
```

## Formula Examples

You can add custom formulas to your sheets that reference the data in each row:

### 1. Google Sheets Formula Type

```json
"wallet_balance": {
  "data_type": "wallet_balance",
  "spreadsheet_id": "YOUR_SPREADSHEET_ID",
  "sheet_name": "WalletBalance",
  "formula": {
    "type": "formula",
    "text": "=SUM(C{0}+D{0})",
    "position": 5
  }
}
```

In this example:
- The formula type is "formula", which means it will be inserted as a standard Google Sheets formula
- A formula column will be added at position 5 (6th column, as it's zero-based)
- Each row will have a formula that sums the values in columns C and D for that row
- The `{0}` in the formula will be replaced with the actual row number

### 2. Python Code Formula Type

```json
"metagraph_sn1": {
  "data_type": "metagraph",
  "spreadsheet_id": "YOUR_SPREADSHEET_ID",
  "sheet_name": "Metagraph_SN1",
  "formula": {
    "type": "python",
    "text": "\"Active\" if row[\"TRUST\"] > 0.5 else \"Inactive\"",
    "position": -1
  }
}
```

In this example:
- The formula type is "python", which means Python code will be executed to generate the cell value
- The Python code has access to:
  - `row`: The pandas Series object containing the row data (access columns by name)
  - `idx`: The current row index (1-based, matching Google Sheets row numbers)
  - `df`: The entire DataFrame
  - `datetime` and `timedelta` from the datetime module
- The result of the Python expression will be converted to a string and inserted as a static value
- This allows for complex data processing using Python's full capabilities
- The Python code is executed when updating the sheet, not in Google Sheets itself

### More Python Formula Examples

```python
# Format a date from row data
"text": "row[\"created_at\"].strftime(\"%b %d, %Y at %H:%M\")"

# Do calculations with numeric values
"text": "f\"{(row[\"consumed_volume\"] / row[\"declared_volume\"] * 100):.2f}%\""

# Create conditional labels
"text": "\"High\" if row[\"STAKE\"] > 1000 else \"Medium\" if row[\"STAKE\"] > 100 else \"Low\""

# Generate a hyperlink
"text": "f\"https://dashboard.example.com/neuron/{row['HOTKEY']}\""

# Format current date and time
"text": "datetime.now().strftime('%Y-%m-%d %H:%M:%S')"
```

## Available Data Types

- `wallet_balance`: Wallet balance information for all coldkeys
- `subnet_list`: List of all available subnets
- `metagraph`: Detailed metagraph information for specified subnets
  - Parameters: `netuids` (comma-separated subnet IDs), `egrep_keys` (filter by hotkeys)
- `registrations`: Recent registration history
- `sn19_metrics`: Subnet 19 (TauVision) metrics
  - Parameters: `fetchFileDate`, `dateFrom`, `dateTo`, `dataSource`, `egrep_keys` (filter by hotkeys, comma-separated)
- `sn19_recent`: Recent Subnet 19 activities
  - Parameters: `hours` (history timeframe)
- `asset_price`: Current price of TAO
  - Parameters: `symbol` (e.g., "TAO-USDT")

## Security Considerations

- Keep your `service-account.json` file secure and never commit it to public repositories
- Limit the service account's permissions to only the specific Google Sheets it needs to access
- Consider creating a dedicated service account for this specific application rather than using a general-purpose one

## Troubleshooting

If you encounter issues:

1. Check the log file at `btt_to_sheets.log`
2. Ensure your service account has access to the Google Sheets
3. Verify that the subtensor node is accessible at the configured address (default: 127.0.0.1:9944)
4. Check that the subnet IDs specified in your configuration exist
5. Ensure the service account has permission to access protected ranges in your sheets