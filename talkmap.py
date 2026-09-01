# Leaflet cluster map of talk locations
#
# Standalone equivalent of talkmap.ipynb.
# Designed to NEVER crash the calling process — used as CI fallback when the
# notebook path fails.  Imports, geocoding, frontmatter parsing and getorg
# map-writing are all wrapped in try/except.
import sys
import time
import traceback

# ---- Imports (soft-fail) ----------------------------------------------------
try:
    import frontmatter
    import glob
    import getorg
    import os
    from geopy import Nominatim
    from geopy.exc import (
        GeocoderTimedOut,
        GeocoderServiceError,
        GeocoderQuotaExceeded,
        GeocoderUnavailable,
    )
    print("[talkmap.py] imports OK")
except Exception as ex:
    print(f"[talkmap.py][FATAL-IMPORT] {type(ex).__name__}: {ex}")
    traceback.print_exc()
    # Exit 0 so the surrounding CI step does not treat this as a pipeline failure
    sys.exit(0)


TIMEOUT = 10

# ---- Glob talk files --------------------------------------------------------
try:
    g = sorted(glob.glob("_talks/*.md"))
    print(f"[talkmap.py] Found {len(g)} talk file(s): {g}")
except Exception as ex:
    print(f"[talkmap.py] glob error: {ex}")
    g = []

# ---- Geocoder ---------------------------------------------------------------
geocoder = None
try:
    geocoder = Nominatim(user_agent="henu-innopv-ci/1.0", timeout=TIMEOUT)
    print("[talkmap.py] Nominatim geocoder initialized")
except Exception as ex:
    print(f"[talkmap.py][WARN] Could not initialize Nominatim geocoder: {ex}")
    geocoder = None


# ---- Geolocation ------------------------------------------------------------
location_dict = {}
failed_files = []

for file in g:
    print(f"\n--- Processing {file} ---")

    # 1) Parse frontmatter safely
    try:
        data = frontmatter.load(file)
        data = data.to_dict()
    except Exception as ex:
        print(f"  SKIP: failed to parse frontmatter: {ex}")
        failed_files.append((file, "frontmatter", str(ex)))
        continue

    # 2) Skip when no location
    if "location" not in data or not str(data.get("location", "")).strip():
        print("  SKIP: no location field — bypassing")
        continue

    # 3) Safe field access
    title = str(data.get("title", "")).strip() or "(untitled)"
    venue = str(data.get("venue", "")).strip() or "(no venue)"
    location = str(data["location"]).strip()
    description = f"{title}<br />{venue}; {location}"

    # 4) Geocoder missing
    if geocoder is None:
        failed_files.append((file, "no-geocoder", location))
        print("  SKIP: geocoder unavailable")
        continue

    # 5) Geocode
    try:
        result = geocoder.geocode(location, timeout=TIMEOUT)
        if result is None:
            print(f"  WARN: Nominatim returned None for location='{location}'")
            failed_files.append((file, "geocode-None", location))
        else:
            location_dict[description] = result
            print(f"  OK: {location} -> ({result.latitude}, {result.longitude})")
    except (GeocoderTimedOut, GeocoderServiceError,
            GeocoderQuotaExceeded, GeocoderUnavailable) as ex:
        print(f"  WARN: Nominatim service error for '{location}': {type(ex).__name__}: {ex}")
        failed_files.append((file, "geocoder-service", f"{type(ex).__name__}: {ex}"))
    except Exception as ex:
        print(f"  WARN: geocode unexpected error for '{location}': {type(ex).__name__}: {ex}")
        failed_files.append((file, "geocode-other", f"{type(ex).__name__}: {ex}"))

    # Nominatim usage policy: max 1 req/s
    time.sleep(1.1)


# ---- Summary ----------------------------------------------------------------
print("\n========== SUMMARY ==========")
print(f"Successful geolocations: {len(location_dict)}")
print(f"Failed / skipped:         {len(failed_files)}")
for f, reason, msg in failed_files:
    print(f"  - {f} : {reason} : {msg}")


# ---- Write map --------------------------------------------------------------
print(f"\n--- Saving cluster map with {len(location_dict)} locations ---")
try:
    m = getorg.orgmap.create_map_obj()
    getorg.orgmap.output_html_cluster_map(
        location_dict, folder_name="talkmap", hashed_usernames=False
    )
    print("[talkmap.py][OK] output_html_cluster_map completed")
    if os.path.isdir("talkmap"):
        print("talkmap/ contents:", sorted(os.listdir("talkmap")))
    else:
        print("[talkmap.py][WARN] talkmap/ directory not created by getorg")
except Exception as ex:
    print(f"[talkmap.py][FAIL] getorg: {type(ex).__name__}: {ex}")
    traceback.print_exc()
    print("(continuing — no map written)")

# Always exit 0
print("\nDone.")
sys.exit(0)
