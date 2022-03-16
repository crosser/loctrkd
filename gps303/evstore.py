from logging import getLogger
from sqlite3 import connect

__all__ = ("initdb", "stow")

log = getLogger("gps303")

DB = None

SCHEMA = """create table if not exists events (
    timestamp real not null,
    imei text,
    clntaddr text not null,
    length int,
    proto int not null,
    payload blob
)"""


def initdb(dbname):
    global DB
    log.info('Using Sqlite3 database "%s"', dbname)
    DB = connect(dbname)
    DB.execute(SCHEMA)


def stow(clntaddr, timestamp, imei, length, proto, payload):
    assert DB is not None
    parms = dict(
        zip(
            ("clntaddr", "timestamp", "imei", "length", "proto", "payload"),
            (str(clntaddr), timestamp, imei, length, proto, payload),
        )
    )
    DB.execute(
        """insert or ignore into events
                (timestamp, imei, clntaddr, length, proto, payload)
                values
                (:timestamp, :imei, :clntaddr, :length, :proto, :payload)
        """,
        parms,
    )
    DB.commit()
