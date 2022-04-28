import typing
import abc
import asyncio
import enum as py_enum

from .ipacket import T, U
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *
from .struct import *
from .integral import *


@IPacket.singleton
class Flag(PacketAdapter[bool, int]):
    def __init__(self):
        super().__init__(UInt8)

    def _modify_enc(self, obj: bool, ctx: Context) -> int:
        PacketObjTypeError.validate(obj, bool)

        return int(obj)

    def _modify_dec(self, obj: int, ctx: Context) -> bool:
        return bool(obj)


Flag: Flag


EnumT = typing.TypeVar("EnumT", bound=py_enum.Enum)


class Enum(PacketAdapter[EnumT, int], typing.Generic[EnumT]):
    def __init__(self, wrapped: IPacket[int], enum: typing.Type[EnumT]):
        super().__init__(wrapped)

        self._enum: typing.Type[EnumT] = enum

    def _modify_enc(self, obj: EnumT, ctx: Context) -> int:
        PacketObjTypeError.validate(obj, py_enum.Enum)

        value = obj.value
        assert isinstance(value, int)

        return value

    def _modify_dec(self, obj: int, ctx: Context) -> EnumT:
        try:
            return self._enum(obj)
        except ValueError as e:
            raise PacketDecodeError from e


__all__ = (
    "Flag",
    "Enum",
)
