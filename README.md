# Bittensor Stats API

A comprehensive toolset for extracting, visualizing, and analyzing Bittensor blockchain data.

## Overview

This repository provides two different approaches to managing Bittensor stats:

1. **Google Sheets Integration** (Recommended): Automatically export Bittensor data directly to Google Sheets for easy visualization and analysis.

2. **HTTP API Server**: A lightweight web server that provides endpoints with Bittensor data in CSV format for custom integrations.

## Quick Start

### Google Sheets Integration (Recommended)

```bash
# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
pip install pandas bittensor pexpect requests python-dotenv portalocker google-auth google-api-python-client

# Set up Google Sheets API credentials
# (See SHEETS-README.md for detailed instructions)

# Configure your Google Sheets connection
cp .sheets_config.json.example .sheets_config.json
# Edit .sheets_config.json with your spreadsheet details

# Run the integration
python btt_to_sheets.py
```

### HTTP API Server

```bash
# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
pip install pandas bittensor pexpect requests python-dotenv portalocker

# Start the API server
python http_server.py
# Server runs on port 41337 by default
```

## Features

- **Wallet Balance Tracking**: Monitor TAO balances across all coldkeys
- **Subnet Information**: Detailed view of all subnets
- **Metagraph Data**: Complete neuron data including stake, trust, and rewards
- **Registration History**: Track registration attempts and costs
- **Subnet 19 (TauVision) Metrics**: Specialized data for SN19 miners
- **Price Data**: Current TAO price from exchanges

## Detailed Documentation

For comprehensive setup and usage instructions, see:

- [Google Sheets Integration Guide](SHEETS-README.md) - Complete guide to setting up and using the Google Sheets integration
- [HTTP API Documentation](API-README.md) - Details on using the HTTP API endpoints

## Which Method Should I Use?

- **Google Sheets Integration** is ideal for most users who want:
  - Easy visualization with charts and formatting
  - Scheduled automatic updates
  - Data organization across multiple sheets
  - No need to run a server continuously

- **HTTP API Server** is better for:
  - Custom applications needing raw data
  - Integration with other systems via HTTP
  - Programmatic access to Bittensor data

We recommend the Google Sheets approach for most use cases, as it provides better visualization options and easier setup.

## License

MIT
