import requests
import re
import os
import sys # For sys.exit()

# --- Configuration and Setup for Cloudflare ---
print("Starting script: Cloudflare IP Updater")

CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_ZONE_ID = os.getenv('CLOUDFLARE_ZONE_ID')

if not CLOUDFLARE_API_TOKEN:
    print("Error: CLOUDFLARE_API_TOKEN environment variable not set.")
    sys.exit(1)
if not CLOUDFLARE_ZONE_ID:
    print("Error: CLOUDFLARE_ZONE_ID environment variable not set.")
    sys.exit(1)

BASE_DOMAIN_NAME = "freeus.us.to"
TARGET_SUBDOMAINS = [f"sp{i}.{BASE_DOMAIN_NAME}" for i in range(10, 21)] # sp10 to sp20

CLOUDFLARE_HEADERS = {
    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
    "Content-Type": "application/json"
}

print("Cloudflare configuration loaded.")
print(f"Zone ID: {CLOUDFLARE_ZONE_ID}")
print(f"Base Domain: {BASE_DOMAIN_NAME}")
print(f"Target Subdomains: {TARGET_SUBDOMAINS}")

# --- Existing IP Collection Logic ---
# 目标URL列表
urls = [
    'https://cf.vvhan.com/',
    'https://ip.164746.xyz'
]
ip_pattern = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
all_ips = []

print("Starting IP collection phase...") 
for url in urls: 
    print(f"Fetching IPs from: {url}") 
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        page_content = response.text
        ip_matches = re.findall(ip_pattern, page_content)
        all_ips.extend(ip_matches)
        print(f"Found {len(ip_matches)} potential IPs from {url}.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while processing {url}: {e}")

unique_ips = []
seen_ips = set()
for ip in all_ips:
    if ip not in seen_ips:
        unique_ips.append(ip)
        seen_ips.add(ip)

if os.path.exists('ip.txt'):
    try:
        os.remove('ip.txt')
        print("Removed existing ip.txt.")
    except OSError as e:
        print(f"Error removing existing ip.txt: {e}")

try:
    with open('ip.txt', 'w') as file:
        for ip in unique_ips:
            file.write(f"{str(ip)}\n")
    print(f"{len(unique_ips)} unique IP addresses were collected and saved to ip.txt.")
except IOError as e:
    print(f"Error writing to ip.txt: {e}")
except Exception as e:
    print(f"An unexpected error occurred while writing to file: {e}")

# --- Cloudflare DNS Update Logic ---
print("Starting Cloudflare DNS update phase...")

if not unique_ips:
    print("No unique IPs collected. Skipping DNS update process.")
else:
    print(f"Found {len(unique_ips)} unique IPs. Proceeding with DNS updates for up to {len(TARGET_SUBDOMAINS)} subdomains.")
    
    num_ips_to_process = min(len(unique_ips), len(TARGET_SUBDOMAINS))

    for i in range(num_ips_to_process):
        current_subdomain = TARGET_SUBDOMAINS[i]
        ip_to_assign = unique_ips[i]
        record_id = None # Reset for each subdomain

        print(f"Processing subdomain: {current_subdomain} with IP: {ip_to_assign}")

        # Fetch Existing DNS Record
        fetch_url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records?type=A&name={current_subdomain}"
        print(f"Attempting to fetch existing DNS record for {current_subdomain}...")
        try:
            response = requests.get(fetch_url, headers=CLOUDFLARE_HEADERS, timeout=10)
            if response.status_code == 404:
                print(f"No existing 'A' record found for {current_subdomain} (404). Will attempt to create.")
                record_id = None
            elif response.status_code == 401 or response.status_code == 403:
                print(f"Authorization error ({response.status_code}) fetching DNS record for {current_subdomain}. Check API token and permissions. Skipping this subdomain.")
                print(f"Response: {response.text}")
                continue
            else:
                response.raise_for_status()
                records_data = response.json()
                if records_data.get("success") and records_data.get("result"):
                    if records_data["result"]:
                        record_id = records_data["result"][0]["id"]
                        print(f"Found existing record for {current_subdomain} with ID: {record_id}")
                    else:
                        print(f"No existing 'A' record found for {current_subdomain} (API success, empty result).")
                        record_id = None
                else:
                    print(f"Failed to fetch valid record data for {current_subdomain}. Response: {records_data}")
                    record_id = None

        except requests.exceptions.HTTPError as e:
            print(f"HTTP error fetching DNS record for {current_subdomain}: {e}")
            if record_id is not None:
                print("Proceeding without a valid record_id due to HTTP error during fetch.")
                record_id = None
        except requests.exceptions.RequestException as e:
            print(f"Network error fetching DNS record for {current_subdomain}: {e}")
            continue
        except ValueError as e: # Includes JSONDecodeError
            print(f"Error parsing JSON response for {current_subdomain}: {e}")
            record_id = None


        # Data for DNS Update/Create
        dns_payload = {
            "type": "A",
            "name": current_subdomain,
            "content": ip_to_assign,
            "ttl": 3600,
            "proxied": False
        }

        if record_id:
            # Update Existing Record
            update_url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records/{record_id}"
            print(f"Attempting to update record for {current_subdomain} (ID: {record_id}) with IP: {ip_to_assign}...")
            try:
                response = requests.put(update_url, json=dns_payload, headers=CLOUDFLARE_HEADERS, timeout=10)
                response.raise_for_status()
                update_result = response.json()
                if update_result.get("success"):
                    print(f"Successfully updated DNS record for {current_subdomain} to {ip_to_assign}.")
                else:
                    print(f"Failed to update DNS record for {current_subdomain}. Response: {update_result}")
            except requests.exceptions.RequestException as e:
                print(f"Error updating DNS record for {current_subdomain}: {e}")
            except ValueError as e:
                print(f"Error parsing JSON response during update for {current_subdomain}: {e}")
        else:
            # Create New Record
            create_url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records"
            print(f"Attempting to create new record for {current_subdomain} with IP: {ip_to_assign}...")
            try:
                response = requests.post(create_url, json=dns_payload, headers=CLOUDFLARE_HEADERS, timeout=10)
                response.raise_for_status()
                create_result = response.json()
                if create_result.get("success"):
                    print(f"Successfully created DNS record for {current_subdomain} with IP {ip_to_assign}.")
                else:
                    print(f"Failed to create DNS record for {current_subdomain}. Response: {create_result}")
            except requests.exceptions.RequestException as e:
                print(f"Error creating DNS record for {current_subdomain}: {e}")
            except ValueError as e:
                print(f"Error parsing JSON response during creation for {current_subdomain}: {e}")
    
    print("Cloudflare DNS update phase completed.")

print("Script finished.")
