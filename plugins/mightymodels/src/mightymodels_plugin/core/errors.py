"""The base of every failure a tool or command reports to its caller instead of crashing on."""


class StateError(Exception):
    pass
