from datetime import datetime, timezone
from sqlite3 import connect
import sys

from .gps303proto import *
from .opencellid import qry_cell

db = connect(sys.argv[1])
c = db.cursor()
c.execute(
    "select timestamp, imei, clntaddr, length, proto, payload from events"
)

print("""<?xml version="1.0"?>
<gpx version="1.1"
creator="gps303"
xmlns="http://www.topografix.com/GPX/1/1">
  <name>Location Data</name>
  <trk>
    <name>Location Data</name>
    <trkseg>
""")

for timestamp, imei, clntaddr, length, proto, payload in c:
    msg = make_object(length, proto, payload)
    if isinstance(msg, (WIFI_POSITIONING, WIFI_OFFLINE_POSITIONING)):
        lat, lon = qry_cell(sys.argv[2], msg.mcc, msg.gsm_cells)
        if lat is None or lon is None:
            continue
    elif isinstance(msg, (GPS_POSITIONING, GPS_OFFLINE_POSITIONING)):
        lat, lon = msg.latitude, msg.longitude
    else:
        continue
    isotime = datetime.fromtimestamp(timestamp).astimezone(tz=timezone.utc).isoformat()
    isotime = isotime[:isotime.rfind(".")] + "Z"
    trkpt = """      <trkpt lat="{}" lon="{}">
          <time>{}</time>
      </trkpt>""".format(lat, lon, isotime)
    print(trkpt)
    if False:
        print(
            datetime.fromtimestamp(timestamp)
            .astimezone(tz=timezone.utc)
            .isoformat(),
            msg,
        )
print("""    </trkseg>
  </trk>
</gpx>""")
