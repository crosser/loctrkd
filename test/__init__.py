from typing import Callable, Tuple


__all__ = ("no_less_than",)


def no_less_than(base: str) -> Callable[[str], bool]:
    def _no_less_than(base: str, what: str) -> bool:
        bl, wl = (
            tuple((int(el) for el in s.split("."))) for s in (base, what)
        )

        def __no_less_than(bl: Tuple[int, ...], wl: Tuple[int, ...]) -> bool:
            if len(bl) == 0 and len(wl) == 0:
                return True
            if (len(bl) == 0) != (len(wl) == 0):
                return len(bl) < len(wl)
            # At this point both lists are non-empty
            if bl[0] == wl[0]:
                return __no_less_than(bl[1:], wl[1:])
            return bl[0] < wl[0]

        return __no_less_than(bl, wl)

    return lambda arg: _no_less_than(base, arg)
