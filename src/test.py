from network import *
from packet import *


async def test_example_com():
    async with await connect("example.com", 80) as stream:
        await stream.send(b"GET / HTTP/1.1\r\n"
                          b"Host: example.com\r\n"
                          b"\r\n")

        # resp = await stream.recv(b"\r\n\r\n")
        resp = await stream.recv(4096, exactly=False)

        print(resp.decode())


CmdPacket = StructPacket.create(
    "I:cmd",
    "28s:arg",
    name="CmdPacket",
    attr_access=True
)
assert CmdPacket.size() == 32


class Server(BaseServer):
    class Handler(BaseServerHandler):
        async def handle(self, stream: Stream) -> None:
            while True:
                try:
                    # cmd = await stream.recv(b"\n")
                    # cmd = cmd.decode().strip()
                    # match cmd:
                    #     case "quit":
                    #         await stream.send(b"Bye!\n")
                    #         break
                    #     case "stop":
                    #         await stream.send(b"Stopping...\n")
                    #         self.server.close()
                    #         await self.server.wait_closed()
                    #         return
                    #     case _:
                    #         await stream.send(f"{cmd}\n".encode())

                    packet = CmdPacket()

                    await packet.decode(stream)

                    self.server.log("Got {}", packet)

                    match packet.cmd:
                        case 0:
                            await CmdPacket(cmd=0, arg=packet.arg).encode(stream)
                        case 1:
                            await CmdPacket(cmd=0, arg=b"Bye!").encode(stream)
                            break
                        case 2:
                            await CmdPacket(cmd=0, arg=b"Stopping...").encode(stream)
                            self.server.close()
                            await self.server.wait_closed()
                            return
                except asyncio.IncompleteReadError:
                    # TODO: Handler.log()?
                    self.server.log("Client disconnected...")
                    break

    def get_handler(self) -> BaseServerHandler:
        return self.Handler(self)


async def run_server():
    async with Server() as srv:
        srv: Server

        await srv.run(18878)


async def run_client():
    async with await connect("localhost", 18878) as stream:
        # async def send_cmd(cmd: str):
        #     print(f"> {cmd}")
        #     await stream.send(f"{cmd}\n".encode())
        #
        #     data = await stream.recv(b"\n")
        #     print("<", data.decode().rstrip("\n"))
        #
        # await send_cmd("Hello!")
        # await send_cmd("stop")

        # async def send_cmd(cmd: int, arg: str):
        #     print(f"> {cmd} {arg}")
        #     await CmdPacket(cmd=cmd, arg=arg.encode()).encode(stream)
        #
        #     data = CmdPacket()
        #     await data.decode(stream)
        #     print("<", data.cmd, data.arg.rstrip(b'\0').decode())
        #
        # await send_cmd(0, "Hello")
        # await send_cmd(2, "")

        TwoCmdPackets = CompoundPacket.create(CmdPacket, CmdPacket, name="TwoCmdPackets")

        data = TwoCmdPackets(CmdPacket(cmd=0, arg=b"Hi!"), CmdPacket(cmd=2, arg=b"..."))
        print(">", data)
        await data.encode(stream)

        data.clear()
        await data.decode(stream)
        print("<", data)


async def test_server():
    server = asyncio.create_task(run_server())
    client = asyncio.create_task(run_client())

    await client
    await server


async def main():
    # await test_example_com()

    await test_server()


if __name__ == "__main__":
    asyncio.run(main())
