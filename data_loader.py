import pandas as pd
import os
import sys
import json
from datetime import datetime, time


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

PRICE_CATS = ['Cat A', 'Cat B', 'Cat C', 'Cat D', 'Cat E', 'Cat F', 'Cat G', 'Cat H', 'Cat I', 'Cat J']

NON_LA_ZONES = {'OKC', 'New York', 'Columbus', 'Nashville', 'St. Louis', 'San Jos\u00e9', 'San Diego'}

VENUE_COORDS = {
    "2028 Stadium": (33.9534, -118.3390),
    "Intuit Dome": (33.9425, -118.3412),
    "LA Memorial Coliseum": (34.0141, -118.2879),
    "Exposition Park Stadium": (34.0163, -118.2862),
    "Galen Center": (34.0232, -118.2841),
    "Dodger Stadium": (34.0739, -118.2400),
    "DTLA Arena": (34.0430, -118.2590),
    "Peacock Theater": (34.0453, -118.2669),
    "LA Convention Center Hall 1": (34.0400, -118.2695),
    "LA Convention Center Hall 2": (34.0397, -118.2680),
    "LA Convention Center Hall 3": (34.0394, -118.2665),
    "Valley Complex 1": (34.2285, -118.5368),
    "Valley Complex 2": (34.2275, -118.5358),
    "Valley Complex 3": (34.2265, -118.5348),
    "Valley Complex 4": (34.2255, -118.5338),
    "Carson Center Court": (33.8661, -118.2614),
    "Carson Court 1": (33.8651, -118.2604),
    "Carson Court 2": (33.8641, -118.2594),
    "Carson Courts 3-11": (33.8631, -118.2584),
    "Carson Field": (33.8621, -118.2574),
    "Carson Stadium": (33.8661, -118.2614),
    "Carson Velodrome": (33.8671, -118.2624),
    "Long Beach Aquatics Center": (33.7866, -118.1870),
    "Long Beach Arena": (33.7604, -118.1893),
    "Long Beach Climbing Theater": (33.7614, -118.1883),
    "Long Beach Target Shooting Hall": (33.7624, -118.1873),
    "Alamitos Beach Stadium": (33.7594, -118.1850),
    "Belmont Shore": (33.7540, -118.1500),
    "Marine Stadium": (33.7610, -118.1330),
    "Venice Beach": (33.9850, -118.4695),
    "Venice Beach Boardwalk": (33.9860, -118.4705),
    "Rose Bowl Stadium": (34.1613, -118.1676),
    "Rose Bowl Aquatics Center": (34.1620, -118.1660),
    "Santa Anita Park": (34.1361, -118.0434),
    "Riviera Country Club": (34.0500, -118.4300),
    "Fairgrounds Cricket Stadium": (34.0553, -117.7520),
    "Comcast Squash Center": (34.1381, -118.3534),
    "Industry Hills MTB Course": (34.0025, -117.9220),
    "Port of Los Angeles": (33.7350, -118.2753),
    "Whittier Narrows Clay Center": (34.0240, -118.0470),
    "Honda Center": (33.8078, -117.8764),
    "Trestles State Beach": (33.3825, -117.5883),
}

SAVE_FILE = "my_selections.json"
TIERS_FILE = "my_tiers.json"
EXCLUDED_FILE = "my_excluded.json"
SAVES_DIR = "saved_profiles"


def find_excel():
    # Check multiple locations: script dir, exe dir, _internal dir
    search_dirs = [get_base_dir()]
    if getattr(sys, "frozen", False):
        internal = os.path.join(os.path.dirname(sys.executable), "_internal")
        if os.path.isdir(internal):
            search_dirs.append(internal)
    for d in search_dirs:
        for f in os.listdir(d):
            if f.endswith(".xlsx") and "LA 2028" in f:
                return os.path.join(d, f)
    return os.path.join(get_base_dir(), "LA 2028 Session Table - Shareable.xlsx")


def load_events(filepath=None):
    if filepath is None:
        filepath = find_excel()
    df = pd.read_excel(filepath, sheet_name="Event List - Sorted by SPORT")
    df.columns = [c.replace("\n", " ") for c in df.columns]

    events = []
    for _, row in df.iterrows():
        prices = {}
        for cat in PRICE_CATS:
            val = row.get(cat, "-")
            if pd.notna(val) and val != "-" and val != "":
                try:
                    prices[cat] = float(val)
                except (ValueError, TypeError):
                    pass

        start_str = str(row.get("Start Time", ""))
        end_str = str(row.get("End Time", ""))
        start_time = parse_time(start_str)
        end_time = parse_time(end_str)

        date_val = row.get("Date")
        if pd.notna(date_val):
            if isinstance(date_val, str):
                try:
                    date_val = datetime.strptime(date_val, "%Y-%m-%d").date()
                except ValueError:
                    date_val = None
            else:
                try:
                    date_val = date_val.date()
                except AttributeError:
                    date_val = None
        else:
            date_val = None

        zone = str(row.get("Zone", "")) if pd.notna(row.get("Zone")) else ""

        event = {
            "sport": str(row.get("Sport", "")) if pd.notna(row.get("Sport")) else "",
            "venue": str(row.get("Venue", "")) if pd.notna(row.get("Venue")) else "",
            "zone": zone,
            "session_code": str(row.get("Session Code", "")) if pd.notna(row.get("Session Code")) else "",
            "date": date_val,
            "games_day": row.get("Games Day") if pd.notna(row.get("Games Day")) else None,
            "session_type": str(row.get("Session Type", "")) if pd.notna(row.get("Session Type")) else "",
            "description": str(row.get("Session Description", "")) if pd.notna(row.get("Session Description")) else "",
            "start_time": start_time,
            "end_time": end_time,
            "prices": prices,
            "is_la": zone not in NON_LA_ZONES and zone != "TBD",
        }
        events.append(event)

    return events


def parse_time(s):
    s = str(s).strip()
    if s in ("TBD", "nan", "", "None"):
        return None
    try:
        parts = s.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def get_unique_sports(events):
    return sorted(set(e["sport"] for e in events if e["sport"]))


def get_unique_zones(events):
    return sorted(set(e["zone"] for e in events if e["zone"]))


def get_unique_venues(events):
    return sorted(set(e["venue"] for e in events if e["venue"]))


def get_unique_dates(events):
    return sorted(set(e["date"] for e in events if e["date"]))


def get_unique_session_types(events):
    return sorted(set(e["session_type"] for e in events if e["session_type"]))


def save_selections(selections, filename=SAVE_FILE):
    filepath = os.path.join(get_base_dir(), filename)
    data = {}
    for code, sel in selections.items():
        data[code] = {
            "category": sel.get("category", ""),
            "price": sel.get("price", 0),
            "priority": sel.get("priority", "want"),
        }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load_selections(filename=SAVE_FILE):
    filepath = os.path.join(get_base_dir(), filename)
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r") as f:
        return json.load(f)


def save_tiers(tiers, filename=TIERS_FILE):
    filepath = os.path.join(get_base_dir(), filename)
    with open(filepath, "w") as f:
        json.dump(tiers, f, indent=2)


def load_tiers(filename=TIERS_FILE):
    filepath = os.path.join(get_base_dir(), filename)
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r") as f:
        return json.load(f)


def save_excluded(excluded, filename=EXCLUDED_FILE):
    filepath = os.path.join(get_base_dir(), filename)
    with open(filepath, "w") as f:
        json.dump(list(excluded), f, indent=2)


def load_excluded(filename=EXCLUDED_FILE):
    filepath = os.path.join(get_base_dir(), filename)
    if not os.path.exists(filepath):
        return set()
    with open(filepath, "r") as f:
        return set(json.load(f))


def get_saves_dir():
    d = os.path.join(get_base_dir(), SAVES_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def save_profile(name, selections, tiers, excluded):
    d = get_saves_dir()
    data = {
        "selections": selections,
        "tiers": tiers,
        "excluded": list(excluded),
    }
    with open(os.path.join(d, f"{name}.json"), "w") as f:
        json.dump(data, f, indent=2)


def load_profile(name):
    d = get_saves_dir()
    filepath = os.path.join(d, f"{name}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r") as f:
        data = json.load(f)
    return {
        "selections": data.get("selections", {}),
        "tiers": data.get("tiers", {}),
        "excluded": set(data.get("excluded", [])),
    }


def list_profiles():
    d = get_saves_dir()
    profiles = []
    for f in os.listdir(d):
        if f.endswith(".json"):
            profiles.append(f[:-5])
    return sorted(profiles)


def delete_profile(name):
    d = get_saves_dir()
    filepath = os.path.join(d, f"{name}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
