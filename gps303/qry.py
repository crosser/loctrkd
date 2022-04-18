from datetime import datetime, timezone
from sqlite3 import connect
import sys

from .gps303proto import *

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
    "select timestamp, imei, clntaddr, length, proto, payload from events" +
    selector, {"proto": proto}
)

for timestamp, imei, clntaddr, length, proto, payload in c:
    msg = make_object(length, proto, payload)
    print(
        datetime.fromtimestamp(timestamp)
        .astimezone(tz=timezone.utc)
        .isoformat(),
        msg,
    )
