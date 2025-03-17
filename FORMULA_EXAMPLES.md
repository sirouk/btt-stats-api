# Formula Examples for Bittensor to Google Sheets

This document provides a comprehensive list of formula examples that you can use in your `.sheets_config.json` file to enhance your Google Sheets with calculated values and formatting.

## Google Sheets Formula Type

With `"type": "formula"`, you can use native Google Sheets formulas. The row number will be injected where you place `{0}` in your formula.

### Basic Calculations

```json
// Sum values from columns C and D
"formula": {
  "type": "formula",
  "text": "=SUM(C{0}+D{0})",
  "position": -1
}

// Calculate average from a range
"formula": {
  "type": "formula",
  "text": "=AVERAGE(C{0}:F{0})",
  "position": -1
}

// Percentage calculation
"formula": {
  "type": "formula",
  "text": "=D{0}/C{0}*100",
  "position": -1
}
```

### Conditional Formatting

```json
// Simple conditional
"formula": {
  "type": "formula",
  "text": "=IF(C{0}>100, \"High\", \"Low\")",
  "position": -1
}

// Multiple conditions
"formula": {
  "type": "formula",
  "text": "=IF(C{0}>1000, \"High\", IF(C{0}>100, \"Medium\", \"Low\"))",
  "position": -1
}

// Check for active neurons
"formula": {
  "type": "formula",
  "text": "=IF(K{0}>0, \"Active\", \"Inactive\")",
  "position": -1
}
```

### Text Operations

```json
// Concatenate values
"formula": {
  "type": "formula",
  "text": "=CONCATENATE(\"SN\", A{0}, \"-\", B{0})",
  "position": -1
}

// Extract part of text
"formula": {
  "type": "formula",
  "text": "=LEFT(E{0}, 8)",
  "position": -1
}
```

### Date Operations

```json
// Format date from another cell
"formula": {
  "type": "formula",
  "text": "=TEXT(F{0}, \"yyyy-mm-dd hh:mm:ss\")",
  "position": -1
}

// Calculate days between dates
"formula": {
  "type": "formula",
  "text": "=DAYS(TODAY(), F{0})",
  "position": -1
}

// Current date
"formula": {
  "type": "formula",
  "text": "=TODAY()",
  "position": -1
}
```

## Python Formula Type

With `"type": "python"`, you can execute Python code to calculate values. You have access to the current row as `row` and the row index as `idx`.

### Basic Python Examples

```json
// Simple string
"formula": {
  "type": "python",
  "text": "\"Static Value\"",
  "position": -1
}

// Access row value
"formula": {
  "type": "python",
  "text": "str(row['Coldkey_Address'])",
  "position": -1
}

// Format with f-string
"formula": {
  "type": "python",
  "text": "f\"Row {idx}: {row['HOTKEY']}\"",
  "position": -1
}
```

### Numeric Calculations

```json
// Basic calculation
"formula": {
  "type": "python",
  "text": "str(float(row['Free_Balance']) + float(row['Staked_Balance']))",
  "position": -1
}

// Format number with precision
"formula": {
  "type": "python",
  "text": "f\"{float(row['STAKE']):.2f} TAO\"",
  "position": -1
}

// Percentage calculation
"formula": {
  "type": "python",
  "text": "f\"{(float(row['consumed_volume']) / float(row['declared_volume']) * 100):.1f}%\"",
  "position": -1
}
```

### Conditional Logic

```json
// Simple conditional
"formula": {
  "type": "python",
  "text": "\"Active\" if row['ACTIVE'] else \"Inactive\"",
  "position": -1
}

// Multiple conditions
"formula": {
  "type": "python",
  "text": "\"High\" if float(row['STAKE']) > 1000 else \"Medium\" if float(row['STAKE']) > 100 else \"Low\"",
  "position": -1
}

// Complex condition with f-string
"formula": {
  "type": "python",
  "text": "f\"Registration {'succeeded' if row['Cost'] else 'failed'} for SN{row['Subnet']}\"",
  "position": -1
}
```

### Date Formatting - Standard Formats

```json
// Basic date format (YYYY-MM-DD HH:MM:SS)
"formula": {
  "type": "python",
  "text": "datetime.now().strftime('%Y-%m-%d %H:%M:%S')",
  "position": -1
}

// ISO 8601 Format
"formula": {
  "type": "python",
  "text": "datetime.now().isoformat()",
  "position": -1
}

// RFC 2822 Format (for emails)
"formula": {
  "type": "python",
  "text": "datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')",
  "position": -1
}

// Human-readable format
"formula": {
  "type": "python",
  "text": "datetime.now().strftime('%B %d, %Y at %I:%M %p')",
  "position": -1
}
```

### Date Formatting - From Row Data

```json
// Format a datetime column
"formula": {
  "type": "python",
  "text": "row['created_at'].strftime('%Y-%m-%d %H:%M:%S')",
  "position": -1
}

// Parse string date and reformat
"formula": {
  "type": "python",
  "text": "datetime.strptime(row['Timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')",
  "position": -1
}

// Format with day name
"formula": {
  "type": "python",
  "text": "row['created_at'].strftime('%A, %B %d, %Y')",
  "position": -1
}

// Format with timezone
"formula": {
  "type": "python",
  "text": "row['created_at'].astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')",
  "position": -1
}
```

### Date Calculations

```json
// Days ago calculation
"formula": {
  "type": "python",
  "text": "f\"{(datetime.now() - row['created_at']).days} days ago\"",
  "position": -1
}

// Format with time difference
"formula": {
  "type": "python",
  "text": "f\"Created {(datetime.now() - row['created_at']).days} days, {((datetime.now() - row['created_at']).seconds // 3600)} hours ago\"",
  "position": -1
}

// Format based on update timestamp (seconds)
"formula": {
  "type": "python",
  "text": "f\"Updated: {(datetime.now() - timedelta(seconds=int(row['UPDATED']))).strftime('%Y-%m-%d %H:%M:%S')}\"",
  "position": -1
}

// Show different format based on recency
"formula": {
  "type": "python",
  "text": "row['created_at'].strftime('%H:%M:%S') if (datetime.now() - row['created_at']).days < 1 else row['created_at'].strftime('%b %d, %Y')",
  "position": -1
}
```

### Hyperlinks and References

```json
// Generate a hyperlink to explorer
"formula": {
  "type": "python",
  "text": "f\"https://explorer.bittensor.com/neuron/{row['HOTKEY']}\"",
  "position": -1
}

// Generate a mailto link
"formula": {
  "type": "python",
  "text": "f\"mailto:admin@example.com?subject=Neuron%20{row['UID']}%20Issue\"",
  "position": -1
}
```

### Advanced Examples

```json
// Combine multiple fields
"formula": {
  "type": "python",
  "text": "f\"SN{row['SUBNET']} - UID: {row['UID']} - {row['HOTKEY'][:10]}...\"",
  "position": -1
}

// Calculate percentile rank
"formula": {
  "type": "python",
  "text": "f\"{idx / len(df) * 100:.1f}% rank\"",
  "position": -1
}

// Conditional with time-based logic
"formula": {
  "type": "python",
  "text": "\"Recently Updated\" if int(row['UPDATED']) < 3600 else \"Updated Today\" if int(row['UPDATED']) < 86400 else \"Outdated\"",
  "position": -1
}
```

## Combining Formula Types

You can add multiple formula columns by configuring multiple tasks with different configurations:

```json
"wallet_balance_with_sum": {
  "data_type": "wallet_balance",
  "spreadsheet_id": "YOUR_SPREADSHEET_ID",
  "sheet_name": "WalletBalance",
  "start_cell": "A1",
  "formula": {
    "type": "formula",
    "text": "=SUM(C{0}+D{0})",
    "position": 5
  }
},
"wallet_balance_with_date": {
  "data_type": "wallet_balance",
  "spreadsheet_id": "YOUR_SPREADSHEET_ID",
  "sheet_name": "WalletBalance",
  "start_cell": "A1",
  "formula": {
    "type": "python",
    "text": "datetime.now().strftime('%Y-%m-%d %H:%M:%S')",
    "position": 6
  }
}
```

## Common Date Format Codes

Here's a reference for common date format codes used in `strftime()`:

| Format Code | Description | Example |
|-------------|-------------|---------|
| `%Y` | Year with century | 2023 |
| `%y` | Year without century | 23 |
| `%m` | Month as zero-padded number | 01-12 |
| `%d` | Day as zero-padded number | 01-31 |
| `%H` | Hour in 24-hour format | 00-23 |
| `%I` | Hour in 12-hour format | 01-12 |
| `%M` | Minute as zero-padded number | 00-59 |
| `%S` | Second as zero-padded number | 00-59 |
| `%p` | AM/PM | AM, PM |
| `%a` | Abbreviated weekday name | Sun, Mon, ... |
| `%A` | Full weekday name | Sunday, Monday, ... |
| `%b` | Abbreviated month name | Jan, Feb, ... |
| `%B` | Full month name | January, February, ... |
| `%c` | Locale's datetime representation | Mon Sep 30 07:06:05 2013 |
| `%x` | Locale's date representation | 09/30/13 |
| `%X` | Locale's time representation | 07:06:05 | 