from datetime import timedelta as tdelta

from replan.logging import log


class StrictList(list):
    def __init__(self, t):
        self.type = t

    def append(self, value):
        assert isinstance(value, self.type), f"Append: {value} is not of type {self.type}"
        super(StrictList, self).append(value)

    def __setitem__(self, i, value):
        assert isinstance(value, self.type), f"{i} => {value} is not of type {self.type}"
        super(StrictList, self).__setitem__(i, value)


class SmartList(StrictList):
    def shrinked(self):
        ret = DefaultDict(tdelta(0.0))
        for i, u in enumerate(self):
            for j, v in enumerate(self):
                if v is u: continue
            log.info(f"Checking {u} == {v}")
            if u.name == v.name:
                ret[u.name] += v.duration
        return ret


class StrictDict(dict):
    def __init__(self, t):
        self.type = t

    def __setitem__(self, i, value):
        assert isinstance(value, self.type), f"{i} => {value} is not of type {self.type}"
        super(StrictDict, self).__setitem__(i, value)


class DefaultDict(dict):
    def __init__(self, d):
        self.default = d

    def __getitem__(self, i):
        if i not in super(DefaultDict, self).keys():
            super(DefaultDict, self).__setitem__(i, self.default)
        return super(DefaultDict, self).__getitem__(i)