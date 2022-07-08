from configparser import ConfigParser, NoOptionError
import csv
from logging import getLogger
import requests
from sqlite3 import connect
from typing import Any, IO, Optional
from zlib import decompressobj, MAX_WBITS

from . import common

log = getLogger("loctrkd/ocid_dload")

RURL = (
    "https://opencellid.org/ocid/downloads"
    "?token={token}&type={dltype}&file={fname}.csv.gz"
)

SCHEMA = """create table if not exists cells (
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
)"""
DBINDEX = "create index if not exists cell_idx on cells (area, cell)"


class unzipped:
    """
    File-like object that unzips http response body.
    read(size) method returns chunks of binary data as bytes
    When used as iterator, splits data to lines
    and yelds them as strings.
    """

    def __init__(self, zstream: IO[bytes]) -> None:
        self.zstream = zstream
        self.decoder: Optional[Any] = decompressobj(16 + MAX_WBITS)
        self.outdata = b""
        self.line = b""

    def read(self, n: int = 1024) -> bytes:
        if self.decoder is None:
            return b""
        while len(self.outdata) < n:
            raw_data = self.zstream.read(n)
            self.outdata += self.decoder.decompress(raw_data)
            if not raw_data:
                self.decoder = None
                break
        if self.outdata:
            data, self.outdata = self.outdata[:n], self.outdata[n:]
            return data
        return b""

    def __next__(self) -> str:
        while True:
            splittry = self.line.split(b"\n", maxsplit=1)
            if len(splittry) > 1:
                break
            moredata = self.read(256)
            if not moredata:
                raise StopIteration
            self.line += moredata
        line, rest = splittry
        self.line = rest
        return line.decode("utf-8")

    def __iter__(self) -> "unzipped":
        return self


def main(conf: ConfigParser) -> None:
    try:
        url = conf.get("opencellid", "downloadurl")
        mcc = "<unspecified>"
    except NoOptionError:
        try:
            with open(
                conf.get("opencellid", "downloadtoken"), encoding="ascii"
            ) as fl:
                token = fl.read().strip()
        except FileNotFoundError:
            log.warning(
                "Opencellid access token not configured, cannot download"
            )
            return
        mcc = conf.get("opencellid", "downloadmcc")
        if mcc == "full":
            dltype = "full"
            fname = "cell_towers"
        else:
            dltype = "mcc"
            fname = mcc
        url = RURL.format(token=token, dltype="mcc", fname=mcc)
    dbfn = conf.get("opencellid", "dbfn")
    count = 0
    with requests.get(url, stream=True) as resp, connect(dbfn) as db:
        log.debug("Requested %s, result %s", url, resp)
        if resp.status_code != 200:
            log.error("Error getting %s: %s", url, resp)
            return
        db.execute("pragma journal_mode = wal")
        db.execute(SCHEMA)
        db.execute("delete from cells")
        rows = csv.reader(unzipped(resp.raw))
        for row in rows:
            db.execute(
                """insert into cells
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )
            count += 1
        if count < 1:
            db.rollback()
            log.warning("Did not get any data for MCC %s, rollback", mcc)
        else:
            db.execute(DBINDEX)
            db.commit()
            log.info(
                "repopulated %s with %d records for MCC %s", dbfn, count, mcc
            )


if __name__.endswith("__main__"):
    main(common.init(log))
