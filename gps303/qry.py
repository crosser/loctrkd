from datetime import datetime, timezone
from sqlite3 import connect
import sys

from .GT06mod import *

db = connect(sys.argv[1])
c = db.cursor()
c.execute(
    "select timestamp, imei, clntaddr, length, proto, payload from events"
)
for timestamp, imei, clntaddr, length, proto, payload in c:
    print(
        datetime.fromtimestamp(timestamp)
        .astimezone(tz=timezone.utc)
        .isoformat(),
        make_object(length, proto, payload),
    )
