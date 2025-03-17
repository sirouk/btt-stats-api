# Bittensor to Google Sheets

This tool collects data from Bittensor and exports it to Google Sheets. It supports retrieving wallet balances, subnet information, metagraph data, registration history, and SN19-specific metrics.

## New Functionality: Google Sheets Integration

This repository now includes a new feature that allows you to export Bittensor data directly to Google Sheets instead of just serving it via HTTP. The new `btt_to_sheets.py` script integrates the existing data collection functions but outputs the results to Google Sheets rather than CSV format.

Key features:
- Configure multiple data exports in a single configuration file
- Schedule updates via cron jobs
- Maintain formatting and filtering in Google Sheets
- Customize which data goes to which sheets

## Prerequisites

- Python 3.7 or higher
- A Google Cloud Platform account with Google Sheets API enabled
- A service account with access to Google Sheets

## Installation

1. Clone this repository or download the files
2. Install required packages:

```bash
pip install pandas bittensor pexpect requests python-dotenv portalocker google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

## Google Sheets API Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API for your project
4. Create a service account with Editor permissions
5. Create and download a key for the service account as JSON
6. Save the downloaded JSON file as `service-account.json` in the root directory of this project
7. Share your Google Sheets with the service account email address (found in the JSON file)

### Testing Google Sheets Authentication

You can verify that your Google Sheets authentication is set up correctly by running:

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

### Setting Up Sheet Permissions

To allow the script to write to your Google Sheets:

1. Open your Google Sheet
2. Click "Share" in the upper right corner
3. Add the service account email displayed during the authentication test
4. Grant "Editor" access to the service account

If your sheet has protection rules:
1. In Google Sheets, select the protected range
2. Click the three dots in the upper right of the sheet and select "Protected sheets & ranges"
3. Select your protected range from the sidebar
4. Click "Edit permissions"
5. Add the service account email to the list of users who can edit
6. Save your changes

Without proper permissions, the script will fail with access errors when trying to update protected ranges.

## Configuration

1. Copy `.sheets_config.json.example` to `.sheets_config.json`:

```bash
cp .sheets_config.json.example .sheets_config.json
```

2. Edit `.sheets_config.json` to:
   - Replace `YOUR_SPREADSHEET_ID` with the ID of your Google Sheet (found in the URL)
   - Configure sheet names and other parameters as needed
   - You can remove any sections you don't need

3. For SN19 specific features, add your hotkeys to a .env file:

```bash
echo 'HOTKEYS=your_hotkey1,your_hotkey2' > .env
```

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

### Scheduling Regular Updates

To schedule automatic updates, add a cron job:

```bash
crontab -e
```

Add a line like this to update every hour:
```
0 * * * * cd /path/to/btt-stats-api && python btt_to_sheets.py >> btt_sheets_cron.log 2>&1
```

## Configuration Options

Each entry in the configuration file supports these options:

- `data_type`: Type of data to collect (e.g., "wallet_balance", "subnet_list", "metagraph", etc.)
- `spreadsheet_id`: The ID of your Google Sheet
- `sheet_name`: The name of the specific sheet tab to update
- `start_cell`: Cell where data should start (default: "A1")
- `include_header`: Whether to include column headers (default: true)
- `handle_existing_filters`: Whether to preserve existing filters in the sheet (default: false)
- `params`: Additional parameters specific to the data type

## Available Data Types

- `wallet_balance`: Wallet balance information for all coldkeys
- `subnet_list`: List of all available subnets
- `metagraph`: Detailed metagraph information for specified subnets
  - Parameters: `netuid` (subnet ID), `egrep` (filter by regex)
- `registrations`: Recent registration history
- `sn19_metrics`: Subnet 19 (TauVision) metrics
  - Parameters: `fetchFileDate`, `dateFrom`, `dateTo`, `dataSource`
- `sn19_recent`: Recent Subnet 19 activities
  - Parameters: `hours` (history timeframe)

## Troubleshooting

If you encounter issues:

1. Check the log file at `btt_to_sheets.log`
2. Ensure your service account has access to the Google Sheets
3. Verify that the subtensor node is accessible at the configured address
4. Check that the subnet IDs specified in your configuration exist

## License

MIT
