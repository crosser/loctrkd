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

from sqlite3 import connect


def qry_cell(dbname, mcc, gsm_cells):
    with connect(dbname) as ldb:
        lc = ldb.cursor()
        lc.execute("""attach database ":memory:" as mem""")
        lc.execute("create table mem.seen (locac int, cellid int, signal int)")
        lc.executemany(
            """insert into mem.seen (locac, cellid, signal)
                            values (?, ?, ?)""",
            gsm_cells,
        )
        lc.execute(
            """select c.lat, c.lon, s.signal
                      from main.cells c, mem.seen s
                      where c.mcc = ?
                      and c.area = s.locac
                      and c.cell = s.cellid""",
            (mcc,),
        )
        data = list(lc.fetchall())
        sumsig = sum([sig for _, _, sig in data])
        nsigs = [sig / sumsig for _, _, sig in data]
        avlat = sum([lat * nsig for (lat, _, _), nsig in zip(data, nsigs)])
        avlon = sum([lon * nsig for (_, lon, _), nsig in zip(data, nsigs)])
        # lc.execute("drop table mem.seen")
        lc.close()
        return avlat, avlon


if __name__.endswith("__main__"):
    from datetime import datetime, timezone
    import sys
    from .GT06mod import *

    db = connect(sys.argv[1])
    c = db.cursor()
    c.execute(
        """select timestamp, imei, clntaddr, length, proto, payload from events
            where proto in (?, ?)""",
        (WIFI_POSITIONING.PROTO, WIFI_OFFLINE_POSITIONING.PROTO),
    )
    for timestamp, imei, clntaddr, length, proto, payload in c:
        obj = make_object(length, proto, payload)
        avlat, avlon = qry_cell(sys.argv[2], obj.mcc, obj.gsm_cells)
        print(
            "{} {:+#010.8g},{:+#010.8g}".format(
                datetime.fromtimestamp(timestamp), avlat, avlon
            )
        )
