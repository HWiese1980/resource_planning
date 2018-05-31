#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-

from toggl.api import Api
import yaml
from datetime import datetime as dt, timedelta as tdelta
import datetime
from calendar import monthrange
import os

from replan.checks import check_for_expected_hours, check_for_gaps_and_overlaps, check_for_completeness, check_weekends
from replan.collections import StrictList, SmartList, StrictDict, DefaultDict
from replan.entry import Entry
from replan.functions import add_hours, mk_headline
from replan.logging import log, hdl
from replan.working_hours import WorkingHours, parse_holidays
from replan.yaml_classes import *

__all__ = ["main"]

from resource_objects import *

config_file = os.path.expanduser("~/.toggl_summary/config.yaml")

import pprint
import argparse
import logging

from dateutil.parser import parse
pp = pprint.PrettyPrinter()

log.setLevel(logging.INFO)
hdl.setLevel(logging.DEBUG)
log.addHandler(hdl)


class ResourcePlanner:
    def __init__(self, start_date, end_date, config):
        self.config = config

        self.api_key = config.api["api_key"]
        self.ezve_rounding = config.settings["ezve_rounding"]
        self.projects = config.projects
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
        log.info(mk_headline(sgn ="="))

    def get_working_hours(self, day):
        return self.bh.get_daily_working_hours()

    def load_data(self):
        pass

    def calculate_percents(self):
        for ws in self.ws:
            ws_obj = Workspace(ws)

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

    def output_ezve(self, outfile):
        days = sorted(self.days)
        lines = []
        for d in days:
            log.info(mk_headline(str(d)))
            day = self.days[d]

            project_seconds = DefaultDict(0.0)
            day_seconds = 0.0

            for e in day:
                if "pause" in e.tags:
                    continue

                project = self.projects.get_by_name(e.name)
                project_seconds[project.code] += e.duration.seconds
                day_seconds += e.duration.seconds

            prod_mapping_names = [m.code for m in self.productivity_mappings]
            mapped_seconds = DefaultDict(0.0)
            for s in project_seconds:
                prod_proj = self.projects.get_by_code(s)
                ps = project_seconds[s]
                if s in prod_mapping_names:
                    mappings = self.productivity_mappings[s].mappings
                    for m in mappings:
                        prod_proj = self.projects.get_by_code(m.productive_project)
                        mapped_seconds[prod_proj.ccenter] += ps * m.fraction
                else:
                    mapped_seconds[prod_proj.ccenter] += ps

            day_sum = 0
            for s in mapped_seconds:
                ps = mapped_seconds[s]
                ps_perc = ps / day_seconds * 100.
                ps_perc = int(self.ezve_rounding * round(float(ps_perc)/self.ezve_rounding))
                day_sum += ps_perc
                log.info(f"  {str(s):15s} {ps_perc:>8.0f}%")
                lines.append(f"{d.year}\t{d.month}\t{d.day}\t{s:05d}\t{ps_perc}")

            assert day_sum == 100, f"Day does not sum to 100: {day_sum}%"
            with open(outfile, "w") as f:
                for l in lines:
                    f.write(l+"\n")


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
    parser.add_argument("--ezve", "-z", type=str, default=False, help="Print out EZVE CSV")

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
        rp.output_ezve(args.ezve)
    else:
        rp.output_results()

if __name__ == "__main__":
    main()
