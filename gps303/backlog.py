""" Get backlog from evstore """

from .opencellid import qry_cell
from .evstore import initdb, fetch
from .gps303proto import GPS_POSITIONING, WIFI_POSITIONING, parse_message


def blinit(evdb):
    initdb(evdb)


def backlog(imei, backlog):
    result = []
    for packet in fetch(
        imei, (GPS_POSITIONING.PROTO, WIFI_POSITIONING.PROTO), backlog
    ):
        msg = parse_message(packet)
    return reversed(result)
