"""
Download csv for your carrier and your area from https://opencellid.org/
$ sqlite3 <cell-database-file>
sqlite> create table if not exists cells (
  "radio" text,
  "mcc" int,
  "net" int,
  "area" int,
  "cell" int,
  "unit" int,
  "lon" int,
  "lat" int,
  "range" int,
  "samples" int,
  "changeable" int,
  "created" int,
  "updated" int,
  "averageSignal" int
);
sqlite> .mode csv
sqlite> .import <downloaded-file.csv> cells
sqlite> create index if not exists cell_idx on cells (mcc, area, cell);
"""

from datetime import datetime, timezone
from pprint import pprint
from sqlite3 import connect
import sys

from .GT06mod import *

db = connect(sys.argv[1])
ldb = connect(sys.argv[2])
lc = ldb.cursor()
c = db.cursor()
c.execute(
    """select timestamp, imei, clntaddr, length, proto, payload from events
        where proto in (?, ?)""",
    (WIFI_POSITIONING.PROTO, WIFI_OFFLINE_POSITIONING.PROTO),
)
for timestamp, imei, clntaddr, length, proto, payload in c:
    obj = make_object(length, proto, payload)
    qry = """select lat, lon from cells
             where mcc = {} and (area, cell) in ({})""".format(
        obj.mcc,
        ", ".join(
            [
                "({}, {})".format(locac, cellid)
                for locac, cellid, _ in obj.gsm_cells
            ]
        ),
    )
    print(qry)
    lc.execute(qry)
    for lat, lon in lc:
        print(lat, lon)
