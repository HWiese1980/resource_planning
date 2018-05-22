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
            dur += e[3]
            dur_h += e[3].total_seconds()/3600.0
        overunder = dur_h - get_working_hours_func(d)
        overunder_sum += overunder

        c = Colour.RED if overunder < 0.0 else Colour.BLUE
        overunder_str = f"{Colour.BOLD}{c}{overunder:>4.1f}{Colour.END}"

        log.info(f" {dt.strftime(d, '%d.%m.%Y')}; duration: {dur_h:>4.2f} hours, => +/- {overunder_str} hours")

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
        items = sorted(days[d], key=lambda x: x[1])

        for i, first in enumerate(items[:-1]):
            second = items[i+1]

            if first[1].date() != first[2].date():
                log.warn(f"    [step] {first[0]:<10s} overlaps midnight")
            if second[1].date() != second[2].date():
                log.warn(f"    [step] {second[0]:<10s} overlaps midnight")

            f_end_str = dt.strftime(first[2], "%H:%M:%S")
            s_start_str = dt.strftime(second[1], "%H:%M:%S")

            diff = second[1] - first[2]
            if diff.total_seconds() >= gap_threshold_seconds:
                stat = "gap"
                okay = False
            elif diff.total_seconds() <= -gap_threshold_seconds:
                stat = "ovl"
                okay = False
            else:
                stat = None

            if stat:
                log.warn(f"    [{stat}] {abs(diff.total_seconds()):>8.0f}s; {first[0]:10s} and {second[0]:10s} on {first[2].date()}: {f_end_str} -> {s_start_str}")

    return okay

@check("Completeness")
def check_for_completeness(days, actual_work_days):
    okay = True
    for d in actual_work_days:
        if d.date() >= datetime.datetime.today().date():
            break
        if d.date() not in days:
            log.warn("Workday %s has no entry" % dt.strftime(d.date(), "%d.%m.%Y"))
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

class ResourcePlanner:
    def __init__(self, start_date, end_date, config):
        self.api_key = config.api["api_key"]
        self.holidays = parse_holidays(config.holidays)
        self.api = Api(self.api_key)
        self.ws = self.api.workspaces
        self.start = start_date
        self.end = end_date
        self.worktimings = config.settings["worktimings"]
        self.weekends = config.settings["weekends"]

        self.bh = WorkingHours(self.start, self.end, weekends = self.weekends, worktimings = self.worktimings, holidays = self.holidays)
        Workspace.working_hours = self.bh
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
    def show_percents(self):
        for ws in self.ws:
            ws_obj = Workspace(ws)

            log.info(mk_headline(f"Times in Workspace {ws}", "*"))
            days = {}
            seconds = {}
            total_time = tdelta(0)

            project_seconds = {
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

                    if start.date() not in days:
                        days[start.date()] = []

                    if (p_name == "Holidays"
                        or (hasattr(i, "tags")
                            and "Pause" in i.tags)):
                        days[start.date()].append(("Pause", start, end, dur))
                        continue
                    else:
                        if p_name not in project_seconds:
                            project_seconds[p_name] = 0.0

                        project_seconds[p_name] += dur.total_seconds()
                        days[start.date()].append((p_name, start, end, dur))

            check_for_expected_hours(days, self.get_working_hours)
            check_for_gaps_and_overlaps(days)

            for h in self.bh.holidays:
                if h[1] == "Holidays":
                    continue

                d = h[0].date()
                if d < self.start.date() or d > self.end.date():
                    continue

                dwh = self.bh.get_daily_working_hours()
                project_seconds[h[1]] += tdelta(hours=dwh).total_seconds()
                total_time += tdelta(hours = dwh)
                if d not in days:
                    days[d] = []
                days[d].append((h[1], d, add_hours(d, dwh), tdelta(hours = dwh)))

            check_for_completeness(days, self.bh.get_actual_work_days())
            check_weekends(days, self.weekends)

            log.info(mk_headline(f"Resulting Resource Distribution", "="))
            log.info(mk_headline(sgn="-"))
            perc_sum = 0.0
            for p_name in project_seconds:
                phours = project_seconds[p_name] / 3600.
                percent = phours / self.bh.gethours() * 100.
                if percent < 5.0:
                    continue

                if p_name != "Vacations" and p_name != "Sick":
                    total_time += tdelta(hours = phours)

                perc_sum += percent
                log.info(f"    {p_name:<20s}: {percent:>3.0f}% (hours: {phours:>10.1f})")

            log.info(mk_headline("Total hours in the given period", "-"))
            total_hours = total_time.total_seconds() / 3600.
            log.info(f" {total_hours:>3.1f} hours => {total_hours/self.bh.gethours() * 100.:>3.0f}%")
            log.info(mk_headline(sgn="="))

def main():
    parser = argparse.ArgumentParser()
    curr_month = int(datetime.datetime.now().strftime("%m"))
    curr_year = int(datetime.datetime.now().strftime("%Y"))
    parser.add_argument("month", nargs="?", default=curr_month, type=int, help="Month of this year to be evaluated")
    parser.add_argument("--year", default=curr_year, type=int, help="Year of the given month to be evaluated")
    parser.add_argument("--start", type=str, default=False, help="Start date of period to be evaluated")
    parser.add_argument("--end", type=str, default=False, help="End date of period to be evaluated")
    parser.add_argument("--config", "-c", default=config_file, help="File containing configuration")
    parser.add_argument("--ezve", "-e", default=False, help="Print out EZVE CSV")

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
    rp.show_percents()

if __name__ == "__main__":
    main()
