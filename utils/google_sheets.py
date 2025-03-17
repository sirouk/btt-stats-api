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

def update_google_sheet(spreadsheet_id, sheet_name, df, start_cell='A1', include_header=True, handle_existing_filters=False, formula=None, formula_position=0, append_mode=False, max_rows_limit=None):
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
        append_mode (bool): If True, append data to the end of the sheet instead of replacing
        max_rows_limit (int): Maximum number of rows to keep in the sheet when in append mode
    """
    service = setup_sheets_api()
    sheet = service.spreadsheets()

    # 1. Get the current sheet properties
    sheet_metadata = sheet.get(spreadsheetId=spreadsheet_id, ranges=[sheet_name], includeGridData=False).execute()
    sheet_props = sheet_metadata['sheets'][0]['properties']
    sheet_id = sheet_props['sheetId']
    current_max_rows = sheet_props['gridProperties']['rowCount']
    current_max_cols = sheet_props['gridProperties']['columnCount']

    # Parse the start cell (this indicates where the header is)
    start_col, header_row = start_cell[0], int(start_cell[1:])

    # 2. Calculate dimensions of new data to be appended
    rows_to_append = df.shape[0] + (1 if include_header else 0)
    total_cols = df.shape[1] + (1 if formula is not None else 0)
    end_col = chr(ord(start_col) + total_cols - 1)
    end_col_index = ord(end_col) - ord('A') + 1
    
    if append_mode:
        print(f"Append mode: will add {rows_to_append} rows of data")
        
        # 3. Count the total existing rows with data
        try:
            data_response = sheet.values().get(
                spreadsheetId=spreadsheet_id,
                range=f'{sheet_name}!{start_col}:{start_col}',
                valueRenderOption='UNFORMATTED_VALUE'
            ).execute()
            
            existing_values = data_response.get('values', [])
            existing_rows = len(existing_values)
            
            print(f"Found {existing_rows} existing rows with data")
            
            # Determine where data starts (immediately after the header)
            data_start_row = header_row + 1
            
            # If sheet is empty (except for header), use header_row as the last row
            if existing_rows < header_row:
                print(f"Sheet appears to be empty (found {existing_rows} rows, header at row {header_row})")
                last_row = header_row
            else:
                last_row = existing_rows
                
            # 4. Handle max_rows_limit by deleting rows if necessary
            if max_rows_limit is not None:
                # Calculate total rows after appending
                total_rows_after_append = last_row + rows_to_append
                
                if total_rows_after_append > max_rows_limit:
                    # Calculate how many rows to delete from the top (after the header)
                    rows_to_delete = total_rows_after_append - max_rows_limit
                    
                    # Find the first row that contains actual data
                    # If include_header is True, data starts at header_row + 1
                    # If include_header is False, data starts at header_row
                    first_data_row = header_row if not include_header else header_row + 1
                    delete_start_index = first_data_row - 1  # 0-indexed for API
                    
                    # Make sure we don't try to delete more rows than exist
                    available_rows_to_delete = last_row - first_data_row + 1
                    
                    if rows_to_delete > available_rows_to_delete:
                        print(f"Warning: Need to delete {rows_to_delete} rows but only {available_rows_to_delete} data rows exist")
                        rows_to_delete = available_rows_to_delete
                        
                    if rows_to_delete > 0:
                        # Get a sample of the data we're about to delete for verification
                        try:
                            # Get first few rows being deleted
                            first_few_range = f'{sheet_name}!{start_col}{delete_start_index+1}:{end_col}{min(delete_start_index+3, delete_start_index+rows_to_delete)}'
                            first_response = sheet.values().get(
                                spreadsheetId=spreadsheet_id,
                                range=first_few_range,
                                valueRenderOption='UNFORMATTED_VALUE'
                            ).execute()
                            first_rows = first_response.get('values', [])
                            
                            # If we're deleting a lot of rows, also get the last few rows
                            last_few_data = []
                            if rows_to_delete > 5:
                                last_few_range = f'{sheet_name}!{start_col}{delete_start_index+rows_to_delete-2}:{end_col}{delete_start_index+rows_to_delete}'
                                last_response = sheet.values().get(
                                    spreadsheetId=spreadsheet_id,
                                    range=last_few_range,
                                    valueRenderOption='UNFORMATTED_VALUE'
                                ).execute()
                                last_rows = last_response.get('values', [])
                                last_few_data = [f"row {delete_start_index+rows_to_delete-2+i}: {row[0] if row and len(row) > 0 else 'empty'}" 
                                                for i, row in enumerate(last_rows)]
                            
                            # Format first few rows for printing
                            first_few_data = [f"row {delete_start_index+1+i}: {row[0] if row and len(row) > 0 else 'empty'}" 
                                            for i, row in enumerate(first_rows)]
                            
                            # Prepare detailed log message with coordinates and sample data
                            delete_range = f'{start_col}{delete_start_index+1}:{end_col}{delete_start_index+rows_to_delete}'
                            print(f"Will delete {rows_to_delete} rows - from row {delete_start_index+1} (first data row) to {delete_start_index+rows_to_delete}")
                            print(f"Sheet coordinates: {delete_range}")
                            print(f"First rows being deleted: {first_few_data}")
                            if last_few_data:
                                print(f"Last rows being deleted: {last_few_data}")
                        except Exception as e:
                            print(f"Could not fetch sample of data to be deleted: {e}")
                        
                        print(f"Deleting {rows_to_delete} rows from the top (starting from first data row) to maintain max limit of {max_rows_limit}")
                        
                        delete_request = {
                            "requests": [
                                {
                                    "deleteDimension": {
                                        "range": {
                                            "sheetId": sheet_id,
                                            "dimension": "ROWS",
                                            "startIndex": delete_start_index,
                                            "endIndex": delete_start_index + rows_to_delete
                                        }
                                    }
                                }
                            ]
                        }
                        
                        try:
                            sheet.batchUpdate(spreadsheetId=spreadsheet_id, body=delete_request).execute()
                            print(f"Successfully deleted {rows_to_delete} rows (rows {delete_start_index+1}-{delete_start_index+rows_to_delete})")
                            
                            # Update the last row position after deletion
                            last_row -= rows_to_delete
                        except Exception as e:
                            print(f"Error while deleting rows: {e}")
            
            # 5. Calculate the position to append data
            start_row = max(last_row + 1, data_start_row)
            
        except Exception as e:
            print(f"Error while determining append position: {e}")
            # Fallback to appending after header
            start_row = header_row + 1
            
        print(f"Will append data starting at row {start_row}")
    else:
        # In non-append mode, we start at the original position specified in start_cell
        start_row = header_row
    
    # Calculate the end row after all operations
    end_row = start_row + rows_to_append - 1
    
    # 6. Check and resize the grid if necessary to prevent errors
    resize_needed = False
    resize_requests = []
    
    if end_row >= current_max_rows:
        # Add buffer rows (1% more than needed, minimum of 10 extra rows)
        new_row_count = max(end_row + 10, int(end_row * 1.01))
        resize_requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "rowCount": new_row_count
                    }
                },
                "fields": "gridProperties.rowCount"
            }
        })
        print(f"Need to resize sheet from {current_max_rows} to {new_row_count} rows")
        resize_needed = True
    
    if end_col_index > current_max_cols:
        # Add buffer columns (1% more than needed, minimum of 3 extra columns)
        new_col_count = max(end_col_index + 3, int(end_col_index * 1.01))
        resize_requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "columnCount": new_col_count
                    }
                },
                "fields": "gridProperties.columnCount"
            }
        })
        print(f"Need to resize sheet from {current_max_cols} to {new_col_count} columns")
        resize_needed = True
    
    if resize_needed:
        try:
            sheet.batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": resize_requests}
            ).execute()
            print("Sheet grid successfully resized to accommodate new data")
        except Exception as e:
            print(f"Error resizing grid: {e}")

    # Handle existing filters
    existing_filter = None
    if handle_existing_filters:
        try:
            filter_metadata = sheet.get(spreadsheetId=spreadsheet_id, ranges=[sheet_name], fields='sheets/basicFilter').execute()
            existing_filter = filter_metadata['sheets'][0].get('basicFilter')
            
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
        except Exception as e:
            print(f"Error handling filters: {e}")
    
    # 7. Prepare the data for update
    data_range = f'{sheet_name}!{start_col}{start_row}:{end_col}{end_row}'
    print(f"Updating data in range: {data_range}")

    # Convert DataFrame to list of lists
    values = []
    
    if include_header:
        # Process header row
        header_values = df.columns.tolist()
        
        # Ensure header can accommodate formula column
        if formula is not None:
            if formula_position == 0:
                header_values = [''] + header_values
            elif formula_position == -1 or formula_position >= len(header_values):
                header_values = header_values + ['']
            else:
                header_values.insert(formula_position, '')
                
        values.append(header_values)
    
    # Process data rows with careful error handling for formulas
    for idx, (_, row) in enumerate(df.iterrows()):
        try:
            # Convert row values with proper serialization
            row_values = [serialize_for_sheets(val) for val in row]
            
            # Handle formula if specified
            if formula is not None:
                # Calculate the actual row number in the sheet
                sheet_row = start_row + idx + (1 if include_header else 0)
                
                try:
                    # Process formula based on type
                    if callable(formula):
                        formula_cell = formula(sheet_row)
                    else:
                        formula_cell = formula.format(sheet_row)
                except Exception as e:
                    print(f"Error processing formula for row {sheet_row}: {e}")
                    formula_cell = f"ERROR: {str(e)}"
                
                # Insert formula at the specified position
                if formula_position == 0:
                    row_values = [formula_cell] + row_values
                elif formula_position == -1 or formula_position >= len(row_values):
                    row_values = row_values + [formula_cell]
                else:
                    row_values.insert(formula_position, formula_cell)
            
            values.append(row_values)
        except Exception as e:
            print(f"Error processing row {idx}: {e}")
            # Add a placeholder row with error message
            error_row = ["ERROR processing row"] * total_cols
            values.append(error_row)
    
    # 8. Update the sheet with prepared data
    body = {'values': values}
    
    try:
        result = sheet.values().update(
            spreadsheetId=spreadsheet_id,
            range=data_range,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        print(f"{result.get('updatedCells')} cells updated successfully")
    except Exception as e:
        print(f"Error updating cells: {e}")
        return False

    # Only apply formatting if not in append mode
    if not append_mode:
        try:
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
    
            # Clear everything below the new data
            current_max_rows = sheet_metadata['sheets'][0]['properties']['gridProperties']['rowCount']
            if end_row < current_max_rows:
                clear_request = {
                    "requests": [
                        {
                            "updateCells": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": end_row,
                                    "endRowIndex": current_max_rows,
                                    "startColumnIndex": ord(start_col) - ord('A'),
                                    "endColumnIndex": ord(end_col) - ord('A') + 1
                                },
                                "fields": "userEnteredValue"
                            }
                        }
                    ]
                }
                sheet.batchUpdate(spreadsheetId=spreadsheet_id, body=clear_request).execute()
                print(f"Cleared rows from {end_row + 1} to {current_max_rows} in columns {start_col} to {end_col}")
        except Exception as e:
            print(f"Error applying formatting: {e}")

    # Reapply filter if needed
    if handle_existing_filters and existing_filter:
        try:
            # Reapply filter to the data range
            filter_start_row = header_row - 1  # 0-indexed for API
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
    
            if 'criteria' in existing_filter:
                filter_request["requests"][0]["setBasicFilter"]["filter"]["criteria"] = existing_filter["criteria"]
    
            sheet.batchUpdate(spreadsheetId=spreadsheet_id, body=filter_request).execute()
            print(f"Reapplied filter to range {sheet_name}!{start_col}{filter_start_row+1}:{end_col}{end_row}")
        except Exception as e:
            print(f"Error reapplying filter: {e}")
    
    return True

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