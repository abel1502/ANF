import asyncio
import abc
import datetime
import typing

from stream import *


async def connect(host: str, port: int, **kwargs) -> Stream:
    return Stream(await asyncio.open_connection(host, port, **kwargs))


class BaseServerHandler(abc.ABC):
    def __init__(self, server: "BaseServer"):
        self.server = server

    @abc.abstractmethod
    async def handle(self, stream: Stream) -> None:
        pass


class BaseServer(abc.ABC):
    def __init__(self):
        self._server: (asyncio.AbstractServer | None) = None
        self.verbose = True

    def wait_closed(self) -> typing.Awaitable[None]:
        return self.server_impl.wait_closed()

    async def run(self, port: int, host: (str | None) = None, **kwargs):
        self.log("Starting...")
        self._server = await asyncio.start_server(self._callback, host, port, **kwargs)

        self.log("Awaiting connections")
        serve_forever = self.server_impl.serve_forever()

        try:
            await serve_forever
            await self.wait_closed()
        except asyncio.CancelledError:
            pass
        self.log("Done.")

    def close(self):
        if self.server_impl.is_serving():
            self.log("Shutting down...")
        self.server_impl.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
        await self.wait_closed()

    @property
    def server_impl(self) -> asyncio.AbstractServer:
        if self._server is None:
            raise RuntimeError("Server not started")

        return self._server

    @abc.abstractmethod
    def get_handler(self) -> BaseServerHandler:
        pass

    async def _callback(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        async with Stream((reader, writer)) as stream:
            await self.get_handler().handle(stream)

    # noinspection PyMethodMayBeStatic
    def format_log_msg(self, msg: str) -> str:
        return "[SERVER] [{time:%H:%M:%S}] {msg}".format(time=datetime.datetime.today(), msg=msg)

    def log(self, msg: str, *args, **kwargs):
        if not self.verbose:
            return

        msg = msg.format(*args, **kwargs)
        msg = self.format_log_msg(msg)
        print(msg)


__all__ = ("Stream", "connect", "BaseServerHandler", "BaseServer")
