"""Políticas HTTP locais e limitação compartilhada entre os aliases de login."""
from collections import deque
import ipaddress
import threading
import time
from urllib.parse import urlsplit


class LoginLimiter:
    def __init__(self, limit=5, window=900, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.attempts = {}
        self.lock = threading.RLock()

    def reserve(self, ip, username):
        username = str(username or '').strip().casefold().removesuffix('@radache.local')
        keys = (('ip', ip), ('user', username))
        with self.lock:
            now = self.clock()
            for key in list(self.attempts):
                queue = self.attempts[key]
                while queue and queue[0] <= now - self.window:
                    queue.popleft()
                if not queue:
                    del self.attempts[key]
            if any(len(self.attempts.get(key, ())) >= self.limit for key in keys):
                return None
            for key in keys:
                self.attempts.setdefault(key, deque()).append(now)
            return keys, now

    def allow(self, ip, username):
        return self.reserve(ip, username) is not None

    def release(self, ticket):
        keys, instant = ticket
        with self.lock:
            for key in keys:
                queue = self.attempts.get(key)
                if queue and instant in queue:
                    queue.remove(instant)


LOGIN_LIMITER = LoginLimiter()


def loopback(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def same_origin(origin, host, secure=False):
    try:
        parsed = urlsplit(origin)
        return (parsed.scheme == ('https' if secure else 'http')
                and parsed.netloc.casefold() == host.casefold()
                and not parsed.username and not parsed.password)
    except ValueError:
        return False
