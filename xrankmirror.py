import argparse
import time
import http.client
import sys
import json
from pathlib import Path
from operator import itemgetter
from operator import methodcaller
import importlib.metadata
from typing import Any


PKG = "runit-2.2.0_2.x86_64.xbps"
HTTP_TIMEOUT = 5
MAX_REDIRECTS = 3


def get_xrankmirror_version():
    """Get the rankmirror program version from pyproject.toml"""
    try:
        return importlib.metadata.version("xrankmirror")
    except Exception as _:
        return "unknown"


def format_speed(speed: float, suffix="B/s"):
    for unit in ("", "K", "M", "G"):
        if abs(speed) < 1000.0:
            return f"{speed:3.1f}{unit}{suffix}"
        speed /= 1000.0
    return f"{speed:.1f}T{suffix}"


def create_connection(url: str):
    if url.startswith("https://"):
        host, path = url[8:].split("/", maxsplit=1)
        conn = http.client.HTTPSConnection(host, timeout=HTTP_TIMEOUT)
    elif url.startswith("http://"):
        host, path = url[7:].split("/", maxsplit=1)
        conn = http.client.HTTPConnection(host, timeout=HTTP_TIMEOUT)
    else:
        sys.exit("Error: Invalid url %s" % url)
    return conn, path


def fetch_mirrorlist(url: str):
    conn, path = create_connection(url)
    conn.request("GET", f"/{path}")
    response = conn.getresponse()
    if response.status != 200:
        sys.exit("Error: Unable to fetch mirror list. failed with status code %d" % response.status)
    raw_content = response.read().decode()
    records = json.loads(raw_content)
    response.close()
    return records


def list_regions(mirrors: dict[str, Any], *, display=True) -> list[str]|None:
    """
    List the unique regions found in the mirrors list.
    if display is True print
    else return the set of regions.
    """
    regions = list(set([mirror["region"] for mirror in mirrors]))
    regions.sort()
    if not display:
        return regions

    if regions:
        print("Available Regions:")
        for region in regions:
            print(f" - {region}")
    else:
        print("No regions available.")


def list_mirrors(mirrors: dict[str, Any]):
    if not mirrors:
        return
    print(f"{'repo':^50}    {'tier':<4}    {'region':<6}    {'location':<8}")
    for mirror in mirrors:
        print(f"{mirror['base_url'][:50]:>50}    {mirror['tier']:<4}    {mirror['region']:<6}    {mirror['location']:<}")


def rank_mirror(mirror: dict, pkg_path: str) -> float|None:
    # {'base_url': 'https://repo-de.voidlinux.org/', 'region': 'EU', 'location': 'Frankfurt, Germany', 'tier': 1, 'enabled': True}
    try:
        base_url = mirror["base_url"]
        base_url = base_url.rstrip("/") + pkg_path
        stime = time.perf_counter()
        for _ in range(MAX_REDIRECTS):
            conn, path = create_connection(base_url)
            conn.request("GET", f"/{path}")
            response = conn.getresponse()
            if response.status not in (301, 302, 303, 307, 308):
                break
            base_url = response.getheader('Location')
            response.close()
        etime = time.perf_counter()
        ttime = etime-stime
        data_len = len(response.read())
        if response.status != 200:
            sys.stderr.writelinse(f"ERROR: {conn.host}: failed with status code {response.status}")
            return None
        speed = (data_len/ttime)
        return speed
    except Exception as _:
        print(f"ERROR: {conn.host}: failed utterly")
        return None


def benchmark_mirrors(mirrors: dict):
    total_mirrors = len(mirrors)
    print(f"Found {total_mirrors} mirrors")
    pkg_path = "/current/" + PKG

    results = []
    for index, mirror in enumerate(mirrors):
        mirror["speed"] = rank_mirror(mirror, pkg_path)
        if mirror.get("speed") is not None:
            results.append(mirror)
        print(f"Progress: {index+1:>3}/{total_mirrors:<3}", end="\r")
    print()

    # sort results
    results.sort(key=itemgetter("speed"), reverse=True)

    if not results:
        print("No working mirrors available")
        return
    print(f"{'repo':^50}    {'tier':<4}    {'region':<6}    {'location':<28}    {'speed':<}")
    for mirror in results:
        print(f"{mirror['base_url'][:50]:>50}    {mirror['tier']:<4}    {mirror['region']:<6}    {mirror['location']:<28}    {format_speed(mirror['speed'])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--version", help="print xrankmirror version", action="store_true")
    parser.add_argument("--list-regions",  help="List the available regions", action="store_true")
    parser.add_argument("-r", "--regions",  help="filter mirror by regions eg: -r AS or -r AS,EU ", default="")
    parser.add_argument( "--tier",  help="List the available mirrors", type=int, choices=[1, 2])
    parser.add_argument("-l", "--list-mirrors",  help="List the available mirrors", action="store_true")
    args = parser.parse_args()

    mirrorlist_url = "https://xmirror.voidlinux.org/v0/mirrors.json"
    mirrors = fetch_mirrorlist(mirrorlist_url)

    mirrors = [mirror for mirror in mirrors if mirror["enabled"]] # get only enabled mirrors

    # List regions 
    if args.list_regions:
        list_regions(mirrors)
        return

    # Filter by region
    regions = args.regions.strip(" ,")
    if regions:
        regions = regions.split(",")
        available_regions = list_regions(mirrors, display=False)
        for region in regions:
            if region not in available_regions: # check for invalid regions
                sys.exit("Error: Region '%s' not supported" % region)

        mirrors = [mirror for mirror in mirrors if mirror["region"] in regions]

    # Filter by tier
    if args.tier:
        mirrors = [mirror for mirror in mirrors if mirror['tier'] == args.tier]

    # List mirrors
    if args.list_mirrors:
        list_mirrors(mirrors)
        return
    
    benchmark_mirrors(mirrors)
    print()


if __name__ == "__main__":
    main()
    # result_path = Path("~/.cache/xrankmirrors-results").expanduser().resolve()
    # mirrorlist_url = "https://xmirror.voidlinux.org/v0/mirrors.json"
    # mirrorlist = fetch_mirrorlist(mirrorlist_url)
    # total_mirrors = len(mirrorlist)
    # print(f"Found {total_mirrors} mirrors")
    # pkg_path = "/current/" + PKG
    # # rank_mirror({'base_url': 'https://mirrors.servercentral.com/voidlinux/', 'region': 'EU', 'location': 'Frankfurt, Germany', 'tier': 1, 'enabled': True}, pkg_path)
    #
    # results = []
    # for index, mirror in enumerate(mirrorlist):
    #     results.append(rank_mirror(mirror, pkg_path))
    #     print(f"Progress: {index+1:>3}/{total_mirrors:<3}", end="\r")
    # print()
    #
    # with open(result_path, "w", encoding="utf-8") as f:
    #     for result in results:
    #         if all(result):
    #             f.write("|".join(map(str, result))+"\n")

    # print("\nStats:")
    # with open(result_path, "r", encoding="utf-8") as f:
    #     results = f.readlines()
    # results = map(lambda x: x.split("|"), results)
    # results = [(host, float(ttime), float(speed)) for host, ttime, speed in results]
    # results.sort(key=itemgetter(2), reverse=True)    
    # for row in results:
    #     if all(row):
    #         print(f"{row[0]:<30}     {float(row[1]):3.2f}   {format_speed(float(row[2]))}")
