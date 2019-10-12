import sys
import json
import re
import math
import logging
import logging.config

import asyncio
import serial_asyncio
import websockets
import websockets.exceptions

E_RADIUS = 6371000

DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s [%(levelname)s] - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'formatter': 'default',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        },
        'logfile': {
            'level': 'INFO',
            'formatter': 'default',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': 'ars.log',
            'when': 'midnight',
            'utc': True
        }
    },
    'loggers': {
        '': { # Root logger
            'level': 'INFO',
            'handlers': ['console', 'logfile'],
            'propagate': True
        },
        'ugnd-ars': {
            'level': 'INFO',
            'handlers': ['console', 'logfile'],
            'propagate': False
        }
    }
}

MCS_RECONNECT_SECS = 15 # Time between reconnect attemps to MCS

def input_type(msg, type_converter):
    while True:
        s = input(msg)
        try :
            return type_converter(s)
        except ValueError as e:
            print(e)

def manual_antenna_rotation_notice(azimuth, elevation):
    print(f"Rotate antenna to azimuth: {azimuth}, elevation: {elevation}")

class BaseRadioStation():
    """
    Base class implementing common radio station functionality.
    Handles most of the communication with the UGND mission control server
    You should not derive classes from this directly unless you're implementing
    a new connection type different from serial, etc.
    """

    def __init__(self, mcs_addr):
        self.mcs_address = mcs_addr # Address of the UGND mission control server WS endpoint

        self.station_name = None # Station name
        self.station_lat = None # Station latitude, decimal degrees
        self.station_lng = None # Station longitude, decimal degrees
        self.station_alt = None # Station altitude, metres

        self.antenna_azimuth = None # Antenna azimuth, decimal degrees
        self.antenna_elevation = None # Antenna elevation, decimal degrees
        self.target_distance = None # Distance of tracked target from ARS, metres

        self.websocket = None

        logging.config.dictConfig(DEFAULT_LOGGING)
        self.logger = logging.getLogger('ugnd-ars')

    async def send_to_mcs(self, data):
        """
        Send data to the UGND mission control server.
        data should be a dict that has a 'type' key of a valid UGND message type
        and all fields specified by the given message type
        """
        try:
            data_txt = json.dumps(data)
            await self.websocket.send(data_txt)
            self.logger.debug("Sent to MCS: %s", data_txt)
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("Could not send data to MCS, connection is closed.")
            pass

    async def recv_from_mcs(self):
        """
        Receive the next message from the UGND mission control server
        """
        data_txt = await self.websocket.recv()
        self.logger.debug("Received from MCS: %s", data_txt)
        return json.loads(data_txt)

    async def listen_from_mcs(self):
        """
        Listen for messages from the UGND mission control server
        """
        await self.mcs_hello()
        async for msg_txt in self.websocket:
            self.logger.debug("Received from MCS: %s", msg_txt)
            msg = json.loads(msg_txt)
            # TODO: Figure out MCS message handling
            if msg['type'] == 'mission.list':
                await self.pick_mission(msg['missions'])

    async def recv_from_gnd(self):
        """
        Receive a packet from lower level GND equipment (eg. modem).
        Should be overrided by derived classes.
        The implementaton of this method should return the packet in string form
        """
        raise NotImplementedError()

    async def mcs_reconnect_attempt(self, reconnect_secs):
        self.logger.info("Trying to reconnect in %d seconds...", reconnect_secs)
        await asyncio.sleep(reconnect_secs)

    def setup_mcs_address(self):
        self.mcs_address = input('Enter address of MCS websocket endpoint: ')

    def setup_name(self):
        self.station_name = input('Station name: ')

    def setup_location(self):
        print('Station location setup')
        self.station_lat = input_type('Station latitude: ', float)
        self.station_lng = input_type('Station longitude: ', float)
        self.station_alt = input_type('Station altitude: ', int)

    async def pick_mission(self, missionlist):
        print('Available missions:')
        for mission in missionlist:
            print(f'{mission["id"]}) {mission["name"]}')
        picked = input_type('Pick mission num: ', int)
        await self.send_to_mcs({
            'type': 'mission.select',
            'id': picked
        })

    async def mcs_hello(self):
        """
        Sends info about the radio station to the MCS after connecting
        and asks for the list of available missions
        """
        await self.send_to_mcs({
            'type': 'name.ars',
            'name': self.station_name
        })
        await self.send_to_mcs({
            'type': 'location.ars',
            'lat': self.station_lat,
            'lng': self.station_lng,
            'alt': self.station_alt
        })
        await self.send_to_mcs({
            'type': 'mission.list.get'
        })

    async def parse_gnd_packet(self, packet):
        """
        Parse a raw packet string received from lower level GND equipment.
        Should be overrided by derived classes implementing actual radio stations,
        which have knowledge about the packet formats they will receive.
        Parsed data can be sent as typed valid UGND messages using send_to_mcs()
        """
        raise NotImplementedError

    async def calc_rotation_for_hab(self, hab_lat, hab_lng, hab_alt):
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

        self.antenna_azimuth = math.degrees(math.atan2(sa, sb))

        aa = math.hypot(sa, sb)
        ab = (math.sin(ars_lat_rad) * math.sin(hab_lat_rad)) + (math.cos(ars_lat_rad) * math.cos(hab_lat_rad) * math.cos(d_lng))
        angle_at_centre = math.atan2(aa, ab)
        great_circle_distance = angle_at_centre * E_RADIUS

        ta = E_RADIUS + station_alt
        tb = E_RADIUS + hab_alt
        ea = (math.cos(angle_at_centre) * tb) - ta
        eb = math.sin(angle_at_centre) * tb
        antenna_elevation_rad = math.atan2(ea, eb)
        self.antenna_elevation = 0 if antenna_elevation_rad < 0 else math.degrees(antenna_elevation_rad)

        self.target_distance = math.sqrt((ta * ta) + (tb * tb) - 2 * tb * ta * math.cos(angle_at_centre))

        # TODO: Implement a strategy pattern that can also allow auto rotation besides this
        manual_antenna_rotation_notice(self.antenna_azimuth, self.antenna_elevation)


    async def keep_listening_from_mcs(self):
        mcs_online = False

        while True:
            if not re.match('^wss?://', self.mcs_address):
                self.mcs_address = 'ws://'+self.mcs_address
            try:
                async with websockets.connect(self.mcs_address) as ws:
                    mcs_online = True
                    self.websocket = ws
                    self.logger.info("Connected to Misson Control Server at %s", self.mcs_address)
                    await self.listen_from_mcs()
            except websockets.exceptions.InvalidURI:
                self.logger.error("Cannot connect to invalid MCS address %s", self.mcs_address)
                self.setup_mcs_address()
                pass
            except websockets.exceptions.WebSocketException:
                if mcs_online:
                    mcs_online = False
                    self.logger.exception("Connection lost to MCS!")
                else:
                    self.logger.error("Could not reconnect to MCS.")
                await self.mcs_reconnect_attempt(MCS_RECONNECT_SECS)
                pass
            except Exception:
                self.logger.critical("An unexpected error occured", exc_info=True)
                await self.mcs_reconnect_attempt(MCS_RECONNECT_SECS)
                pass

    async def connect_to_gnd(self):
        """
        Called to establish connection to the lower level GND equipment of the station.
        Should be overrided by derived classes.
        """
        raise NotImplementedError

    async def listen_from_gnd(self):
        while True:
            packet = await self.recv_from_gnd()
            self.logger.debug("Received from GND: %s", packet)
            await self.send_to_mcs({
                'type': 'rawpacket',
                'packet': packet
            })
            await self.parse_gnd_packet(packet)

    async def keep_listening_from_gnd(self):
        await self.connect_to_gnd()
        await self.listen_from_gnd()
        #TODO: Catch Exceptions here somehow

    async def run_station_async(self):
        self.setup_name()
        self.setup_location()

        await asyncio.gather(
            self.keep_listening_from_mcs(),
            self.keep_listening_from_gnd()
        )

    def run(self):
        asyncio.run(self.run_station_async())


class SerialConnectorRadioStation(BaseRadioStation):
    """
    Implements a generic radio station that connects to lower level
    GND equipment via serial port.
    """
    def __init__(self, mcs_addr, port, baud):
        super().__init__(mcs_addr)

        self.serial_port = port
        self.baudrate = int(baud)

        self.gnd_reader = None
        self.gnd_writer = None

    async def connect_to_gnd(self):
        self.gnd_reader, self.gnd_writer = await serial_asyncio.open_serial_connection(
            url=self.serial_port, baudrate=self.baudrate)
        self.logger.info("Connected to serial port %s, baud %d", self.serial_port, self.baudrate)

    async def recv_from_gnd(self):
        packet_bin = await self.gnd_reader.readuntil(b'\n')
        packet = packet_bin.rstrip().decode()
        return packet
