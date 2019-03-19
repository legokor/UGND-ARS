import re


class Wrapper:
    def __init__(self, pattern, reciever, sender):
        self.pattern = pattern
        self.reciever = reciever
        self.sender = sender
        self.buffer = ""

    def consume_character(self, char):
        try:
            self.buffer += char.decode('utf-8')
        except UnicodeDecodeError:
            pass
        if re.search(self.pattern, self.buffer):
            self.digest_message(self.buffer)
            self.buffer = ""

    def digest_message(self, message):
        self.reciever(message)

    def send(self, message):
        self.sender(message)
