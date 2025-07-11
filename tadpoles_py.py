import os
import requests
import json
import time
from datetime import datetime

# CONFIG
# adjust the dates in the MAIN loop below
EMAIL = '@gmail.com'  # replace with your email
PASSWORD = 'password123' # replace with your password
KIDS = ['Boy', 'Girl', 'Baby']  # replace with the names of your kids as they appear in Tadpoles
DESTINATION_FOLDER = r'' # replace with the folder where you want to save the files
    # Example: DESTINATION_FOLDER = r'C:\Users\YourName\Tadpoles
LAT = '' # replace with your daycare's latitude
LNG = '' # replace with your daycare's longitude
TIMEZONE = '' # replace with your timezone, e.g., 'America/New_York'


session = requests.Session()

# These headers spoof the iPhone app
STANDARD_HEADERS = {
    'Host': 'www.tadpoles.com',
    'content-type': 'application/x-www-form-urlencoded; charset=utf-8',
    'accept': '*/*',
    'x-titanium-id': 'c5a5bca5-43c7-4b8f-b82a-fe1de0e4793c',
    'x-requested-with': 'XMLHttpRequest',
    'accept-language': 'en-us',
    'user-agent': 'Appcelerator Titanium/7.1.1 (iPhone/12.2; iOS; en_US;), Appcelerator Titanium/7.1.1 (iPhone/12.2; iOS; en_US;) (gzip)'
}


def login(email, password):
    data = {'service': 'tadpoles', 'email': email, 'password': password}
    r = session.post('https://www.tadpoles.com/auth/login', headers=STANDARD_HEADERS, data=data)
    r.raise_for_status()
    print("[*] Login successful")


def admit():
    data = {
        'state': 'client', 'mac': '00000000-0000-0000-0000-000000000000',
        'os_name': 'iphone', 'app_version': '8.10.24', 'ostype': '64bit',
        'tz': TIMEZONE, 'battery_level': '-1', 'locale': 'en',
        'logged_in': '0', 'device_id': '00000000-0000-0000-0000-000000000000', 'v': '2'
    }
    r = session.post('https://www.tadpoles.com/remote/v1/athome/admit', headers=STANDARD_HEADERS, data=data)
    r.raise_for_status()
    print("[*] Admit successful")


def events(year, month):
    cursor = ''
    all_events = []
    month = f"{int(month):02d}"

    while True:
        last_day = datetime(year, int(month), 1).replace(day=28).day
        earliest_ts = int(time.mktime(time.strptime(f"{year}-{month}-01 00:00:00", "%Y-%m-%d %H:%M:%S")))
        latest_ts = int(time.mktime(time.strptime(f"{year}-{month}-{last_day} 23:59:59", "%Y-%m-%d %H:%M:%S")))

        params = {
            'num_events': '100',
            'state': 'client',
            'direction': 'range',
            'earliest_event_time': earliest_ts,
            'latest_event_time': latest_ts,
            'cursor': cursor
        }

        r = session.get('https://www.tadpoles.com/remote/v1/events', headers=STANDARD_HEADERS, params=params)
        r.raise_for_status()
        j = r.json()
        all_events.extend(j.get('events', []))
        cursor = j.get('cursor', '')
        if not cursor:
            break

    print(f"[*] Found {len(all_events)} events")
    return all_events


def download_attachment(key, filename):
    url = f'https://www.tadpoles.com/remote/v1/attachment?key={key}'
    # This call either returns a redirect or a file
    resp = session.get(url, headers=STANDARD_HEADERS, allow_redirects=True, stream=True)

    if resp.status_code == 200 and 'content-type' in resp.headers and 'image' in resp.headers['content-type']:
        # Tadpoles directly returned the file
        print(f"[*] Direct download from Tadpoles")
        save_file(resp, filename)
    elif 300 <= resp.status_code < 400 and 'location' in resp.headers:
        # got a redirect URL (rare)
        signed_url = resp.headers['location']
        print(f"[*] Redirect to signed GCS URL")
        download_from_gcs(signed_url, filename)
    else:
        # maybe we already followed redirects and ended up at GCS
        if 'googleapis.com' in resp.url:
            print(f"[*] Already at signed GCS URL")
            download_from_gcs(resp.url, filename)
        else:
            print(f"[!] Unexpected response when fetching attachment key: {resp.status_code}")
            resp.raise_for_status()


def download_all_attachments(year, month):
    e_list = events(year, month)

    for idx, e in enumerate(e_list):
        if e.get('type') != 'Activity':
            continue

        for a in e.get('new_attachments', []):
            if e.get('member_display') not in KIDS:
                continue

            desc = e.get('comment', '')
            dt = datetime.fromtimestamp(e['event_time']).strftime('%Y-%m-%d %H.%M.%S')
            kid_name = e['member_display']

            ext = '.jpg' if a['mime_type'] == 'image/jpeg' else '.mp4'
            filename = os.path.join(
                DESTINATION_FOLDER,
                f"{dt} - Tadpoles - {kid_name}{ext}"
            )

            print(f"[{idx+1}/{len(e_list)}] Downloading {filename}")
            download_attachment(a['key'], filename)

            os.utime(filename, (e['event_time'], e['event_time']))

def save_file(response, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'wb') as f:
        for chunk in response.iter_content(1024):
            f.write(chunk)

def download_from_gcs(signed_url, filename):
    r2 = requests.get(signed_url, stream=True)
    r2.raise_for_status()
    save_file(r2, filename)

if __name__ == '__main__':
    login(EMAIL, PASSWORD)
    admit()
    # example: download one month or loop through many months
    for y, m in [(2024, 4), (2024, 5)]:  # adjust as needed
        download_all_attachments(y, m)
