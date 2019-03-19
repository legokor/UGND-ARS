import socket

from .connector import Connector


class SocketConnector(Connector):
    def __init__(self, ip, port):
        super().__init__()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((ip, port))
        print('Connected to socket ' + ip + ':' + str(port))

    def send(self, message):
        self.socket.send(bytes(message, 'UTF-8'))

    def listen(self):
        while self.listening:
            bt = self.socket.recv(1)
            self.callback(bt)

    def destruct(self):
        self.socket.close()
