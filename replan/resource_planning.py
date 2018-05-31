#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-

from toggl.api import Api
import yaml
from datetime import datetime as dt, timedelta as tdelta, timezone as tz
import datetime
from calendar import monthrange
import os

__all__ = ["main"]

from resource_objects import *

config_file = os.path.expanduser("~/.toggl_summary/config.yaml")

import pprint
import dateutil
import argparse
import logging
import logutils
from resource_logging import RainbowLoggingHandler

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
pp = pprint.PrettyPrinter()

gap_threshold_seconds = 60

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
hdl = RainbowLoggingHandler()
hdl.setLevel(logging.DEBUG)
log.addHandler(hdl)

class Colour:
   PURPLE = '\033[95m'
   CYAN = '\033[96m'
   DARKCYAN = '\033[36m'
   BLUE = '\033[94m'
   GREEN = '\033[92m'
   YELLOW = '\033[93m'
   RED = '\033[91m'
   BOLD = '\033[1m'
   UNDERLINE = '\033[4m'
   END = '\033[0m'

def mk_headline(msg = "", sgn = "-", l = 90, indent = 3):
    h = [sgn]*l
    if msg != "":
        h[indent:indent+len(msg)+2] = list(f" {msg} ")
    h = "".join(h)
    return h

def check(msg):
    def wrap(func):
        def wrapper(*args, **kwargs):
            m = f"Check: {msg}"
            log.info(mk_headline(m, ">", indent = 5))
            log.info(mk_headline("Output"))
            okay = func(*args, **kwargs)
            if not okay:
                log.warn(mk_headline("Not OK!"))
            log.info(mk_headline(sgn="<"))
            log.info("")
            return okay
        return wrapper
    return wrap

class YamlBase(yaml.YAMLObject):
    @classmethod
    def from_yaml(cls, loader, node, *args, **kwargs):
        fields = loader.construct_mapping(node, deep = True)
        yield cls(**fields)

    def __init__(self, *args, **kwargs):
        for attr in kwargs:
            val = kwargs[attr]
            log.debug("YAML Base %s: set Attribute %s -> %s" % (self.__class__.__name__, attr, val))
            setattr(self, attr, val)


class Config(YamlBase):
    yaml_tag = u"!Config"


class Mapping(YamlBase):
    yaml_tag = u"!Mapping"

    def __repr__(self):
        return f"Map to {self.productive_project}"

class ProductivityMapping(YamlBase):
    yaml_tag = u"!PMapping"

    def __init__(self, name, mappings):
        self.name = name
        self.mappings = mappings

    def __repr__(self):
        return f"Mappings for {self.name}: {', '.join([str(s) for s in self.mappings])}"

class ProductivityMappingDict(YamlBase):
    yaml_tag = u"!PMappingDict"

    def __getitem__(self, i):
        ret = [s for s in self.mappings if s.name == i]
        assert len(ret) <= 1, f"There's more than one mapping for project {i}"
        return ret[0]

    def __iter__(self):
        return self.mappings.__iter__()

class WorkingHours:
    def __init__(self, start, end, sum_of_breaks = 1, worktimings=None, weekends=None, holidays=None):
        self.start = start
        self.end = end
        self.breaks = sum_of_breaks
        self.worktimings = worktimings or [9, 18]
        self.weekends = weekends or [6, 7]
        self.holidays = holidays or []

    def get_holidays(self):
        return [d[0].date() for d in self.holidays if d[1] == "Holidays"]

    def get_vacations(self):
        return [d[0].date() for d in self.holidays if d[1] == "Vacations"]

    def get_sick_days(self):
        return [d[0].date() for d in self.holidays if d[1] == "Sick"]

    def get_daily_working_hours(self):
        return self.worktimings[1] - self.worktimings[0]

    def get_all_work_days(self):
        diff = (self.end+tdelta(days=1)) - self.start
        # log.info(f"{self.start.date()} - {self.end.date()} => {diff}")
        days = 0
        for i in range(diff.days):
            day = self.start + tdelta(i)
            sday = dt.strftime(day, "%d.%m.%Y")
            wd = day.weekday()+1
            if wd not in self.weekends:
                yield day

    def get_actual_work_days(self):
        for d in self.get_all_work_days():
            if d.date() not in self.get_holidays():
                yield d

    def getdays(self):
        return len(list(self.get_actual_work_days()))

    def gethours(self):
        days = self.getdays()
        worktiming = self.worktimings[1] - self.worktimings[0] - self.breaks
        return days * worktiming

def parse_holidays(h):
    holidays = []
    for y in h:
        year = h[y]
        for htype in year:
            for month in year[htype]:
                for day in year[htype][month]:
                    if isinstance(day, (list, tuple)):
                        for d in range(day[0], day[1]+1):
                            date_time_object = dt(y, month, d)
                            holidays.append((date_time_object, htype))
                    elif isinstance(day, int):
                        date_time_object = dt(y, month, day)
                        holidays.append((date_time_object, htype))
    return holidays

def add_days(date, number):
    return date + tdelta(days = number)

def add_hours(date, number):
    return date + tdelta(hours = number)

def add_minutes(date, number):
    return date + tdelta(minutes = number)

def add_seconds(date, number):
    return date + tdelta(seconds = number)

@check("Expected hours")
def check_for_expected_hours(days, get_working_hours_func):
    days_sorted = sorted(days.keys())
    overunder_sum = 0.0
    for d in days_sorted:
        dur = tdelta(hours = 0)
        dur_h = 0.0
        for e in days[d]:
            dur += e.duration
            dur_h += e.duration.total_seconds()/3600.0
        overunder = dur_h - get_working_hours_func(d)
        overunder_sum += overunder

        c = Colour.RED if overunder < 0.0 else Colour.BLUE
        overunder_str = f"{Colour.BOLD}{c}{overunder:>4.1f}{Colour.END}"

        log.info(f" {dt.strftime(d, '%d.%m.%Y')}; duration: {dur_h:>5.2f} hours, => +/- {overunder_str} hours")

    log.info(mk_headline("Sum of daily hours"))
    log.info(f" +/- {overunder_sum:>8.1f} hours")

    log.info(mk_headline("So..."))
    if overunder_sum < 0.0:
        log.warn("  You have a negative time record in the given period!")
    elif overunder_sum > 0.0:
        log.info("  You have worked overtime in the given period!")

    return overunder_sum >= 0.0

@check("Gaps and overlaps")
def check_for_gaps_and_overlaps(days):
    okay = True
    for d in days:
        items = sorted(days[d], key=lambda x: x.start)

        for i, first in enumerate(items[:-1]):
            second = items[i+1]

            if first.start.date() != first.end.date():
                log.warn(f"    [step] {first.name:<10s} overlaps midnight")
            if second.start.date() != second.end.date():
                log.warn(f"    [step] {second.name:<10s} overlaps midnight")

            f_end_str = dt.strftime(first.end, "%H:%M:%S")
            s_start_str = dt.strftime(second.start, "%H:%M:%S")

            diff = second.start - first.end
            if diff.total_seconds() >= gap_threshold_seconds:
                stat = "gap"
                okay = False
            elif diff.total_seconds() <= -gap_threshold_seconds:
                stat = "ovl"
                okay = False
            else:
                stat = None

            if stat:
                log.warn(f"    [{stat}] {abs(diff.total_seconds()):>8.0f}s; {first.name:10s} and {second.name:10s} on {first.name.date()}: {f_end_str} -> {s_start_str}")

    return okay

@check("Completeness")
def check_for_completeness(days, actual_work_days):
    okay = True
    for d in actual_work_days:
        if d.date() >= datetime.datetime.today().date():
            break
        if d.date() not in days:
            log.warn(f"Workday {dt.strftime(d.date(), '%d.%m.%Y')} has no entry")
            log.info(f"Entries:{', '.join(days.keys())} ")
            okay = False
    return okay

@check("Weekends")
def check_weekends(days, weekends):
    okay = True
    for d in days:
        if d.weekday()+1 in weekends:
            log.warn(f"Seems like {dt.strftime(d, '%d.%m.%Y')} is set as a weekend day. Were you really working then?")
            okay = False
    return okay

class Entry:
    def __init__(self, name, start, end, duration, tags = None):
        self.name = name
        self.start = start
        self.end = end
        self.duration = duration
        self.tags = tags or []

    def __repr__(self):
        return f"{self.name} {dt.strftime(self.start, '%H:%M')} - {dt.strftime(self.end, '%H:%M')} => {format_td(self.duration)} [{', '.join(self.tags)}]"

def format_td(td):
    s = td.seconds
    dh = s // 3600
    s -= dh*3600
    dm = s // 60
    s -= dm*60
    return f"{dh:02d}:{dm:02d}"

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

class ResourcePlanner:
    def __init__(self, start_date, end_date, config):
        self.config = config

        self.api_key = config.api["api_key"]
        self.holidays = parse_holidays(config.holidays)
        self.api = Api(self.api_key)
        self.ws = self.api.workspaces
        self.start = start_date
        self.end = end_date
        self.worktimings = config.settings["worktimings"]
        self.weekends = config.settings["weekends"]
        self.productivity_mappings = config.productivity_mappings

        self.days = StrictDict(StrictList)

        self.bh = WorkingHours(self.start, self.end, weekends = self.weekends, worktimings = self.worktimings, holidays = self.holidays)
        # Workspace.working_hours = self.bh
        log.info(mk_headline(sgn="="))
        log.info(mk_headline("Resource Planner", "#"))
        log.info(mk_headline(sgn="="))
        log.info("")
        log.info(" Expected working hours in time span %s to %s: %s (%s days)"
              % (dt.strftime(self.start, "%d.%m.%Y"),
                 dt.strftime(self.end, "%d.%m.%Y"),
                 self.bh.gethours(), self.bh.getdays()))
        log.info(mk_headline(sgn = "="))

    def get_working_hours(self, day):
        return self.bh.get_daily_working_hours()

    def load_data(self):
        pass

    def calculate_percents(self):
        for ws in self.ws:
            # ws_obj = Workspace(ws)

            log.info(mk_headline(f"Times in Workspace {ws}", "*"))
            # seconds = {}
            self.total_time = tdelta(0)

            self.project_seconds = {
                "Vacations": 0.0,
                "Sick": 0.0
            }

            for project in ws_obj.native_projects:
                p_name = project.name
                times = project.time_entries.list()

                for i in times:
                    if not hasattr(i, "stop"):
                        log.warn("Entry %s seems to still be running" % i.description)
                        continue
                    start = i.start
                    end = i.stop

                    if start.date() < self.start.date() or end.date() > self.end.date():
                        continue

                    dur = end - start

                    if dur.total_seconds() / 3600. > 11:
                        log.warn("Warning: the entry seems to be too long:")
                        log.warn(f"{p_name} from {start} to {end}; duration {dur}")

                    is_pause = False
                    original_p_name = ""

                    if start.date() not in self.days:
                        self.days[start.date()] = SmartList(Entry)

                    if p_name not in self.project_seconds:
                        self.project_seconds[p_name] = 0.0

                    e = None
                    add_dur = True
                    if (p_name == "Holidays" or (hasattr(i, "tags") and "Pause" in i.tags)):
                        e = Entry(p_name, start, end, dur, ["pause"])
                        add_dur = False
                    elif hasattr(i, "tags") and "Overhead" in i.tags:
                        e = Entry(p_name, start, end, dur, ["overhead"])
                    else:
                        e = Entry(p_name, start, end, dur)

                    self.days[start.date()].append(e)
                    if add_dur: self.project_seconds[p_name] += dur.total_seconds()
    def checks(self):
        log.info(f"Performing checks on {', '.join([str(s) for s in self.days.keys()])}")
        check_for_expected_hours(self.days, self.get_working_hours)
        check_for_gaps_and_overlaps(self.days)
        check_for_completeness(self.days, self.bh.get_actual_work_days())
        check_weekends(self.days, self.weekends)

    def apply_holidays(self):
        for h in self.bh.holidays:
            if h[1] == "Holidays":
                continue

            d = h[0].date()
            if d < self.start.date() or d > self.end.date():
                continue

            dwh = self.bh.get_daily_working_hours()
            self.project_seconds[h[1]] += tdelta(hours=dwh).total_seconds()
            self.total_time += tdelta(hours = dwh)
            if d not in self.days:
                self.days[d] = StrictList(Entry)
            self.days[d].append(Entry(h[1], d, add_hours(d, dwh), tdelta(hours = dwh), ["off"]))

    def output_results(self):
            log.info(mk_headline(f"Resulting Resource Distribution", "="))
            log.info(mk_headline(sgn="-"))
            perc_sum = 0.0
            for p_name in self.project_seconds:
                phours = self.project_seconds[p_name] / 3600.
                percent = phours / self.bh.gethours() * 100.
                if percent < 5.0:
                    continue

                if p_name != "Vacations" and p_name != "Sick":
                    self.total_time += tdelta(hours = phours)

                perc_sum += percent
                log.info(f"    {p_name:<20s}: {percent:>3.0f}% (hours: {phours:>10.1f})")

            log.info(mk_headline("Total hours in the given period", "-"))
            total_hours = self.total_time.total_seconds() / 3600.
            log.info(f" {total_hours:>3.1f} hours => {total_hours/self.bh.gethours() * 100.:>3.0f}%")
            log.info(mk_headline(sgn="="))

    def output_ezve(self):
        log.info(f"Productivity mappings: {self.productivity_mappings}")
        for d in self.days:
            day = self.days[d]

            project_seconds = DefaultDict(0.0)
            day_seconds = 0.0

            for e in day:
                if "pause" in e.tags:
                    continue
                project_seconds[e.name] += e.duration.seconds
                day_seconds += e.duration.seconds

            prod_mapping_names = [m.name for m in self.productivity_mappings]
            for s in project_seconds:
                log.info(f"Project seconds of {s}... in {prod_mapping_names}?")
                mapped_seconds = DefaultDict(0.0)

                if s in prod_mapping_names:
                    mappings = self.productivity_mappings[s].mappings
                    mapping_count = len(mappings)
                    log.info(f"{e.name} has {mapping_count} mappings")
                    for m in mappings:
                        log.info(f"Project {e.name} has productivity mapping: {m.fraction*100.}% of {m.productive_project}")
                        mapped_seconds[m.productive_project] += e.duration.seconds * m.fraction
                else:
                    mapped_seconds[s] = project_seconds[s]

            log.info(mapped_seconds)

            for s in mapped_seconds:
                ps = mapped_seconds[s]
                log.info(f"{s:15s} {ps / day_seconds * 100.:>8.0f}%")

def main():
    parser = argparse.ArgumentParser()
    curr_month = int(datetime.datetime.now().strftime("%m"))
    curr_year = int(datetime.datetime.now().strftime("%Y"))
    parser.add_argument("month", nargs="?", default=curr_month, type=int, help="Month of this year to be evaluated")
    parser.add_argument("year", nargs="?", default=curr_year, type=int, help="Year of the given month to be evaluated")
    parser.add_argument("--start", "-s", type=str, default=False, help="Start date of period to be evaluated")
    parser.add_argument("--end", "-e", type=str, default=False, help="End date of period to be evaluated")
    parser.add_argument("--config", "-c", default=config_file, help="File containing configuration")
    parser.add_argument("--no-checks", "-n", action="store_true", help="Skip all checks")
    parser.add_argument("--ezve", "-z", action="store_true", default=False, help="Print out EZVE CSV")

    args = parser.parse_args()

    if args.start and args.end:
        start = parse(args.start)
        end = parse(args.end)
    else:
        (first, last) = monthrange(args.year, args.month)
        start = datetime.datetime(args.year, args.month, 1, 0, 0, 0)
        end = datetime.datetime(args.year, args.month, last, 23, 59, 59)

    with open(args.config, "r") as f:
        config = yaml.load(f)

    rp = ResourcePlanner(start, end, config = config)
    rp.calculate_percents()
    rp.apply_holidays()
    if not args.no_checks:
        rp.checks()

    if args.ezve:
        rp.output_ezve()
    else:
        rp.output_results()

if __name__ == "__main__":
    main()
