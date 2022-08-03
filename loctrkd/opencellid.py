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


def shut() -> None:
    if ldb is not None:
        ldb.close()


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
    # lc.execute("drop table mem.seen")
    lc.execute("""detach database mem""")
    lc.close()
    if not data:
        raise ValueError("No location data found in opencellid")
    sumsig = sum([1 / sig for _, _, sig in data])
    nsigs = [1 / sig / sumsig for _, _, sig in data]
    avlat = sum([lat * nsig for (lat, _, _), nsig in zip(data, nsigs)])
    avlon = sum([lon * nsig for (_, lon, _), nsig in zip(data, nsigs)])
    return avlat, avlon
