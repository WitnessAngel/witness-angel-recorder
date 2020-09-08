import sys

from decorator import decorator
from kivy.logger import Logger as logger


@decorator
def safe_catch_unhandled_exception(f, *args, **kwargs):
    try:
        return f(*args, **kwargs)
    except Exception as exc:
        try:
            logger.error(
                f"Caught unhandled exception in call of function {f!r}: {exc!r}",
                exc_info=True
            )
        except Exception as exc2:
            print(
                f"Beware, service callback {f!r} and logging system are both broken: {exc2!r}"
            )
