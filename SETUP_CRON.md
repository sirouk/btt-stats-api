# Setting Up Scheduled Updates for Bittensor to Google Sheets

This guide explains how to set up automated scheduled updates for the Bittensor to Google Sheets integration.

## Prerequisites

Before setting up scheduled updates, ensure:

1. The `btt_to_sheets.py` script works correctly when run manually
2. Google Sheets authentication is working (`python utils/google_sheets.py` returns success)
3. Your `.sheets_config.json` file is properly configured with the correct spreadsheet IDs and sheet names

## Setting Up Cron Jobs

### Basic Hourly Update

To update your Google Sheets every hour:

```bash
crontab -e
```

Add the following line:
```
0 * * * * cd /path/to/btt-stats-api && python btt_to_sheets.py >> btt_sheets_cron.log 2>&1
```

### Multiple Update Schedules

You can set up different update frequencies for different configurations:

```
# Update wallet balance every 30 minutes
*/30 * * * * cd /path/to/btt-stats-api && python btt_to_sheets.py --config .wallet_balance_config.json >> wallet_cron.log 2>&1

# Update metagraph data every 4 hours
0 */4 * * * cd /path/to/btt-stats-api && python btt_to_sheets.py --config .metagraph_config.json >> metagraph_cron.log 2>&1
```

### Verifying Cron is Working

Check if your cron jobs are scheduled:
```bash
crontab -l
```

To view logs for debugging:
```bash
tail -f btt_sheets_cron.log
```

## Managing Service Account Permissions

### Finding Your Service Account Email

Run the authentication check to display your service account email:
```bash
python utils/google_sheets.py
```

### Adding Service Account to Multiple Sheets

For each Google Sheet you want to update:
1. Open the Google Sheet
2. Click "Share" in the upper right corner
3. Add the service account email (e.g., `your-service-account@your-project.iam.gserviceaccount.com`)
4. Grant "Editor" access

### Handling Sheet Protection

If you have protected ranges in your sheets:

1. In Google Sheets, select "Tools" → "Protected sheets & ranges"
2. For each protected range:
   - Select the range in the sidebar
   - Click "Edit permissions"
   - Add the service account email to the list of allowed editors
   - Click "Save"

### Testing Permissions

To verify the service account has sufficient permissions:

```bash
python btt_to_sheets.py
```

Check the log for any permission-related errors.

## Troubleshooting

### Common Errors

1. **Authentication errors**: Verify service-account.json is correctly placed in the root directory
2. **Permission errors**: Ensure the service account has access to the spreadsheet
3. **Not found errors**: Verify spreadsheet IDs and sheet names in the configuration
4. **Formatting issues**: Try adding `"handle_existing_filters": true` to your configuration

### Log Rotation

For log management on long-running systems:

```bash
# Install logrotate if not already installed
apt-get install logrotate

# Create a logrotate configuration
cat > /etc/logrotate.d/btt-sheets << EOF
/path/to/btt-stats-api/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF
```

## Security Considerations

- Keep your `service-account.json` file secure and never commit it to public repositories
- Limit the service account's permissions to only the specific Google Sheets it needs to access
- Consider creating a dedicated service account for this specific application rather than using a general-purpose one

## Updating the Service Account

If you need to generate a new service account key:

1. Go to the Google Cloud Console
2. Navigate to "IAM & Admin" → "Service Accounts"
3. Find your service account and click "Manage Keys"
4. Create a new key and download as JSON
5. Replace the existing `service-account.json` file
6. Test authentication again 