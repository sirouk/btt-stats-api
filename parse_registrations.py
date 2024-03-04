import os
import re
import csv
from datetime import datetime

# Configuration
log_directory = os.path.expanduser("~")
output_csv_path = os.path.join(log_directory, 'registrations.csv')
log_pattern = re.compile(r'btt_register_sn(\d+)_ck(\d+)-hk(\d+)\.log')

# CSV Headers - Including 'CreationTime' for the log file creation timestamp
csv_headers = ['Subnet', 'ColdKey', 'HotKey', 'Cost', 'Line', 'ModifiedTime', 'Filename']

def load_existing_entries():
    existing_entries = set()
    if os.path.exists(output_csv_path):
        with open(output_csv_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Reference columns by name
                entry_key = (row['Subnet'], row['ColdKey'], row['HotKey'], row['Cost'], row['Line'])
                existing_entries.add(entry_key)
    return existing_entries

def parse_log_file(filepath):
    entries = []
    with open(filepath, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    for i, line in enumerate(lines):
        if '[32mRegistered' in line:
            for j in range(i-1, -1, -1):
                if "The cost to register" in lines[j]:
                    cost_line = lines[j]
                    break
            else:
                cost_line = "Cost not found"

            cost_match = re.search(r'τ([\d.]+)', cost_line)
            cost = cost_match.group(1) if cost_match else "N/A"
            entries.append((cost, i+1))
    return entries

def append_to_csv(subnet, coldkey, hotkey, entries, filepath, existing_entries):
    file_stats = os.stat(filepath)
    creation_time = datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
    modified_time = datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    filename = os.path.basename(filepath)

    with open(output_csv_path, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_headers)
        for cost, line in entries:
            new_entry = {
                'Subnet': subnet, 
                'ColdKey': coldkey, 
                'HotKey': hotkey,
                'Cost': cost, 
                'Line': str(line), 
                'ModifiedTime': modified_time,
                'Filename': filename
            }
            uniqueness_key = (subnet, coldkey, hotkey, cost, str(line))
            if uniqueness_key not in existing_entries:
                writer.writerow(new_entry)
                existing_entries.add(uniqueness_key)

def main():
    if not os.path.exists(output_csv_path):
        with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_headers)
            writer.writeheader()

    existing_entries = load_existing_entries()

    for filename in os.listdir(log_directory):
        match = log_pattern.match(filename)
        if match:
            subnet, coldkey, hotkey = match.groups()
            filepath = os.path.join(log_directory, filename)
            entries = parse_log_file(filepath)
            if entries:
                append_to_csv(subnet, coldkey, hotkey, entries, filepath, existing_entries)

    print("Processing complete.")

if __name__ == '__main__':
    main()
