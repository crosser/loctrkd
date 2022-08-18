"""
Lookaside backend to query local opencellid database
"""

from configparser import ConfigParser
from sqlite3 import connect
from typing import Any, Dict, List, Tuple

__all__ = "init", "lookup"

ldb = None


def init(conf: ConfigParser) -> None:
    global ldb
    ldb = connect(conf["opencellid"]["dbfn"])
    ldb.execute("create temp table seen (locac int, cellid int, signal int)")


def shut() -> None:
    if ldb is not None:
        ldb.close()


def lookup(
    mcc: int, mnc: int, gsm_cells: List[Tuple[int, int, int]], __: Any
) -> Tuple[float, float, float]:
    assert ldb is not None
    lc = ldb.cursor()
    lc.executemany(
        "insert into seen (locac, cellid, signal) values (?, ?, ?)",
        gsm_cells,
    )
    ldb.commit()
    lc.execute(
        """select c.lat, c.lon, s.signal
                  from cells c, seen s
                  where c.mcc = ?
                  and c.net = ?
                  and c.area = s.locac
                  and c.cell = s.cellid""",
        (mcc, mnc),
    )
    data = list(lc.fetchall())
    # This should be faster than dropping and recreating the temp table
    # https://www.sqlite.org/lang_delete.html#the_truncate_optimization
    lc.execute("delete from seen")
    lc.close()
    if not data:
        raise ValueError("No location data found in opencellid")
    sumsig = sum([1 / sig for _, _, sig in data])
    nsigs = [1 / sig / sumsig for _, _, sig in data]
    avlat = sum([lat * nsig for (lat, _, _), nsig in zip(data, nsigs)])
    avlon = sum([lon * nsig for (_, lon, _), nsig in zip(data, nsigs)])
    return avlat, avlon, 99.9  # TODO estimate accuracy for real
