import sys
import json
import re
import math

import asyncio
import serial_asyncio
import websockets

E_RADIUS = 6371000

UPRA_TLMPACKET_FMT = (
    r'\$\$(?P<csgn>.{7}),'
    r'(?P<msgid>.{3}),'
    r'(?P<hours>.{2})'
    r'(?P<mins>.{2})'
    r'(?P<secs>.{2}),'
    r'(?P<lat>[+-]?.{2})'
    r'(?P<latmins>.{2}\..{3}),'
    r'(?P<lng>[+-]?.{3})'
    r'(?P<lngmins>.{2}\..{3}),'
    r'(?P<alt>.{5}),'
    r'(?P<exttemp>.{4}),'
    r'(?P<obctemp>.{3}),'
    r'(?P<comtemp>.{3}),'
)

station_lat = None # Station latitude, decimal degrees
station_lng = None # Station longitude, decimal degrees
station_alt = None # Station altitude, metres

antenna_azimuth = None # Antenna azimuth, decimal degrees
antenna_elevation = None # Antenna elevation, decimal degrees
target_distance = None # Distance of tracked target from ARS, metres

def input_type(msg, type_converter):
    while True:
        s = raw_input(msg)
        try :
            return type_converter(s)
        except ValueError as e:
            print(e)

async def setup_location(websocket):
    print('Station location setup')
    station_lat = input_type('Station latitude: ', float)
    station_lng = input_type('Station longitude: ', float)
    station_alt = input_type('Station altitude: ', int)
    await websocket.send(json.dumps({
        'type': 'location.ars',
        'lat': station_lat
        'lng': station_lng
        'alt': station_alt
    }))

async def calc_rotation_for_hab(hab_lat, hab_lng, hab_alt):
    """
    Compute antenna rotation using received location of a tracked high altitude balloon
    """
    hab_lat_rad = math.radians(hab_lat)
    hab_lng_rad = math.radians(hab_lng)
    ars_lat_rad = math.radians(station_lat)
    ars_lng_rad = math.radians(station_lng)

    d_lng = hab_lng_rad - ars_lng_rad

    sa = (math.cos(hab_lat_rad) * math.sin(d_lng))
    sb = ((math.cos(ars_lat_rad) * math.sin(hab_lat_rad)) - (math.sin(ars_lat_rad) * math.cos(hab_lat_rad) * math.cos(d_lng)))

    antenna_azimuth = math.degrees(math.atan2(sa, sb))

    aa = math.hypot(sa, sb)
    ab = (math.sin(ars_lat_rad) * math.sin(hab_lat_rad)) + (math.cos(ars_lat_rad) * math.cos(hab_lat_rad) * math.cos(d_lng))
    angle_at_centre = math.atan2(aa, ab)
    great_circle_distance = angle_at_centre * E_RADIUS

    ta = E_RADIUS + station_alt
    tb = E_RADIUS + hab_alt
    ea = (math.cos(angle_at_centre) * tb) - ta
    eb = math.sin(angle_at_centre) * tb
    antenna_elevation_rad = math.atan2(ea, eb)
    antenna_elevation = (antenna_elevation_rad < 0) ? 0 : math.degrees(antenna_elevation_rad)

    target_distance = math.sqrt((ta * ta) + (tb * tb) - 2 * tb * ta * math.cos(angle_at_centre))


async def pick_mission(websocket):
    await websocket.send(json.dumps({
        'type': 'mission.list.get'
    }))
    missionlist_txt = await websocket.recv()
    missionlist = json.loads(missionlist_txt)
    print('Available missions:')
    for mission in missionlist['missions']:
        print(f'{mission["id"]}) {mission["name"]}')
    picked = input('Pick mission num: ')
    await websocket.send(json.dumps({
        'type': 'mission.select',
        'id': picked
    }))


async def recv_from_serial(websocket, serial_reader):
    while True:
        msgbin = await serial_reader.readuntil(b'\n')
        msg = msgbin.rstrip().decode()
        print(f'Received from serial: {msg}')
        await websocket.send(json.dumps({
            'type': 'rawpacket',
            'packet': msg
        }))

async def recv_from_websocket(websocket, serial_writer):
    async for msg in websocket:
        print(f'Received from websocket: {msg}')

async def keep_alive(websocket):
    while True:
        websocket.ping()
        await asyncio.sleep(5)


async def main():
    async with websockets.connect('ws://'+sys.argv[1]) as ws:
        print('Connected to ws://'+sys.argv[1])

        await setup_location(ws)
        await pick_mission(ws)

        serial_reader, serial_writer = await serial_asyncio.open_serial_connection(url=sys.argv[2], baudrate=int(sys.argv[3]))

        print('Connected to '+sys.argv[2])

        await asyncio.gather(
            recv_from_serial(ws, serial_reader),
            recv_from_websocket(ws, serial_writer),
            keep_alive(ws)
        )

asyncio.run(main())
