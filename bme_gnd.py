import sys
import json
import re

import asyncio
import websockets

BME_GND_FMT = r'(?P<data>[0-9A-E]+) RSSI (?P<rssi>[+-][0-9]+) dBm (?P<tstamp>.+)'

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

async def parse_message(message, websocket):
    data_match = re.match(BME_GND_FMT, message)
    if data_match:
        packet = bytes.fromhex(data_match.group('data'))[4:].decode()+','

        await websocket.send(json.dumps({
            'type': 'rawpacket',
            'packet': 'Decoded as: '+packet
        }))
        await websocket.send(json.dumps({
            'type': 'radio.rssi',
            'rssi': int(data_match.group('rssi'))
        }))

        if re.match(UPRA_TLMPACKET_FMT, packet):
            await websocket.send(json.dumps({
                'type': 'rawpacket.upra.telemetry',
                'packet': msg
            }))


async def recv_from_gnd(websocket, reader):
    while True:
        msgbin = await reader.readuntil(b'\n')
        msg = msgbin.rstrip().decode()

        print(f'Received from GND: {msg}')
        await websocket.send(json.dumps({
            'type': 'rawpacket',
            'packet': msg
        }))
        await parse_message(msg, websocket)

async def recv_from_mcs(websocket):
    async for msg in websocket:
        print(f'Received from websocket: {msg}')
        packet = json.loads(msg)

async def keep_alive(websocket):
    while True:
        websocket.ping()
        await asyncio.sleep(5)


async def main():
    async with websockets.connect('ws://'+sys.argv[1]) as ws:
        print('Connected to ws://'+sys.argv[1])

        await pick_mission(ws)

        sock_addr = sys.argv[2].split(':')
        socket_reader, _ = await asyncio.open_connection(sock_addr[0], int(sock_addr[1]))

        print('Connected to '+sys.argv[2])

        await asyncio.gather(
            recv_from_gnd(ws, socket_reader),
            recv_from_mcs(ws),
            keep_alive(ws)
        )

asyncio.run(main())
