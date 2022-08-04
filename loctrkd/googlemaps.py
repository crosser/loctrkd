"""
Google Maps location service lookaside backend
"""

from configparser import ConfigParser
import googlemaps as gmaps
from typing import Any, Callable, Dict, List, Tuple

gclient = None


def init(conf: ConfigParser) -> None:
    global gclient
    with open(conf["googlemaps"]["accesstoken"], encoding="ascii") as fl:
        token = fl.read().rstrip()
    gclient = gmaps.Client(key=token)


def shut() -> None:
    return


def _lookup(
    mcc: int,
    mnc: int,
    gsm_cells: List[Tuple[int, int, int]],
    wifi_aps: List[Tuple[str, int]],
) -> Any:
    assert gclient is not None
    kwargs = {
        "home_mobile_country_code": mcc,
        "home_mobile_network_code": mnc,
        "radio_type": "gsm",
        "carrier": "O2",
        "consider_ip": False,
        "cell_towers": [
            {
                "locationAreaCode": loc,
                "cellId": cellid,
                "signalStrength": sig,
            }
            for loc, cellid, sig in gsm_cells
        ],
        "wifi_access_points": [
            {"macAddress": mac, "signalStrength": sig} for mac, sig in wifi_aps
        ],
    }
    return gclient.geolocate(**kwargs)


def lookup(
    mcc: int,
    mnc: int,
    gsm_cells: List[Tuple[int, int, int]],
    wifi_aps: List[Tuple[str, int]],
) -> Tuple[float, float]:
    result = _lookup(mcc, mnc, gsm_cells, wifi_aps)
    if "location" in result:
        return result["location"]["lat"], result["location"]["lng"]
    else:
        raise ValueError("google geolocation: " + str(result))


if __name__.endswith("__main__"):
    from getopt import getopt
    from json import loads
    from logging import getLogger
    from sys import argv
    from . import common

    def cell_list(s: str) -> List[Tuple[int, int, int]]:
        return [(int(ac), int(ci), int(sg)) for [ac, ci, sg] in loads(s)]

    def ap_list(s: str) -> List[Tuple[str, int]]:
        return [(mac, int(sg)) for [mac, sg] in loads(s)]

    log = getLogger("loctrkd/googlemaps")
    opts, args = getopt(argv[1:], "c:d")
    conf = common.init(log, opts=opts)
    init(conf)
    parms = {}
    needed: Dict[str, Callable[[Any], Any]] = {
        "mcc": int,
        "mnc": int,
        "gsm_cells": cell_list,
        "wifi_aps": ap_list,
    }
    parms = {k: needed.pop(k)(v) for k, v in [arg.split("=") for arg in args]}
    if needed:
        raise ValueError(f"still needed: {needed}")
    print(_lookup(**parms))
