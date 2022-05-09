""" sqlite event store """

from sqlite3 import connect, OperationalError

__all__ = "fetch", "initdb", "stow"

DB = None

SCHEMA = """create table if not exists events (
    tstamp real not null,
    imei text,
    peeraddr text not null,
    is_incoming int not null default TRUE,
    proto int not null,
    packet blob
)"""


def initdb(dbname):
    global DB
    DB = connect(dbname)
    try:
        DB.execute(
            """alter table events add column
                is_incoming int not null default TRUE"""
        )
    except OperationalError:
        DB.execute(SCHEMA)


def stow(**kwargs):
    assert DB is not None
    parms = {
        k: kwargs[k] if k in kwargs else v
        for k, v in (
            ("is_incoming", True),
            ("peeraddr", None),
            ("when", 0.0),
            ("imei", None),
            ("proto", -1),
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


def fetch(imei, matchlist, backlog):
    # matchlist is a list of tuples (is_incoming, proto)
    # returns a list of tuples (is_incoming, timestamp, packet)
    assert DB is not None
    selector = " or ".join(
        (f"(is_incoming = ? and proto = ?)" for _ in range(len(matchlist)))
    )
    cur = DB.cursor()
    cur.execute(
        f"""select is_incoming, tstamp, packet from events
                    where ({selector}) and imei = ?
                    order by tstamp desc limit ?""",
        tuple(item for sublist in matchlist for item in sublist)
        + (imei, backlog),
    )
    result = list(cur)
    cur.close()
    return list(reversed(result))
