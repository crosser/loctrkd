"""
Lookaside backend to query local opencellid database
"""

from sqlite3 import connect
from typing import Any, Dict, List, Tuple

__all__ = "init", "lookup"

ldb = None


def init(conf: Dict[str, Any]) -> None:
    global ldb
    ldb = connect(conf["opencellid"]["dbfn"])


def lookup(
    mcc: int, mnc: int, gsm_cells: List[Tuple[int, int, int]], __: Any
) -> Tuple[float, float]:
    assert ldb is not None
    lc = ldb.cursor()
    lc.execute("""attach database ":memory:" as mem""")
    lc.execute("create table mem.seen (locac int, cellid int, signal int)")
    lc.executemany(
        """insert into mem.seen (locac, cellid, signal)
                        values (?, ?, ?)""",
        gsm_cells,
    )
    ldb.commit()
    lc.execute(
        """select c.lat, c.lon, s.signal
                  from main.cells c, mem.seen s
                  where c.mcc = ?
                  and c.area = s.locac
                  and c.cell = s.cellid""",
        (mcc,),
    )
    data = list(lc.fetchall())
    if not data:
        return 0.0, 0.0
    sumsig = sum([1 / sig for _, _, sig in data])
    nsigs = [1 / sig / sumsig for _, _, sig in data]
    avlat = sum([lat * nsig for (lat, _, _), nsig in zip(data, nsigs)])
    avlon = sum([lon * nsig for (_, lon, _), nsig in zip(data, nsigs)])
    # lc.execute("drop table mem.seen")
    lc.execute("""detach database mem""")
    lc.close()
    return avlat, avlon


if __name__.endswith("__main__"):
    from datetime import datetime, timezone
    import sys
    from .gps303proto import *

    db = connect(sys.argv[1])
    c = db.cursor()
    c.execute(
        """select tstamp, packet from events
            where proto in (?, ?)""",
        (WIFI_POSITIONING.PROTO, WIFI_OFFLINE_POSITIONING.PROTO),
    )
    init({"opencellid": {"dbfn": sys.argv[2]}})
    for timestamp, packet in c:
        obj = parse_message(packet)
        avlat, avlon = lookup(obj.mcc, obj.mnc, obj.gsm_cells, obj.wifi_aps)
        print(
            "{} {:+#010.8g},{:+#010.8g}".format(
                datetime.fromtimestamp(timestamp), avlat, avlon
            )
        )
