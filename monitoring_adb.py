import subprocess
import logging
import csv
import time
import datetime
import os
import glob
import threading

# Constants
CSV_FILE_PATH = r'Poly,yealink,logi-host.csv'  # Your CSV file path
ZABBIX_SERVER = '10.39.1.102'  # Replace with your Zabbix server
DATA_FOLDER = 'data'  # Folder to store logcat and bugreport files

#package
 # Collect memory usage for important packages
packages = {
            "Teams": "com.microsoft.skype.teams.ipphone",
            "Admin Agent": "com.microsoft.teams.ipphone.admin.agent",
            "Company Portal": "com.microsoft.windowsintune.companyportal"
        }

# Setup logging
logging.basicConfig(filename='device_monitor.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Create the data folder if it does not exist
os.makedirs(DATA_FOLDER, exist_ok=True)

def run_command(command):
    """Run a shell command and return the output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Command '{command}' failed with error: {e.stderr.strip()}")
        return None

def get_network_usage(udid):
    """Get network RX and TX bytes from the device, prioritizing Ethernet over WLAN."""
    output = run_command(f"adb -s {udid} shell cat /proc/net/dev")
    if output:
        eth_rx, eth_tx = 0, 0
        wlan_rx, wlan_tx = 0, 0
        
        for line in output.splitlines():
            parts = line.split()
            if "eth0" in line:  # Check for the eth0 interface only
                eth_rx = int(parts[1])  # Received bytes
                eth_tx = int(parts[9])  # Transmitted bytes
            elif "wlan0" in line:  # Check for the wlan0 interface
                wlan_rx = int(parts[1])  # Received bytes
                wlan_tx = int(parts[9])  # Transmitted bytes

        # Prioritize Ethernet over WLAN
        if eth_rx > 0 or eth_tx > 0:
            return eth_rx, eth_tx
        elif wlan_rx > 0 or wlan_tx > 0:
            return wlan_rx, wlan_tx

    logging.warning(f"No network data found for device {udid}")
    return 0, 0  # Default to 0 if nothing found

def get_memory_usage(udid, package_name):
    """Get memory usage for the specified package on the device."""
    output = run_command(f"adb -s {udid} shell dumpsys meminfo {package_name}")
    if output:
        for line in output.splitlines():
            if "TOTAL" in line:
                memory_usage = int(line.split()[1])
                return memory_usage
    logging.warning(f"Memory usage data not found for {package_name} on device {udid}")
    return 0

def get_cpu_usage(udid):
    """Get the current CPU usage for the device."""
    output = run_command(f"adb -s {udid} shell dumpsys cpuinfo")
    if output:
        total_cpu_line = [line for line in output.splitlines() if "TOTAL" in line]
        if total_cpu_line:
            try:
                cpu_usage = float(total_cpu_line[0].split('%')[0].strip())
                return max(cpu_usage, 0.0)  # Ensure no negative CPU usage is returned
            except ValueError as e:
                logging.error(f"Error parsing CPU usage for {udid}: {str(e)}")
                return 0.0
    logging.warning(f"CPU usage data not found for device {udid}")
    return 0.0

def get_battery_health(udid):
    """Get the battery level from the device."""
    output = run_command(f"adb -s {udid} shell dumpsys battery")
    if output:
        for line in output.splitlines():
            if "health" in line:
                get_battery_health = int(line.split(":")[1].strip())
                return get_battery_health
    logging.warning(f"Battery data not found for device {udid}")
    return 0

def get_uptime(udid):
    """Get the network uptime for the device."""
    output = run_command(f"adb -s {udid} shell cat /proc/uptime")
    if output:
        uptime_seconds = float(output.split()[0])
        return uptime_seconds
    logging.warning(f"Uptime data not found for device {udid}")
    return 0.0
def analyze_memory_data(memory_data, hostname, udid):
    """Analyze memory data and check for potential leaks, sending results to Zabbix."""
    print("\n--- Analyzing Memory Data for Potential Leaks ---\n")
    
    for name, mem_usages in memory_data.items():
        print(f"[{name}] Memory Usage Data: {mem_usages} KB")
        
        if len(mem_usages) > 1:
            if mem_usages[-1] > mem_usages[0]:  # Check if there's an increase
                increase_percentage = ((mem_usages[-1] - mem_usages[0]) / mem_usages[0]) * 100
                print(f"Memory usage increased by {increase_percentage:.2f}% over the monitoring period.")
                logging.info(f"Memory usage for {name} increased by {increase_percentage:.2f}%")
                
                zabbix_key = f"memory.leak[{packages[name]}]"  # Zabbix key for memory leak
                send_to_zabbix(hostname, zabbix_key, increase_percentage)  # Send percentage increase
            else:
                print(f"No memory leak detected for {name}. Memory usage is stable or decreased.")
                send_to_zabbix(hostname, f"memory.leak[{packages[name]}]", -1)  # Send -1 or a value to indicate no leak
        else:
            logging.warning(f"Insufficient memory data for {name}, unable to analyze.")
            send_to_zabbix(hostname, f"memory.leak[{packages[name]}]", 0)  # Indicate no analysis could be done


def send_to_zabbix(hostname, key, value):
    """Send data to Zabbix."""
    try:
        command = f'zabbix_sender -z {ZABBIX_SERVER} -s "{hostname}" -k "{key}" -o {value}'
        result = run_command(command)
        if result:
            logging.info(f"Sent to Zabbix: {hostname} - {key} = {value}")
        else:
            logging.error(f"Failed to send data to Zabbix for {hostname}: {key} = {value}")
    except Exception as e:
        logging.error(f"Failed to send data to Zabbix for {hostname}: {str(e)}")

def collect_logcat(udid, hostname):
    """Collect logcat data from the device."""
    output = run_command(f"adb -s {udid} logcat -d")
    if output:
        timestamp = datetime.datetime.now().isoformat().replace(":", "-")  # Replace colons with hyphens
        logcat_filename = os.path.join(DATA_FOLDER, f"logcat_{udid}_{timestamp}.txt")
        
        with open(logcat_filename, 'w', encoding='utf-8') as log_file:
            log_file.write(output)
        logging.info(f"Logcat collected for {udid} and saved to {logcat_filename}")

        # Send logcat collection timestamp to Zabbix
        timestamp_minutes = int(time.time() / 60)  # Convert to minutes since epoch
        send_to_zabbix(hostname, "logcat.collection.timestamp", timestamp_minutes)

        return logcat_filename
    else:
        logging.warning(f"Failed to collect logcat for {udid}")
    return None

def collect_bugreport(udid, hostname):
    """Collect bugreport data from the device."""
    # Create the data folder if it doesn't exist
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER)

    # Run the bugreport command
    command = f"adb -s {udid} bugreport {DATA_FOLDER}"  # Specify the data folder as the destination
    subprocess.run(command, shell=True, check=True)

    # Get the path of the generated bug report
    list_of_files = glob.glob(os.path.join(DATA_FOLDER, '*'))
    bugreport_path = max(list_of_files, key=os.path.getctime)  # Get the most recent file

    # Create the new filename based on the current timestamp
    timestamp = datetime.datetime.now().isoformat().replace(":", "-")  # Replace colons with hyphens
    new_file_name = f"bugreport_{hostname}_{timestamp}.zip"  # New filename
    new_file_path = os.path.join(DATA_FOLDER, new_file_name)

    # Rename the bug report file
    os.rename(bugreport_path, new_file_path)

    logging.info(f"Bugreport collected for {udid} and saved to {new_file_path}")

    # Send bugreport collection timestamp to Zabbix
    timestamp_minutes = int(time.time() / 60)  # Convert to minutes since epoch
    send_to_zabbix(hostname, "bugreport.collection.timestamp", timestamp_minutes)

    return new_file_path

def send_device_online_status(hostname, is_online):
    """Send device online/offline status to Zabbix."""
    online_status = 1 if is_online else 0
    send_to_zabbix(hostname, "device.online.status", online_status)

def is_device_online(udid):
    """Check if the device is online."""
    if not udid:
        logging.error("UDID is missing, cannot check device status")
        return False

    # Check if the device responds to adb get-state
    device_status = run_command(f"adb -s {udid} get-state")
    if device_status == "device":
        return True
    else:
        logging.info(f"Device {udid} is offline with status: {device_status}")
        return False

def process_device_main(udid, hostname):
    """Process network, memory, CPU, and battery usage for a given device."""
    if is_device_online(udid):
        # Get network usage
        rx_bytes, tx_bytes = get_network_usage(udid)
        if rx_bytes > 0 and tx_bytes > 0:
            send_to_zabbix(hostname, "network.rx.bytes", rx_bytes)
            send_to_zabbix(hostname, "network.tx.bytes", tx_bytes)

        # Get network uptime
        uptime_seconds = get_uptime(udid)
        if uptime_seconds > 0:
            send_to_zabbix(hostname, "device.uptime", uptime_seconds)

        # Get CPU usage
        cpu_usage = get_cpu_usage(udid)
        if cpu_usage > 0:
            send_to_zabbix(hostname, "cpu.usage", cpu_usage)

        memory_data = {name: [] for name in packages.keys()}  # To store memory usage over time
        
        # Monitor memory usage over the desired period (e.g., 5 intervals, checking every 60 seconds)
        check_duration = 5  # Number of times to check memory usage
        check_interval = 60  # Time (in seconds) between each check

        for i in range(check_duration):
            for package_name, package_id in packages.items():
                memory_usage = get_memory_usage(udid, package_id)
                if memory_usage > 0:
                    memory_data[package_name].append(memory_usage)
                    send_to_zabbix(hostname, f"memory.usage[{package_id}]", memory_usage)
            
            time.sleep(check_interval)

        # Analyze memory data for potential leaks and send results to Zabbix
        analyze_memory_data(memory_data, hostname, udid)

        # Get battery level
        battery_level = get_battery_health(udid)
        if battery_level > 0:
            send_to_zabbix(hostname, "battery.health", battery_level)

        # Send device online status
        send_device_online_status(hostname, True)
    else:
        send_device_online_status(hostname, False)

def process_device_logs(udid, hostname):
    """Collect logcat and bugreport for a given device."""
    if is_device_online(udid):
        collect_logcat(udid, hostname)
        collect_bugreport(udid, hostname)

def main_loop():
    """Main function to read devices from CSV and monitor them every 10 seconds."""
    while True:
        with open(CSV_FILE_PATH, newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            threads = []
            for row in reader:
                if 'Host' in row and 'udid' in row:
                    udid = row['udid'].strip()
                    hostname = row['Host'].strip()
                    if udid and hostname:
                        thread = threading.Thread(target=process_device_main, args=(udid, hostname))
                        threads.append(thread)
                        thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

        time.sleep(10)  # Wait for 10 seconds before the next iteration

def log_collection_loop():
    """Function to collect logs every 10 minutes."""
    while True:
        with open(CSV_FILE_PATH, newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            threads = []
            for row in reader:
                if 'Host' in row and 'udid' in row:
                    udid = row['udid'].strip()
                    hostname = row['Host'].strip()
                    if udid and hostname:
                        thread = threading.Thread(target=process_device_logs, args=(udid, hostname))
                        threads.append(thread)
                        thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

        time.sleep(600)  # Wait for 10 minutes before the next iteration

if __name__ == "__main__":
    # Start the main monitoring loop in a separate thread
    main_thread = threading.Thread(target=main_loop)
    main_thread.start()

    # Start the log collection loop in the main thread
    log_collection_loop()