import serial

from .connector import Connector


class SerialConnector(Connector):
    def __init__(self, baud, port):
        super().__init__()
        self.connection = serial.Serial()
        self.connection.baudrate = baud
        self.connection.port = port
        self.connection.open()
        print('Connected to serial port {}'.format(port))

    def send(self, message):
        self.connection.write(message.encode('ascii'))

    def listen(self):
        while self.listening:
            message = self.connection.read(1)
            self.callback(message)

    def destruct(self):
        self.connection.close()
