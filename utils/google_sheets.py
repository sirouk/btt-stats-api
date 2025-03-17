import os
import pandas as pd
import numpy as np
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Google Sheets API configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'service-account.json')

def check_auth():
    """Check if authentication with Google Sheets API is working properly"""
    try:
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            print(f"ERROR: Service account file not found at {SERVICE_ACCOUNT_FILE}")
            print("To set up Google Sheets authentication:")
            print("1. Create a service account in Google Cloud Console")
            print("2. Enable Google Sheets API in your Google Cloud project")
            print("3. Create and download a service account key as JSON")
            print("4. Save the downloaded JSON file as 'service-account.json' in the root directory of this project")
            return False
            
        # Test if we can create the service with the credentials
        # Just creating the service object verifies that the credentials are valid
        service = setup_sheets_api()
        
        # If we got here, the credentials are valid
        print(f"Google Sheets authentication is working correctly!")
        print(f"Service account: {get_service_account_email()}")
        print(f"Make sure to share your Google Sheets with this email address.")
        return True
    except Exception as e:
        print(f"ERROR: Failed to authenticate with Google Sheets API: {e}")
        return False

def get_service_account_email():
    """Get the email address of the service account from the credentials file"""
    try:
        import json
        with open(SERVICE_ACCOUNT_FILE, 'r') as f:
            data = json.load(f)
            return data.get('client_email', 'Email not found in credentials file')
    except Exception as e:
        return f"Error reading credentials file: {e}"

def setup_sheets_api():
    """Set up and return Google Sheets API service"""
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

def serialize_for_sheets(val):
    """Convert various Python/Pandas data types to formats acceptable by Google Sheets"""
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.isoformat()
    elif pd.isna(val):
        return ''  # Empty string for NaN values
    elif isinstance(val, (float, np.float64)):
        return float(val)  # Convert numpy float to Python float
    elif isinstance(val, (bool, np.bool_)):
        # Convert numpy bool to Python bool, then TRUE if True, FALSE if False
        return 'TRUE' if val else 'FALSE'    
    elif isinstance(val, (int, np.int64)):
        return int(val)  # Convert numpy int to Python int
    return str(val)  # Convert everything else to string

def update_google_sheet(spreadsheet_id, sheet_name, df, start_cell='A1', include_header=True, handle_existing_filters=False, formula=None, formula_position=0):
    """Update a Google Sheet with DataFrame data, preserving formatting and handling filters
    
    Args:
        spreadsheet_id (str): Google Sheets ID
        sheet_name (str): Name of the sheet to update
        df (pandas.DataFrame): DataFrame containing the data to upload
        start_cell (str): Cell where data should start (e.g., 'A1')
        include_header (bool): Whether to include the DataFrame column headers
        handle_existing_filters (bool): Whether to preserve existing filters in the sheet
        formula (str or callable): Optional formula to add to a column. Use {0} as row placeholder if string,
                               or pass a function that takes row_index as parameter.
        formula_position (int): Position to place formula column (0=first, -1=last, n=nth column)
    """
    service = setup_sheets_api()
    sheet = service.spreadsheets()

    # Get the current sheet properties and existing filter
    sheet_metadata = sheet.get(spreadsheetId=spreadsheet_id, ranges=[sheet_name], includeGridData=False).execute()
    sheet_props = sheet_metadata['sheets'][0]['properties']
    sheet_id = sheet_props['sheetId']
    max_rows = sheet_props['gridProperties']['rowCount']
    max_cols = sheet_props['gridProperties']['columnCount']

    # Fetch existing filter
    if handle_existing_filters:
        existing_filter = None
        try:
            filter_metadata = sheet.get(spreadsheetId=spreadsheet_id, ranges=[sheet_name], fields='sheets/basicFilter').execute()
            existing_filter = filter_metadata['sheets'][0].get('basicFilter')
        except Exception as e:
            print(f"No existing filter found or error fetching filter: {e}")

        # If a filter exists, remove it temporarily
        if existing_filter:
            remove_filter_request = {
                "requests": [
                    {
                        "clearBasicFilter": {
                            "sheetId": sheet_id
                        }
                    }
                ]
            }
            sheet.batchUpdate(spreadsheetId=spreadsheet_id, body=remove_filter_request).execute()
            print("Temporarily removed existing filter")

    # Determine the range based on the start cell and data size
    start_col, start_row = start_cell[0], int(start_cell[1:])
    
    # Calculate the end column considering the formula column
    total_cols = df.shape[1] + (1 if formula is not None else 0)
    end_col = chr(ord(start_col) + total_cols - 1)
    end_row = start_row + df.shape[0] + (1 if include_header else 0) - 1
    data_range = f'{sheet_name}!{start_cell}:{end_col}{end_row}'

    # Convert DataFrame to list of lists, ensuring all values are properly serialized
    values = []
    
    if include_header:
        # Process header row
        header_row = df.columns.tolist()
        if formula is not None:
            # Insert empty cell for formula column at the specified position
            if formula_position == 0:
                header_row = [''] + header_row
            elif formula_position == -1 or formula_position >= len(header_row):
                header_row = header_row + ['']
            else:
                header_row.insert(formula_position, '')
        values.append(header_row)
    
    # Process data rows
    for idx, (_, row) in enumerate(df.iterrows()):
        row_values = [serialize_for_sheets(val) for val in row]
        
        if formula is not None:
            # Calculate the actual row number in the sheet (accounting for header)
            # This is used for both formula string formatting and as input to formula functions
            sheet_row = start_row + idx + (1 if include_header else 0)
            
            # Determine the formula value based on its type
            if callable(formula):
                # If formula is a function, call it with the row index
                try:
                    formula_cell = formula(sheet_row)
                except Exception as e:
                    print(f"Error executing formula function for row {sheet_row}: {e}")
                    formula_cell = f"ERROR: {str(e)}"
            else:
                # Otherwise, treat it as a string template and format it
                try:
                    formula_cell = formula.format(sheet_row)
                except Exception as e:
                    print(f"Error formatting formula for row {sheet_row}: {e}")
                    formula_cell = f"ERROR: {str(e)}"
                    
            # Insert formula at the specified position
            if formula_position == 0:
                row_values = [formula_cell] + row_values
            elif formula_position == -1 or formula_position >= len(row_values):
                row_values = row_values + [formula_cell]
            else:
                row_values.insert(formula_position, formula_cell)
        
        values.append(row_values)

    body = {
        'values': values
    }

    # Update the sheet with new data, preserving formatting
    result = sheet.values().update(
        spreadsheetId=spreadsheet_id,
        range=data_range,
        valueInputOption='USER_ENTERED',
        body=body
    ).execute()

    print(f"{result.get('updatedCells')} cells updated with new data.")

    # Fetch the format of the first data row
    first_data_row = start_row + (1 if include_header else 0)
    format_range = f'{sheet_name}!{start_col}{first_data_row}:{end_col}{first_data_row}'
    format_response = sheet.get(spreadsheetId=spreadsheet_id, ranges=format_range, fields='sheets/data/rowData/values/userEnteredFormat').execute()
    
    if 'sheets' in format_response and format_response['sheets']:
        row_data = format_response['sheets'][0]['data'][0]['rowData']
        if row_data and 'values' in row_data[0]:
            # Prepare format copy request
            format_copy_request = {
                "requests": [
                    {
                        "copyPaste": {
                            "source": {
                                "sheetId": sheet_id,
                                "startRowIndex": first_data_row - 1,
                                "endRowIndex": first_data_row,
                                "startColumnIndex": ord(start_col) - ord('A'),
                                "endColumnIndex": ord(end_col) - ord('A') + 1
                            },
                            "destination": {
                                "sheetId": sheet_id,
                                "startRowIndex": first_data_row,
                                "endRowIndex": end_row,
                                "startColumnIndex": ord(start_col) - ord('A'),
                                "endColumnIndex": ord(end_col) - ord('A') + 1
                            },
                            "pasteType": "PASTE_FORMAT",
                            "pasteOrientation": "NORMAL"
                        }
                    }
                ]
            }

            # Apply format to new rows
            sheet.batchUpdate(spreadsheetId=spreadsheet_id, body=format_copy_request).execute()
            print(f"Applied format to new rows from {first_data_row + 1} to {end_row}")

    # Clear everything below the new data, respecting sheet limits
    if end_row < max_rows:
        clear_request = {
            "requests": [
                {
                    "updateCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": end_row,
                            "endRowIndex": max_rows,
                            "startColumnIndex": ord(start_col) - ord('A'),
                            "endColumnIndex": ord(end_col) - ord('A') + 1
                        },
                        "fields": "userEnteredValue"
                    }
                }
            ]
        }
        sheet.batchUpdate(spreadsheetId=spreadsheet_id, body=clear_request).execute()
        print(f"Cleared rows from {end_row + 1} to {max_rows} in columns {start_col} to {end_col}")

    # If there was an existing filter, copy its criteria
    if handle_existing_filters and existing_filter:
        # Reapply filter to the data range
        filter_start_row = start_row - 1 if include_header else start_row - 2
        filter_request = {
            "requests": [
                {
                    "setBasicFilter": {
                        "filter": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": filter_start_row,
                                "endRowIndex": end_row,
                                "startColumnIndex": ord(start_col) - ord('A'),
                                "endColumnIndex": ord(end_col) - ord('A') + 1
                            }
                        }
                    }
                }
            ]
        }

        if existing_filter and 'criteria' in existing_filter:
            filter_request["requests"][0]["setBasicFilter"]["filter"]["criteria"] = existing_filter["criteria"]

        sheet.batchUpdate(spreadsheetId=spreadsheet_id, body=filter_request).execute()

        print(f"Reapplied filter to range {sheet_name}!{chr(ord('A') + filter_start_row)}{start_col}:{end_col}{end_row}")

def get_sheet_id(spreadsheet_id, sheet_name):
    """Get the sheet ID from a spreadsheet name"""
    service = setup_sheets_api()
    sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = sheet_metadata.get('sheets', '')
    for sheet in sheets:
        if sheet['properties']['title'] == sheet_name:
            return sheet['properties']['sheetId']
    return None

if __name__ == "__main__":
    print("Checking Google Sheets API authentication...")
    if check_auth():
        print("Authentication successful!")
    else:
        print("Authentication failed. Please follow the instructions above to set up authentication.") 