""" Send junk to the collector """

from sqlite3 import connect
from time import sleep
from typing import Any
import unittest
from .common import send_and_drain, TestWithServers
from gps303 import ocid_dload


class Ocid_Dload(TestWithServers):
    def setUp(self, *args: str, **kwargs: Any) -> None:
        super().setUp(httpd=True)

    def tearDown(self) -> None:
        sleep(1)  # give collector some time
        super().tearDown()

    def test_ocid_dload(self) -> None:
        ocid_dload.main(self.conf)
        with connect(self.conf.get("opencellid", "dbfn")) as db:
            (count,) = db.execute("select count(*) from cells").fetchone()
        self.assertEqual(count, 163)


if __name__ == "__main__":
    unittest.main()
