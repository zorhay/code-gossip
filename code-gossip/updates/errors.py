"""Failures callers can report without a traceback."""


class UpdateError(RuntimeError):
    pass


class Busy(UpdateError):
    pass
