"""
For when responding to the terminal is not trivial
"""

from .gps303proto import *
from .opencellid import qry_cell

def prepare_response(conf, msg):
    if isinstance(msg, WIFI_POSITIONING):
        lat, lon = qry_cell(conf["opencellid"]["dbfn"],
                msg.mcc, msg.gsm_cells)
        return {"lat": lat, "lon": lon}
    return {}
