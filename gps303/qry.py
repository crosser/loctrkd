from datetime import datetime
from sqlite3 import connect
import sys

from .GT06mod import *

db = connect(sys.argv[1])
c = db.cursor()
c.execute("select timestamp, imei, clntaddr, proto, payload from events")
for timestamp, imei, clntaddr, proto, payload in c:
    print(datetime.fromtimestamp(timestamp).isoformat(),
            make_object(proto, payload))
