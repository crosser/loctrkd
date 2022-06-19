""" Send junk to the collector """

from random import Random
from socket import getaddrinfo, socket, AF_INET6, SOCK_STREAM
from sqlite3 import connect, Row
from time import sleep
import unittest
from .common import send_and_drain, TestWithServers


class Storage(TestWithServers):
    def setUp(self, *args: str) -> None:
        super().setUp("collector", "storage", "lookaside", "termconfig")
        for fam, typ, pro, cnm, skadr in getaddrinfo(
            "::1",
            self.conf.getint("collector", "port"),
            family=AF_INET6,
            type=SOCK_STREAM,
        ):
            break  # Just take the first element
        self.sock = socket(AF_INET6, SOCK_STREAM)
        self.sock.connect(skadr)

    def tearDown(self) -> None:
        sleep(1)  # give collector some time
        super().tearDown()

    def test_storage(self) -> None:
        buf = b"xx\r\x01\x03Y3\x90w\x19q\x85\x05\r\n"
        send_and_drain(self.sock, buf)
        self.sock.close()
        # TODO: make a proper sequence
        sleep(1)
        print("checking database")
        with connect(self.conf.get("storage", "dbfn")) as db:
            db.row_factory = Row
            for row in db.execute("select * from events"):
                print(dict(row))


if __name__ == "__main__":
    unittest.main()