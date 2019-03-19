import threading


class Connector:
    def __init__(self):
        self._listening = False
        self._callback = lambda: None

    def start_listening(self, callback):
        self._callback = callback
        if not self.listening:
            self._listening = True
            thread = threading.Thread(target=self.listen)
            thread.daemon = True
            thread.start()

    def stop_listening(self):
        if self.listening:
            self.destruct()
        self._listening = False

    @property
    def listening(self):
        return self._listening

    @property
    def callback(self):
        return self._callback

    @callback.setter
    def callback(self, cb):
        self._callback = cb

    def send(self, message):
        pass

    def listen(self):
        pass

    def destruct(self):
        pass
