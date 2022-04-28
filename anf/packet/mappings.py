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
    @typing.overload
    def __init__(self, wrapped: IPacket[int], enum: typing.Type[EnumT]):
        ...

    @typing.overload
    def __init__(self, wrapped: IPacket[int], names: typing.Any, *,
                 flags: bool = False, metaname: str = ""):
        ...

    def __init__(self, wrapped, arg, **kwargs):
        super().__init__(wrapped)

        if isinstance(arg, type) and issubclass(arg, py_enum.Enum):
            arg: typing.Type[py_enum.Enum]
            enum_cls = arg
        else:
            arg: typing.Any
            flags: bool = kwargs.get("flags", False)
            metaname: str = kwargs.get("metaname", "")
            enum_meta: typing.Type[py_enum.Enum] = py_enum.IntFlag if flags else py_enum.IntEnum
            enum_cls = enum_meta(metaname, arg)

        self._enum_cls: typing.Type[EnumT] = enum_cls

    @property
    def enum_cls(self) -> typing.Type[EnumT]:
        return self._enum_cls

    def is_flags(self) -> bool:
        return isinstance(self._enum_cls, py_enum.Flag)

    def _convert(self, obj: int | str | EnumT) -> EnumT:
        """
        :raises ValueError: if obj is not an enum's member
        """

        if isinstance(obj, int):
            # May raise ValueError, but it's fine
            obj = self._enum_cls(obj)
        elif isinstance(obj, str):
            obj = self._enum_cls.__members__.get(obj, None)

        if not isinstance(obj, self._enum_cls):
            raise ValueError(f"Unknown obj type: {type(obj)}")

        return obj

    def __getattr__(self, item: str) -> EnumT:
        try:
            return self._convert(item)
        except ValueError as e:
            raise AttributeError from e

    def _modify_enc(self, obj: EnumT | int | str, ctx: Context) -> int:
        try:
            obj = self._convert(obj)
        except ValueError as e:
            raise PacketObjTypeError from e

        value = obj.value
        assert isinstance(value, int)

        return value

    def _modify_dec(self, obj: int, ctx: Context) -> EnumT:
        try:
            return self._enum_cls(obj)
        except ValueError as e:
            raise PacketDecodeError from e


class Mapping(PacketAdapter[T, U]):
    def __init__(self, wrapped: IPacket[T], *,
                 enc_map: typing.Mapping[U, T] | None = None,
                 dec_map: typing.Mapping[T, U] | None = None,
                 allow_direct: bool = False):
        super().__init__(wrapped)

        if enc_map is not None:
            assert dec_map is None
            self._enc_map = dict(enc_map)
            self._dec_map = dict(zip(enc_map.values(), enc_map.keys()))
        elif dec_map is not None:
            assert enc_map is None
            self._dec_map = dict(dec_map)
            self._enc_map = dict(zip(dec_map.values(), dec_map.keys()))
        else:
            assert False

        self._allow_direct = allow_direct

        assert len(self._enc_map) == len(self._dec_map), "The mapping is not unique"

    def map_enc(self, obj: T) -> U:
        return self._enc_map[obj]

    def map_dec(self, obj: U) -> T:
        return self._dec_map[obj]

    def _modify_enc(self, obj: T | U, ctx: Context) -> U:
        try:
            return self.map_enc(obj)
        except KeyError as e:
            if self._allow_direct and obj in self._dec_map:
                ctx.register_val(self.map_dec(obj))
                return obj
            raise PacketEncodeError from e

    def _modify_dec(self, obj: U, ctx: Context) -> T:
        try:
            return self.map_dec(obj)
        except KeyError as e:
            raise PacketDecodeError from e


__all__ = (
    "Flag",
    "Enum",
    "Mapping",
)
