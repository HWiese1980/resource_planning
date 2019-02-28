from datetime import datetime as dt

from replan.functions import format_td


class Entry:
    def __init__(self, name, start, end, duration, tags = None):
        assert hasattr(start, "time"), "Start of entry must have time information"
        assert hasattr(end, "time"), "End of entry must have time information"

        self.name = name
        self.start = start
        self.end = end
        self.duration = duration
        self.tags = tags or []

    def __repr__(self):
        return f"{self.name} {dt.strftime(self.start, '%H:%M')} - {dt.strftime(self.end, '%H:%M')} => {format_td(self.duration)} [{', '.join(self.tags)}]"