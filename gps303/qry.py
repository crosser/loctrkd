from datetime import datetime, timezone
from sqlite3 import connect
import sys

from .gps303proto import parse_message, proto_by_name

db = connect(sys.argv[1])
c = db.cursor()
if len(sys.argv) > 2:
    proto = proto_by_name(sys.argv[2])
    if proto < 0:
        raise ValueError("No protocol with name " + sys.argv[2])
    selector = " where proto = :proto"
else:
    proto = -1
    selector = ""

c.execute(
    "select tstamp, imei, peeraddr, proto, packet from events" +
    selector, {"proto": proto}
)

for tstamp, imei, peeraddr, proto, packet in c:
    if len(packet) >  packet[0] + 1:
        print("proto", packet[1] , "datalen", len(packet),
                "msg.length", packet[0], file=sys.stderr)
    msg = parse_message(packet)
    print(
        datetime.fromtimestamp(tstamp)
        .astimezone(tz=timezone.utc)
        .isoformat(),
        imei,
        peeraddr,
        msg,
    )
