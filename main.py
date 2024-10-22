import subprocess
import time
import csv
import os

# Path to the scripts
CREATE_HOST_SCRIPT = 'createhost.py'
CONNECT_ADB_SCRIPT = 'connect_to_adb.py'
MONITORING_ADB_SCRIPT = 'monitoring_adb.py'

def run_script(script_name):
    """Run a Python script and return its output."""
    result = subprocess.run(['python', script_name], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running {script_name}: {result.stderr.strip()}")
    else:
        print(f"{script_name} output:\n{result.stdout.strip()}")

def check_hosts_created():
    """Check if hosts have been created successfully by reading the CSV."""
    csv_file_path = 'Poly,yealink,logi-host.csv'
    if not os.path.exists(csv_file_path):
        print(f"CSV file not found: {csv_file_path}")
        return False
    
    with open(csv_file_path, mode='r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        for row in reader:
            hostname = row.get('Host', '').strip()
            if not hostname:
                print(f"Skipping row due to missing hostname: {row}")
                continue
            
            # Here you might want to implement a check to see if the host exists in Zabbix
            # For now, we will just assume the host exists if the CSV was processed successfully
            print(f"Host '{hostname}' is to be created.")
    return True  # Return true for this simplified check

def main():
    # Step 1: Run the createhost.py script
    print("Running createhost.py...")
    run_script(CREATE_HOST_SCRIPT)
    
    # Step 2: Check if hosts were created successfully
    if not check_hosts_created():
        print("Hosts were not created successfully. Exiting.")
        return
    
    # Step 3: Start connecting to ADB every second
    print("Starting connect_to_adb.py...")
    while True:
        run_script(CONNECT_ADB_SCRIPT)
        time.sleep(1)  # Wait for 1 second before the next iteration

        # Run monitoring_adb.py once after connecting to ADB
        print("Running monitoring_adb.py...")
        run_script(MONITORING_ADB_SCRIPT)

if __name__ == "__main__":
    main()
