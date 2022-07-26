import googlemaps as gmaps
from typing import Any, Dict, List, Tuple

gclient = None


def init(conf: Dict[str, Any]) -> None:
    global gclient
    with open(conf["googlemaps"]["accesstoken"], encoding="ascii") as fl:
        token = fl.read().rstrip()
    gclient = gmaps.Client(key=token)


def shut() -> None:
    return


def lookup(
    mcc: int,
    mnc: int,
    gsm_cells: List[Tuple[int, int, int]],
    wifi_aps: List[Tuple[str, int]],
) -> Tuple[float, float]:
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
    result = gclient.geolocate(**kwargs)
    if "location" in result:
        return result["location"]["lat"], result["location"]["lng"]
    else:
        raise ValueError("google geolocation: " + str(result))


if __name__.endswith("__main__"):
    from datetime import datetime, timezone
    from sqlite3 import connect
    import sys
    from .zx303proto import *
    from .zx303proto import WIFI_POSITIONING, WIFI_OFFLINE_POSITIONING

    db = connect(sys.argv[1])
    c = db.cursor()
    c.execute(
        """select tstamp, packet from events
            where proto in (?, ?)""",
        (proto_name(WIFI_POSITIONING), proto_name(WIFI_OFFLINE_POSITIONING)),
    )
    init({"googlemaps": {"accesstoken": sys.argv[2]}})
    count = 0
    for timestamp, packet in c:
        obj = parse_message(packet)
        print(obj)
        avlat, avlon = lookup(obj.mcc, obj.mnc, obj.gsm_cells, obj.wifi_aps)
        print(
            "{} {:+#010.8g},{:+#010.8g}".format(
                datetime.fromtimestamp(timestamp), avlat, avlon
            )
        )
        count += 1
        if count > 10:
            break
