import abc
import typing


class Context:
    KEEP_ENCODED: typing.ClassVar[bool] = True

    def __init__(self,
                 parent: typing.Optional["Context"] = None,
                 cur_name: str | None = None,
                 members: typing.Dict[str, typing.Any] | None = None):
        self.parent: Context | None = parent
        self.cur_name: str | None = cur_name
        self.members: typing.Dict[str, typing.Any] = members or {}
        self.encoded: typing.Dict[str, typing.Any] = {}

    def get_member(self, name: str, encoded: bool = False) -> typing.Any | "Context":
        if name == ".":
            return self

        if name in ("..", "_"):
            if self.parent is None:
                raise KeyError("Context has no parent")
            return self.parent

        return (self.encoded if encoded else self.members)[name]

    def register_enc(self, data: bytes) -> bytes:
        if self.parent is not None:
            assert self.cur_name is not None
            self.parent.encoded[self.cur_name] = data

        return data


class Path:
    def __init__(self, initial: str | typing.Iterable[str] | "Path" = (), encoded: bool = False):
        if isinstance(initial, Path):
            # noinspection PyProtectedMember
            encoded = initial._encoded
            initial = initial.path

        if isinstance(initial, str):
            initial = self._split_path(initial)
        else:
            initial = list(initial)

        self.path: typing.List[str] = initial
        self._encoded: bool = encoded

    def encoded(self, value: bool = True):
        self._encoded = value

    @staticmethod
    def _split_path(path: str) -> list[str]:
        return path.split("/")

    def __truediv__(self, other: typing.Any) -> "Path":
        copy = Path(self.path, self._encoded)

        copy /= other

        return copy

    def __itruediv__(self, other: typing.Any) -> "Path":
        if isinstance(other, str):
            other = self._split_path(other)

        assert all(isinstance(name, str) for name in other), "A path must only consist of strings"

        self.path += other

        return self

    def __call__(self, ctx: Context) -> typing.Any:
        for name in self.path:
            ctx = ctx.get_member(name, encoded=self._encoded)

        return ctx

    def __repr__(self) -> str:
        return "/".join(self.path)


T = typing.TypeVar("T")


def _wrap_path_func(func: typing.Callable[[typing.Any], T]) \
        -> typing.Callable[[Path], typing.Callable[[Context], T]]:
    return lambda path: lambda ctx: func(path(ctx))


this = Path()
this.__repr__ = lambda self:  f"this/{super()!r}"
len_ = _wrap_path_func(len)
