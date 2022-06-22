""" Send junk to the collector """

from random import Random
from socket import getaddrinfo, socket, AF_INET, SOCK_STREAM
from sqlite3 import connect, Row
from time import sleep
import unittest
from .common import send_and_drain, TestWithServers
from gps303.gps303proto import *


class Storage(TestWithServers):
    def setUp(self, *args: str) -> None:
        super().setUp("collector", "storage", "lookaside", "termconfig")
        for fam, typ, pro, cnm, skadr in getaddrinfo(
            "127.0.0.1",
            self.conf.getint("collector", "port"),
            family=AF_INET,
            type=SOCK_STREAM,
        ):
            break  # Just take the first element
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.connect(skadr)

    def tearDown(self) -> None:
        sleep(1)  # give collector some time
        super().tearDown()

    def test_storage(self) -> None:
        for buf in (
            LOGIN.In(imei="9999123456780000", ver=9).packed,
            STATUS.In().packed,
            HIBERNATION.In().packed,
        ):
            send_and_drain(self.sock, b"xx" + buf + b"\r\n")
        self.sock.close()
        sleep(1)
        got = set()
        with connect(self.conf.get("storage", "dbfn")) as db:
            db.row_factory = Row
            for is_incoming, packet in db.execute(
                "select is_incoming, packet from events"
            ):
                msg = parse_message(packet, is_incoming=is_incoming)
                # print(msg)
                got.add(type(msg))
        self.assertEqual(
            got, {LOGIN.Out, HIBERNATION.In, LOGIN.In, STATUS.Out, STATUS.In}
        )


if __name__ == "__main__":
    unittest.main()
