import typing
import asyncio
import io
import math
import abc
import enum
from anf.packet.integral import *
from anf.packet.bytestr import *
from anf.packet.struct import *
from anf.packet.tunneling import *
from anf.packet.ipacket import *
from anf.packet.misc import *
from anf.packet.repeaters import *
from anf.packet.mappings import *
from anf.packet.conditional import *
from anf.packet.context import *
from anf.stream import *


T = typing.TypeVar("T")


async def test(packet: IPacket[T], obj: T, verbose: bool = True) -> bool:
    if verbose:
        print("packet:", packet)
        print("obj:", obj)
    stream = BytesStream()
    await packet.encode(stream, obj)
    enc = stream.get_data()
    if verbose:
        print("enc:", enc.hex())
    stream.reset()
    dec = await packet.decode(stream)
    if verbose:
        print("dec:", dec)

    return obj == dec


def _hash_sum8(data: bytes) -> int:
    return sum(data) % 256


ByteSumZero = postponed(Checksum(
    UInt8,
    _hash_sum8,
    joined_enc_partial(),
    compute=lambda ctx, hashed: (-hashed) % 256,
    validate=lambda ctx, value, hashed: hashed == 0
))


def _gen_my_struct() -> Struct:
    """
    MyStruct = Struct(
        magic=Const(b"ABEL"),
        id=VarInt,
        msg=CString(),
    )
    """

    """
    class MyStruct(metaclass=Struct):
        magic = Const(b"ABEL")
        id = VarInt
        msg = CString()
    """

    # This way and with metaclass and "_" you can add unnamed fields
    MyStruct = Struct(
        Const(b"ABEL"),
        "id" / VarInt,
        "msg" / CString(),
        "is_cool" / Default(Flag, False),
        "how_cool" / Conditional(this.is_cool, Default(CString(), "AWESOME!")),
        Checksum(
            UInt8,
            _hash_sum8,
            # encoded(this.msg)
            joined_enc_partial()
        )
    )

    return MyStruct


async def main():
    my_struct = _gen_my_struct()
    my_struct_val = dict(id=123, msg="Woah, structs too?!", is_cool=True)

    # checksum_weird = Struct(
    #     Const(b"MAGIC"),
    #     postponed(Deduced(UInt8, lambda ctx: (-_hash_sum8(joined_enc_partial()(ctx))) % 256)),
    #     "data" / Bytes(10),
    #     postponed(Check(lambda ctx: _hash_sum8(joined_enc_partial()(ctx)) == 0))
    # )

    # noinspection PyPep8Naming
    class checksum_weird(metaclass=Struct):
        _ = Const(b"MAGIC")
        _ = ByteSumZero
        data = Bytes(10)
    checksum_weird_val = dict(data=b'0123456789')

    some_enum = Enum(
        UInt8,
        dict(a=1, b=2, secret=0xf0),
        metaname="SomeEnum",
        flags=True
    )

    options = (
        (VarInt, 0),
        (ZigZag, 12345678),
        (Bytes(4), b'abel'),
        (BytesInt(12, False), 123456),
        (CountPrefixed(VarInt, Bytes), b'Abel is the best!'),
        (SizePrefixed(UInt8, GreedyBytes), b"Indeed he is!"),
        (Padded(VarInt, 4), 123456),
        (PaddedString(32), "???????????? ??????????????"),
        (PaddedString(4), "ABEL"),
        (CString(), "???????????? ?????????????? 2: ????????-????????????????????"),
        (PascalString(VarInt), "This time it's size-prefixed!"),
        (Aligned(UInt16, 4), 777),
        (checksum_weird, checksum_weird_val),
        (Array[int](UInt16, 5), [6, 8, 10, 12, 77]),
        (CString()[3], ["Hello", "Dear", "World"]),
        (CountPrefixedArray(VarInt, PaddedString(8)), ["I'm", "here", "again"]),
        (some_enum, some_enum.a | some_enum.secret),
        (Mapping[str, int](VarInt, enc_map={"Hello": 1, "Goodbye": -1, "": 0}), "Hello"),
        (Discriminated[int](UInt8, {0: my_struct, 1: PaddedString(8)}), (1, "Hi!!!")),
        (my_struct, my_struct_val, False),
    )

    for option in options:
        if len(option) == 2:
            option = (*option, True)

        packet, obj, check = option

        result: bool = await test(packet, obj)

        if check and not result:
            print("ERROR!  ^^^")

        print()

    # print(await my_struct.decode_bytes(
    #     b"ABEL\x01Woah, structs too?!\x00\x54"
    # ))


if __name__ == "__main__":
    asyncio.run(main())


exit(0)


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
                            await CmdPacket(0, packet.arg).encode(stream)
                        case 1:
                            await CmdPacket(0, "Bye!").encode(stream)
                            break
                        case 2:
                            await CmdPacket(0, "Stopping...").encode(stream)
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

        data = TwoCmdPackets(CmdPacket(0, "Hi!"), CmdPacket(2, "..."))
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
