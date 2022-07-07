""" Example that produces gpx from events in evstore """

# run as:
# python -m gps303.mkgpx <sqlite-file> <IMEI>
# Generated gpx is emitted to stdout

from datetime import datetime, timezone
from sqlite3 import connect
import sys

from .gps303proto import *

db = connect(sys.argv[1])
c = db.cursor()
c.execute(
    """select tstamp, is_incoming, packet from events
       where imei = ?
       and ((is_incoming = false and proto = ?) 
         or (is_incoming = true and proto = ?))
       order by tstamp""",
    (sys.argv[2], proto_name(WIFI_POSITIONING), proto_name(GPS_POSITIONING)),
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

for tstamp, is_incoming, packet in c:
    msg = parse_message(packet, is_incoming=is_incoming)
    lat, lon = msg.latitude, msg.longitude
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
