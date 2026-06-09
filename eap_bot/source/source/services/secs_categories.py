# source/services/secs_categories.py

SECS_STREAM_CATEGORIES = {
    1: "Equipment Status",
    2: "Equipment Control",
    3: "Material Status",
    4: "Material Control",
    5: "Exception Handling",
    6: "Data Collection",
    7: "Process Program Management",
    8: "Control Program Transfer",
    9: "System Errors",
    10: "Terminal Services",
    11: "Host File Services",
    12: "Wafer Mapping",
    13: "Data Set Transfers",
    14: "Object Services",
    15: "Recipe Management",
    16: "Processing Management",
    17: "Equipment Control and Diagnostics",
    18: "Subsystem Control and Data",
}

def get_stream_category(stream_id: int) -> str:
    """Return the SECS/GEM category string for a given Stream ID."""
    return SECS_STREAM_CATEGORIES.get(stream_id, f"Stream {stream_id}")
