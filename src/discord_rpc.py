import time
try:
    from pypresence import Presence
except ImportError:
    Presence = None
class DiscordRPC:
    def __init__(self, client_id):
        self.client_id = client_id
        self.rpc = None
    def start(self, details="Managing Lua files"):
        if Presence is None:
            return False, "pypresence is missing"
        if not self.client_id:
            return False, "Discord RPC Client ID is missing"
        if self.rpc is not None:
            return True, None
        try:
            self.rpc = Presence(self.client_id)
            self.rpc.connect()
            self.rpc.update(details=details, start=int(time.time()))
            return True, None
        except Exception:
            self.rpc = None
            return False, "Discord RPC connection failed."
    def stop(self):
        if self.rpc is not None:
            try:
                self.rpc.close()
            except Exception:
                pass
            self.rpc = None