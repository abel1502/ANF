import typing


class StreamOpenError(Exception): pass
class StreamReadError(Exception): pass
class StreamWriteError(Exception): pass


class PacketEncodeError(Exception): pass
class PacketDecodeError(Exception): pass
class NotSizeableError(Exception): pass
class PacketInvalidError(Exception): pass

