""" sqlite event store """

from datetime import datetime
from json import dumps, loads
from sqlite3 import connect, OperationalError, Row
from typing import Any, Dict, List, Optional, Tuple

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
    """create table if not exists pmodmap (
    imei text not null unique,
    pmod text not null,
    tstamp real not null default (strftime('%s'))
)""",
)


def initdb(dbname: str) -> None:
    global DB
    DB = connect(dbname)
    DB.row_factory = Row
    need_populate_pmodmap = False
    try:
        DB.execute("select count(pmod) from pmodmap")
        try:
            DB.execute("select count(tstamp) from pmodmap")
        except OperationalError:
            need_populate_pmodmap = True
            DB.execute("alter table pmodmap rename to old_pmodmap")
    except OperationalError:
        pass  # DB was empty
    for stmt in SCHEMA:
        DB.execute(stmt)
    if need_populate_pmodmap:
        DB.execute(
            """insert into pmodmap(imei, pmod)
               select imei, pmod from old_pmodmap"""
        )
        DB.execute("drop table old_pmodmap")
        DB.commit()


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


def stowpmod(imei: str, pmod: str) -> None:
    assert DB is not None
    DB.execute(
        """insert or replace into pmodmap
                (imei, pmod) values (:imei, :pmod)
        """,
        {"imei": imei, "pmod": pmod},
    )
    DB.commit()


def fetch(imei: str, backlog: int) -> List[Dict[str, Any]]:
    assert DB is not None
    cur = DB.cursor()
    cur.execute(
        """select imei, devtime, accuracy, latitude, longitude, remainder
                    from reports where imei = ?
                    order by devtime desc limit ?""",
        (imei, backlog),
    )
    result = []
    for row in cur:
        dic = dict(row)
        remainder = loads(dic.pop("remainder"))
        dic.update(remainder)
        result.append(dic)
    cur.close()
    return list(reversed(result))


def fetchpmod(imei: str) -> Optional[Any]:
    assert DB is not None
    ret = None
    cur = DB.cursor()
    cur.execute(
        """select pmod from pmodmap where imei = ?
           and tstamp > strftime('%s') - 3600.0""",
        (imei,),
    )
    result = cur.fetchone()
    if result:
        ret = result[0]
    cur.close()
    return ret
