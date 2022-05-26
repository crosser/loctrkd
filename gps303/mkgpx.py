from datetime import datetime, timezone
from sqlite3 import connect
import sys

from .gps303proto import *
from . import opencellid as ocid

ocid.init({"opencellid": {"dbfn": sys.argv[2]}})
db = connect(sys.argv[1])
c = db.cursor()
c.execute(
    "select tstamp, packet from events where proto in ({})".format(
        ", ".join(
            [
                str(n)
                for n in (
                    WIFI_POSITIONING.PROTO,
                    WIFI_OFFLINE_POSITIONING.PROTO,
                    GPS_POSITIONING.PROTO,
                    GPS_OFFLINE_POSITIONING.PROTO,
                )
            ]
        )
    )
)

print(
    """<?xml version="1.0"?>
<gpx version="1.1"
creator="gps303"
xmlns="http://www.topografix.com/GPX/1/1">
  <name>Location Data</name>
  <trk>
    <name>Location Data</name>
    <trkseg>
"""
)

for tstamp, packet in c:
    msg = parse_message(packet)
    if isinstance(msg, (WIFI_POSITIONING, WIFI_OFFLINE_POSITIONING)):
        lat, lon = ocid.lookup(msg.mcc, msg.gsm_cells, msg.wifi_aps)
        if lat is None or lon is None:
            continue
    elif isinstance(msg, (GPS_POSITIONING, GPS_OFFLINE_POSITIONING)):
        lat, lon = msg.latitude, msg.longitude
    else:
        continue
    isotime = (
        datetime.fromtimestamp(tstamp).astimezone(tz=timezone.utc).isoformat()
    )
    isotime = isotime[: isotime.rfind(".")] + "Z"
    trkpt = """      <trkpt lat="{}" lon="{}">
          <time>{}</time>
      </trkpt>""".format(
        lat, lon, isotime
    )
    print(trkpt)
    if False:
        print(
            datetime.fromtimestamp(tstamp)
            .astimezone(tz=timezone.utc)
            .isoformat(),
            msg,
        )
print(
    """    </trkseg>
  </trk>
</gpx>"""
)
