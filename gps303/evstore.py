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
        DB.execute("""alter table events add column
                is_incoming int not null default TRUE""")
    except OperationalError:
        DB.execute(SCHEMA)


def stow(**kwargs):
    assert DB is not None
    parms = {
        k: kwargs[k] if k in kwargs else v
        for k, v in (
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
                (tstamp, imei, peeraddr, proto, packet)
                values
                (:when, :imei, :peeraddr, :proto, :packet)
        """,
        parms,
    )
    DB.commit()

def fetch(imei, protos, backlog):
    assert DB is not None
    protosel = ", ".join(["?" for _ in range(len(protos))])
    cur = DB.cursor()
    cur.execute(f"""select packet from events
                    where proto in ({protosel}) and imei = ?
                    order by tstamp desc limit ?""",
                protos + (imei, backlog))
    result = [row[0] for row in cur]
    cur.close()
    return result
