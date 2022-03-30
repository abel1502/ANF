import asyncio
import abc
import typing
import struct

from stream import *


class PacketDecodeError(Exception):
    pass


class IPacket(abc.ABC):
    """
    The base interface for a packet

    Other requirements:
     - Must be default-constructible, which would correspond to an empty packet
    """

    @abc.abstractmethod
    def clear(self) -> None:
        pass

    @abc.abstractmethod
    def is_set(self) -> bool:
        pass

    @abc.abstractmethod
    async def encode(self, stream: Stream) -> None:
        pass

    @abc.abstractmethod
    async def decode(self, stream: Stream) -> None:
        pass


class StructPacket(IPacket):
    struct_layout: (struct.Struct | None) = None
    field_names: (typing.Tuple[str, ...] | None) = None
    attr_access: bool = False

    def __init__(self, *args, **kwargs):
        assert self.struct_layout is not None
        assert self.field_names is not None

        self._data: typing.List[typing.Any | None]

        self.clear()

        if args:
            assert len(args) == len(self)
            assert not kwargs
            self._data = list(args)
        elif kwargs:
            self._data = [kwargs.get(name, None) for name in self.field_names]
            assert len(set(kwargs.keys()) - set(self.field_names)) == 0, "Extraneous kwargs"

    def __getitem__(self, idx: int | str):
        return self.field(idx)

    def field(self, idx: int | str) -> typing.Any:
        if isinstance(idx, str):
            idx = self.field_names.index(idx)

        return self._data[idx]

    def __getattr__(self, name: str):
        if not self.attr_access or name not in self.field_names:
            raise AttributeError()

        return self.field(name)

    def is_set(self) -> bool:
        return all(map(lambda x: x is not None, self._data))

    @classmethod
    def size(cls) -> int:
        return cls.struct_layout.size

    @classmethod
    def __len__(cls) -> int:
        return len(cls.field_names)

    def clear(self):
        self._data = [None] * len(self)

    async def encode(self, stream: Stream) -> None:
        assert self.is_set()

        encoded_data = self.struct_layout.pack(*self._data)

        await stream.send(encoded_data)

    async def decode(self, stream: Stream) -> None:
        encoded_data = await stream.recv(self.size())

        try:
            self._data = self.struct_layout.unpack(encoded_data)
        except struct.error as e:
            raise PacketDecodeError from e

    @staticmethod
    def parse_definition(*args: str, order="<") -> typing.Tuple[struct.Struct, typing.Tuple[typing.Any, ...]]:
        """
        Parses a structure definition in a convenient format.

        :param args: The structure's definition in the format of
            "&lt;fmt&gt;" or "&lt;fmt&gt;:&lt;name&gt;", where &lt;fmt&gt; is passed to the struct,
            and &lt;name&gt; is kept as the new field's name. If the field has no
            name, it must have &lt;fmt&gt;="x"
        :param order: Passed to the struct as its format's first character
        :return: struct_layout and field_names, corresponding to the input
        """

        struct_layout = [order]
        field_names = []
        for arg in args:
            if ":" not in arg:
                assert arg == "x"
                struct_layout.append(arg)
                continue

            fmt, name = arg.split(":", 1)
            struct_layout.append(fmt)
            field_names.append(name)

        struct_layout = struct.Struct("".join(struct_layout))
        field_names = tuple(field_names)

        return struct_layout, field_names

    @staticmethod
    def create(*args: str, order="<", name=None, attr_access: bool = None) -> typing.Type["StructPacket"]:
        """
        Creates a new subclass for a given struct
        """

        if name is None:
            name = "CustomStructPacket"

        if attr_access is None:
            attr_access = StructPacket.attr_access

        struct_layout, field_names = StructPacket.parse_definition(*args, order=order)

        return typing.cast(typing.Type["StructPacket"], type(name, (StructPacket,), {
            "struct_layout": struct_layout,
            "field_names": field_names,
            "attr_access": attr_access
        }))

    def __repr__(self):
        data_repr = []

        for name, val in zip(self.field_names, self._data):
            data_repr.append(f"{name}={val!r}")

        data_repr = ", ".join(data_repr)

        return f"{type(self).__name__}({data_repr})"


class CompoundPacket(IPacket):
    class Member:
        __slots__ = ("packet_type", "name")

        def __init__(self, packet_type: typing.Type[IPacket], name: (str | None) = None):
            self.packet_type = packet_type
            self.name = name

        def is_unnamed(self) -> bool:
            return self.name is None

    members: (typing.Tuple[Member, ...] | None) = None
    attr_access: bool = False

    def __init__(self, *args, **kwargs):
        assert self.members is not None

        self._data: typing.List[IPacket]

        self.clear()

        if args:
            assert len(args) == len(self)
            assert not kwargs
            self._data = list(args)
            assert self._validate_types()
        elif kwargs:
            self._data = [kwargs.get(member.name, member.packet_type()) for member in self.members]
            assert len(set(kwargs.keys()) - set(self._member_names())) == 0, "Extraneous kwargs"
            assert self._validate_types()

    def _validate_types(self) -> bool:
        if self._data is None or len(self._data) != len(self.members):
            return False

        for i, member in enumerate(self.members):
            packet = self._data[i]

            if packet is None or not isinstance(packet, member.packet_type):
                return False

        return True

    def _member_names(self) -> typing.Iterable[str]:
        for member in self.members:
            if member.is_unnamed():
                continue

            yield member.name

    def is_set(self) -> bool:
        assert self._validate_types()

        return all(map(lambda x: x.is_set(), self._data))

    def __getitem__(self, idx: int | str):
        return self.member(idx)

    def member(self, idx: int | str) -> IPacket:
        if isinstance(idx, str):
            idx = list(self._member_names()).index(idx)

        return self._data[idx]

    def __getattr__(self, name: str):
        if not self.attr_access or name not in self._member_names():
            raise AttributeError()

        return self.member(name)

    @classmethod
    def __len__(cls) -> int:
        return len(cls.members)

    def clear(self):
        self._data = [member.packet_type() for member in self.members]

    async def encode(self, stream: Stream) -> None:
        assert self.is_set()

        for packet in self._data:
            await packet.encode(stream)

    async def decode(self, stream: Stream) -> None:
        for packet in self._data:
            await packet.decode(stream)

    @staticmethod
    def parse_definition(*args: "CompoundPacket.Member" |
                                typing.Tuple[typing.Type[IPacket], str] |
                                typing.Type[IPacket]) -> typing.Tuple["CompoundPacket.Member", ...]:
        members = []

        for arg in args:
            member: CompoundPacket.Member

            match arg:
                case CompoundPacket.Member():
                    member = arg
                case (packet_type, str()) if issubclass(packet_type, IPacket):
                    member = CompoundPacket.Member(*arg)
                case packet_type if issubclass(packet_type, IPacket):
                    member = CompoundPacket.Member(arg)
                case _:
                    raise TypeError(f"Unexpected argument {arg} of type {type(arg).__name__}")

            members.append(member)

        return tuple(members)

    @staticmethod
    def create(*args: "CompoundPacket.Member" |
                      typing.Tuple[typing.Type[IPacket], str] |
                      typing.Type[IPacket],
                      name: str = None,
                      attr_access: bool = None) -> typing.Type["CompoundPacket"]:
        if name is None:
            name = "CustomCompoundPacket"

        if attr_access is None:
            attr_access = CompoundPacket.attr_access

        members = CompoundPacket.parse_definition(*args)

        return typing.cast(typing.Type["CompoundPacket"], type(name, (CompoundPacket,), {
            "members": members,
            "attr_access": attr_access
        }))

    def __repr__(self):
        data_repr = []

        for member, val in zip(self.members, self._data):
            prefix = ""
            if not member.is_unnamed():
                prefix = f"{member.name}="
            data_repr.append(f"{prefix}{val!r}")

        data_repr = ", ".join(data_repr)

        return f"{type(self).__name__}({data_repr})"


class BaseHeaderPacket(IPacket):
    header_type: (typing.Type[IPacket] | None) = None

    @abc.abstractmethod
    def validate(self) -> bool:
        """
        Tests for header correctness.
        If the header is not set, the packet is correct.

        :return: True if header is correct
        """
        pass

    async def on_encode(self) -> None:
        pass

    async def on_decode(self) -> None:
        pass

    @typing.overload
    def __init__(self):
        ...

    @typing.overload
    def __init__(self, header: IPacket, data: IPacket):
        ...

    def __init__(self, *args):
        assert self.header_type is not None

        self._header: IPacket
        self._content: IPacket | None

        self.clear()

        if not args:
            return

        assert len(args) == 2
        self._header = args[0]
        self._content = args[1]
        assert self.validate()

    @property
    def header(self) -> IPacket:
        return self._header

    @property
    def content(self) -> IPacket | None:
        return self._content

    def is_set(self) -> bool:
        assert not self.header.is_set() or self.validate()
        return self.header.is_set() and self.content is not None and self.content.is_set()

    def clear(self) -> None:
        self._header = self.header_type()
        self._content = None

    async def encode(self, stream: Stream) -> None:
        assert self.is_set()

        await self.on_encode()
        assert self.validate()  # Because the content may be set in on_encode
        await self.header.encode(stream)
        await self.content.encode(stream)

    async def decode(self, stream: Stream) -> None:
        await self.header.decode(stream)
        await self.on_decode()
        await self.content.decode(stream)

    @staticmethod
    def make_struct_header(header_struct_spec: str,
                           name: str = None,
                           order: str = "<",
                           attr_access: bool = None) -> typing.Type["StructPacket"]:
        name = f"{name}_header" if name is not None else None
        return StructPacket.create(f"{header_struct_spec}:value",
                                   order=order,
                                   name=name,
                                   attr_access=attr_access)

    def __repr__(self):
        return f"{type(self).__name__}(header={self.header!r}, content={self.content!r})"


def _replace_method(cls: typing.Type, name: str, new_method: typing.Callable):
    old_method = getattr(cls, name)

    setattr(cls, name, lambda self, *args, **kwargs: new_method(old_method, self, *args, **kwargs))

    return cls


class DiscriminatedPacket(BaseHeaderPacket):
    content_types: (typing.Mapping[int, typing.Type[IPacket]] | None) = None

    @abc.abstractmethod
    def get_id(self) -> int:
        pass

    def validate(self) -> bool:
        if not self.header.is_set():
            return True

        return isinstance(self.header, self.header_type) and \
            isinstance(self.content, self.get_content_type())

    def get_content_type(self) -> typing.Type[IPacket]:
        assert self.header.is_set()

        return self.content_types[self.get_id()]

    async def on_encode(self) -> None:
        pass

    async def on_decode(self) -> None:
        try:
            content_type = self.get_content_type()
        except KeyError as e:
            raise PacketDecodeError() from e

        self._content = content_type()

    @staticmethod
    def create(header_type: typing.Type[IPacket],
               content_types: typing.Mapping[int, typing.Type[IPacket]],
               get_id: typing.Callable[[typing.Any], int],
               name: str = None) -> typing.Type["DiscriminatedPacket"]:
        if name is None:
            name = "CustomDiscriminatedPacket"

        return typing.cast(typing.Type["DiscriminatedPacket"], type(name, (DiscriminatedPacket,), {
            "header_type": header_type,
            "content_types": content_types,
            "get_id": get_id
        }))

    @staticmethod
    def create_simple(header_struct_spec: str,
                      content_types: typing.Mapping[int, typing.Type[IPacket]],
                      **kwargs) -> typing.Type["DiscriminatedPacket"]:
        assert header_struct_spec.replace("x", "") in "BHILQN", \
            "header_struct_spec must be a struct format for a single integer with optional padding"

        header_type = DiscriminatedPacket.make_struct_header(header_struct_spec, **kwargs,
                                                             attr_access=True)
        packet_type = DiscriminatedPacket.create(header_type, content_types, lambda self: self.header.value)

        def __init__(old_init, self, *args):
            args = list(args)

            if len(args) == 2 and isinstance(args[0], int):
                args[0] = self.header_type(value=args[0])

            old_init(self, *args)

        _replace_method(packet_type, "__init__", __init__)

        return packet_type


class BasicBytesPacket(IPacket):
    """
    A very basic packet class that transmits and receives a dynamically specified number of bytes. Chances are, you
    don't want to use it directly. Try DynamicBytesPacket instead
    """

    @typing.overload
    def __init__(self):
        ...

    @typing.overload
    def __init__(self, data: bytes):
        ...

    @typing.overload
    def __init__(self, size: int):
        ...

    def __init__(self, arg=None):
        self._data: bytes | None
        self._expected_size: int | None

        self.clear()

        if isinstance(arg, bytes):
            self._data = arg
        elif isinstance(arg, int):
            self._expected_size = arg

    @property
    def data(self) -> bytes | None:
        return self._data

    @data.setter
    def data(self, value: bytes) -> None:
        assert value is not None
        self._data = value

    def expect_size(self, size: int):
        assert size is not None
        self._expected_size = size

    def clear(self) -> None:
        self._data = None
        self._expected_size = None

    def is_set(self) -> bool:
        return self.data is not None

    async def encode(self, stream: Stream) -> None:
        assert self.is_set()

        await stream.send(self.data)

    async def decode(self, stream: Stream) -> None:
        assert self._expected_size is not None, "You must always call `expect_size()` before `decode()`"

        self._data = await stream.recv(self._expected_size)
        self._expected_size = None

    def __repr__(self):
        return f"BasicBytesPacket(data={self.data!r})"


class DynamicBytesPacket(BaseHeaderPacket):
    """
    A wrapper around BasicBytesPacket (which is transmitted as `content`) that also includes a header to transmit the
    data's length
    """

    @abc.abstractmethod
    def get_size(self) -> int:
        pass

    def _get_content(self) -> BasicBytesPacket:
        return typing.cast(BasicBytesPacket, self.content)

    def validate(self) -> bool:
        if not self.header.is_set():
            return True

        return isinstance(self.header, self.header_type) and \
            isinstance(self.content, BasicBytesPacket)

    @property
    def data(self) -> bytes | None:
        return self._get_content().data

    @data.setter
    def data(self, value: bytes) -> None:
        self._get_content().data = value

    async def on_encode(self) -> None:
        pass

    async def on_decode(self) -> None:
        self._content = BasicBytesPacket(self.get_size())

    @staticmethod
    def create(header_type: typing.Type[IPacket],
               get_size: typing.Callable[[typing.Any], int],
               name: str = None) -> typing.Type["DynamicBytesPacket"]:
        if name is None:
            name = "CustomDynamicBytesPacket"

        packet_type = typing.cast(typing.Type["DynamicBytesPacket"], type(name, (DynamicBytesPacket,), {
            "header_type": header_type,
            "get_size": get_size
        }))

        def __init__(old_init, self, *args):
            args = list(args)

            if len(args) == 2 and isinstance(args[1], bytes):
                args[1] = BasicBytesPacket(args[1])

            old_init(self, *args)

        _replace_method(packet_type, "__init__", __init__)

        return packet_type

    @staticmethod
    def create_simple(header_struct_spec: str,
                      **kwargs) -> typing.Type["DynamicBytesPacket"]:
        assert header_struct_spec.replace("x", "") in "BHILQN", \
            "header_struct_spec must be a struct format for a single integer with optional padding"

        header_type = DynamicBytesPacket.make_struct_header(header_struct_spec, **kwargs,
                                                            attr_access=True)
        packet_type = DynamicBytesPacket.create(header_type, lambda self: self.header.value)

        def __init__(old_init, self, *args):
            args = list(args)

            if len(args) == 2 and isinstance(args[0], int):
                args[0] = self.header_type(args[0])
            elif len(args) == 1 and isinstance(args[0], bytes):
                args = [self.header_type(len(args[0])), args[0]]

            old_init(self, *args)

        _replace_method(packet_type, "__init__", __init__)

        return packet_type
