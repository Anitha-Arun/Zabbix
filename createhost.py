import csv
from pyzabbix import ZabbixAPI

# Zabbix API connection details
ZABBIX_URL = 'http://Zabbix_ip/zabbix'
ZABBIX_USER = 'Admin'
ZABBIX_PASSWORD = '#giveurpassword'

# Connect to Zabbix API
zapi = ZabbixAPI(ZABBIX_URL)
zapi.login(ZABBIX_USER, ZABBIX_PASSWORD)

# Function to get group ID by name
def get_group_id(group_name):
    groups = zapi.hostgroup.get(filter={"name": group_name})
    if groups:
        return groups[0]['groupid']
    return None

# Function to get template ID by name
def get_template_id(template_name):
    templates = zapi.template.get(filter={"host": template_name})
    if templates:
        return templates[0]['templateid']
    return None

# Function to create a new host
def create_host(hostname, group_id, template_id):
    result = zapi.host.create(
        host=hostname,
        groups=[{"groupid": group_id}],
        templates=[{"templateid": template_id}],
        interfaces=[]  # No interfaces specified
    )
    if 'hostids' not in result:
        print(f"Failed to create host {hostname}. Response: {result}")
        return None
    return result['hostids'][0]

# Open CSV file
with open('Poly,yealink,logi-host.csv', mode='r', encoding='utf-8-sig') as file:
    reader = csv.DictReader(file)
    
    # Print the header to verify
    print("CSV Header:", reader.fieldnames)
    
    for row in reader:
        hostname = row.get('Host', '').strip()
        group_name = row.get('Group', '').strip()
        template_name = row.get('Template', '').strip()

        # Skip empty rows
        if not hostname or not group_name or not template_name:
            print(f"Skipping row due to missing data: {row}")
            continue

        # Debugging: Print fields
        print(f"Processing hostname: '{hostname}'")
        print(f"Group: '{group_name}'")
        print(f"Template: '{template_name}'")

        try:
            # Get group ID
            group_id = get_group_id(group_name) if group_name else None

            # Get template ID
            template_id = get_template_id(template_name) if template_name else None

            if group_id and template_id:
                # Create the host with specified group and template
                host_id = create_host(hostname, group_id, template_id)
                if host_id:
                    print(f"Created host {hostname} with ID {host_id}")
                else:
                    print(f"Failed to create host {hostname}")
            else:
                if not group_id:
                    print(f"Group '{group_name}' not found. Skipping host creation.")
                if not template_id:
                    print(f"Template '{template_name}' not found. Skipping host creation.")
        
        except Exception as e:
            print(f"Error while processing {hostname}: {e}")
