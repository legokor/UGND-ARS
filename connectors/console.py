import subprocess
from .connector import Connector


class ConsoleConnector(Connector):
    def __init__(self, program):
        super().__init__()
        self.process = subprocess.Popen([program], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)

    def listen(self):
        while self.listening and self.process.poll() is None:
            line = next(self.process.stdout)
            self.callback(line.decode('utf-8'))

    def send(self, message):
        if self.process.poll() is not None:
            self.callback("The process has terminated")
            return
        self.process.stdin.write((message + '\n').encode('utf-8'))
        self.process.stdin.flush()