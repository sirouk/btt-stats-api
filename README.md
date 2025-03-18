# Bittensor Stats API

A comprehensive toolset for extracting, visualizing, and analyzing Bittensor blockchain data.

## Overview

This repository provides two different approaches to managing Bittensor stats:

1. **Google Sheets Integration** (Recommended): Automatically export Bittensor data directly to Google Sheets for easy visualization and analysis. See [Google Sheets Integration Guide](SHEETS-README.md) for setup and configuration instructions.

2. **HTTP API Server**: A lightweight web server that provides endpoints with Bittensor data in CSV format for custom integrations. See [HTTP API Documentation](API-README.md) for endpoint details and usage examples.

## Available Data and Features

Both methods provide access to comprehensive Bittensor data:

- **Wallet Balance Tracking**: Monitor TAO balances across all coldkeys
- **Subnet Information**: Detailed view of all subnets with network weights and emission values
- **Metagraph Data**: Complete neuron data including:
  - Stakes (both TAO and Alpha)
  - Trust and consensus scores
  - Incentive and dividends
  - Daily reward calculations
  - Validator metrics
  - Immunity periods
- **Registration History**: Track registration attempts and costs
- **Subnet 19 (TauVision) Metrics**: Specialized data for SN19 miners including:
  - Performance scores
  - Task requests and volume
  - Validator interactions
- **Price Data**: Current TAO price from exchanges

## Which Method Should I Use?

- **Google Sheets Integration** is ideal for most users who want:
  - Easy visualization with charts and formatting
  - Scheduled automatic updates
  - Data organization across multiple sheets
  - No need to run a server continuously
  - Historical data tracking with append mode

- **HTTP API Server** is better for:
  - Custom applications needing raw data
  - Integration with other systems via HTTP
  - Programmatic access to Bittensor data
  - Real-time data requests

We recommend the Google Sheets approach for most use cases, as it provides better visualization options and easier setup.

## License

MIT
