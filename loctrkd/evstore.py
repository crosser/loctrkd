""" sqlite event store """

from datetime import datetime
from json import dumps
from sqlite3 import connect, OperationalError
from typing import Any, Dict, List, Tuple

__all__ = "fetch", "initdb", "stow", "stowloc"

DB = None

SCHEMA = (
    """create table if not exists events (
    tstamp real not null,
    imei text,
    peeraddr text not null,
    is_incoming int not null default TRUE,
    proto text not null,
    packet blob
)""",
    """create table if not exists reports (
    imei text,
    devtime text not null,
    accuracy real,
    latitude real,
    longitude real,
    remainder text
)""",
)


def initdb(dbname: str) -> None:
    global DB
    DB = connect(dbname)
    try:
        DB.execute(
            """alter table events add column
                is_incoming int not null default TRUE"""
        )
    except OperationalError:
        for stmt in SCHEMA:
            DB.execute(stmt)


def stow(**kwargs: Any) -> None:
    assert DB is not None
    parms = {
        k: kwargs[k] if k in kwargs else v
        for k, v in (
            ("is_incoming", True),
            ("peeraddr", None),
            ("when", 0.0),
            ("imei", None),
            ("proto", "UNKNOWN"),
            ("packet", b""),
        )
    }
    assert len(kwargs) <= len(parms)
    DB.execute(
        """insert or ignore into events
                (tstamp, imei, peeraddr, proto, packet, is_incoming)
                values
                (:when, :imei, :peeraddr, :proto, :packet, :is_incoming)
        """,
        parms,
    )
    DB.commit()


def stowloc(**kwargs: Dict[str, Any]) -> None:
    assert DB is not None
    parms = {
        k: kwargs.pop(k) if k in kwargs else v
        for k, v in (
            ("imei", None),
            ("devtime", str(datetime.now())),
            ("accuracy", None),
            ("latitude", None),
            ("longitude", None),
        )
    }
    parms["remainder"] = dumps(kwargs)
    DB.execute(
        """insert or ignore into reports
                (imei, devtime, accuracy, latitude, longitude, remainder)
                values
                (:imei, :devtime, :accuracy, :latitude, :longitude, :remainder)
        """,
        parms,
    )
    DB.commit()


def fetch(
    imei: str, matchlist: List[Tuple[bool, str]], backlog: int
) -> List[Tuple[bool, float, str, bytes]]:
    # matchlist is a list of tuples (is_incoming, proto)
    # returns a list of tuples (is_incoming, timestamp, packet)
    assert DB is not None
    selector = " or ".join(
        (f"(is_incoming = ? and proto = ?)" for _ in range(len(matchlist)))
    )
    cur = DB.cursor()
    cur.execute(
        f"""select is_incoming, tstamp, proto, packet from events
                    where ({selector}) and imei = ?
                    order by tstamp desc limit ?""",
        tuple(item for sublist in matchlist for item in sublist)
        + (imei, backlog),
    )
    result = list(cur)
    cur.close()
    return list(reversed(result))
