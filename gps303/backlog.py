""" Get backlog from evstore """

from .opencellid import qry_cell
from .evstore import initdb, fetch
from .gps303proto import GPS_POSITIONING, WIFI_POSITIONING, parse_message
from .zmsg import LocEvt

OCDB = None

def blinit(evdb, ocdb):
    global OCDB
    OCDB = ocdb
    initdb(evdb)

def backlog(imei, backlog):
    result = []
    for packet in fetch(imei, (GPS_POSITIONING.PROTO, WIFI_POSITIONING.PROTO), backlog):
        msg = parse_message(packet)
        if isinstance(msg, GPS_POSITIONING):
            result.append(LocEvt(devtime=msg.devtime, lon=msg.longitude,
                lat=msg.latitude, is_gps=True, imei=imei))
        elif isinstance(msg, WIFI_POSITIONING):
            lat, lon = qry_cell(OCDB, msg.mcc, msg.gsm_cells)
            result.append(LocEvt(devtime=msg.devtime, lon=lon,
                lat=lat, is_gps=False, imei=imei))
    return reversed(result)
