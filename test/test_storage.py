""" Send junk to the collector """

from random import Random
from socket import getaddrinfo, socket, AF_INET, SOCK_STREAM
from sqlite3 import connect
from time import sleep
from typing import Any
import unittest
from .common import send_and_drain, TestWithServers
from loctrkd.zx303proto import *
from loctrkd.ocid_dload import SCHEMA


class Storage(TestWithServers):
    def setUp(self, *args: str, **kwargs: Any) -> None:
        super().setUp(
            "collector", "storage", "lookaside", "termconfig", verbose=True
        )
        with connect(self.conf.get("opencellid", "dbfn")) as ldb:
            ldb.execute(SCHEMA)
            ldb.executemany(
                """insert into cells
                    (radio, mcc, net, area, cell, unit, lon, lat, range,
                     samples, changeable, created, updated, averageSignal)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    (
                        "GSM",
                        262,
                        3,
                        24420,
                        16594,
                        -1,
                        12.681939,
                        53.52603,
                        22733,
                        1999,
                        1,
                        1556575612,
                        1653387028,
                        0,
                    ),
                    (
                        "GSM",
                        262,
                        3,
                        24420,
                        36243,
                        -1,
                        12.66442,
                        53.527534,
                        21679,
                        1980,
                        1,
                        1540870608,
                        1653387028,
                        0,
                    ),
                    (
                        "GSM",
                        262,
                        3,
                        24420,
                        17012,
                        -1,
                        12.741093,
                        53.529854,
                        23463,
                        874,
                        1,
                        1563404603,
                        1653268184,
                        0,
                    ),
                    (
                        "GSM",
                        262,
                        3,
                        24420,
                        26741,
                        -1,
                        12.658822,
                        53.530832,
                        18809,
                        1687,
                        1,
                        1539939964,
                        1653265176,
                        0,
                    ),
                    (
                        "GSM",
                        262,
                        2,
                        24420,
                        36243,
                        -1,
                        12.61111,
                        53.536626,
                        1000,
                        4,
                        1,
                        1623218739,
                        1652696033,
                        0,
                    ),
                    (
                        "GSM",
                        262,
                        1,
                        24420,
                        36243,
                        -1,
                        12.611135,
                        53.536636,
                        1000,
                        3,
                        1,
                        1568587946,
                        1628827437,
                        0,
                    ),
                    (
                        "GSM",
                        262,
                        2,
                        24420,
                        17012,
                        -1,
                        12.829655,
                        53.536654,
                        1000,
                        2,
                        1,
                        1609913384,
                        1612934718,
                        0,
                    ),
                    (
                        "GSM",
                        262,
                        3,
                        24000,
                        35471,
                        -1,
                        11.505135,
                        53.554216,
                        11174,
                        829,
                        1,
                        1544494558,
                        1651063300,
                        0,
                    ),
                    (
                        "GSM",
                        262,
                        3,
                        24420,
                        37156,
                        -1,
                        11.918188,
                        53.870522,
                        1000,
                        1,
                        1,
                        1550199983,
                        1550199983,
                        0,
                    ),
                ),
            )
            ldb.commit()
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
        for msg in (
            LOGIN.In(imei="9999123456780000", ver=9),
            WIFI_POSITIONING.In(
                mnc=3,
                mcc=262,
                wifi_aps=[
                    ("02:03:04:05:06:07", -89),
                    ("92:93:94:95:96:97", -70),
                ],
                gsm_cells=[
                    (24420, 27178, -90),
                    (24420, 36243, -78),
                    (24420, 17012, -44),
                ],
            ),
            SETUP.In(),
            STATUS.In(signal=87),
            HIBERNATION.In(),
        ):
            print("Send:", msg)
            send_and_drain(self.sock, b"xx" + msg.packed + b"\r\n")
        sleep(1)
        self.sock.close()
        got = set()
        with connect(self.conf.get("storage", "dbfn")) as db:
            for is_incoming, packet in db.execute(
                "select is_incoming, packet from events"
            ):
                msg = parse_message(packet, is_incoming=is_incoming)
                print("Stored:", msg)
                got.add(type(msg))
        self.assertEqual(
            got,
            {
                LOGIN.Out,
                HIBERNATION.In,
                LOGIN.In,
                SETUP.In,
                SETUP.Out,
                STATUS.Out,
                STATUS.In,
                WIFI_POSITIONING.In,
                WIFI_POSITIONING.Out,
            },
        )


if __name__ == "__main__":
    unittest.main()
