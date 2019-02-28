#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-
import sys

import datetime
import icu
import markdown2
import os
import pandas
import pytz
import pytz.reference
import pytz.tzinfo
import random
import yaml
from calendar import monthrange
from datetime import datetime as dt, timedelta as tdelta
from toggl.api import Api
from toggl.workspace import Workspace

from replan.checks import check_for_expected_hours, check_for_gaps_and_overlaps, check_for_completeness, check_weekends
from replan.collections import StrictList, StrictDict, DefaultDict
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


def _try_parse(dt, p):
    tf = None
    try:
        tf = p.parse(dt)
    except:
        pass
    return tf


def parse(dt):
    try:
        dt = float(dt)
    except:
        pass

    if isinstance(dt, str):
        ts = parse_to_ts(dt)
    elif isinstance(dt, float):
        ts = dt * 3600.
    else:
        raise ValueError("dt must be str or float")

    d = datetime.datetime.fromtimestamp(ts, pytz.timezone("Europe/Berlin"))
    return d


def parse_to_ts(dt):
    df = icu.SimpleDateFormat('dd.MM.yyyy, HH:mm', icu.Locale('de_DE'))
    ts = _try_parse(dt, df)
    return ts

def parse_time(t):
    return datetime.datetime.strptime(t,"%H:%M")

pp = pprint.PrettyPrinter()

log.setLevel(logging.INFO)
hdl.setLevel(logging.DEBUG)
log.addHandler(hdl)


class ResourcePlanner:
    def __init__(self, start_date, end_date, config):
        self.special_projects = ["Vacations", "Sick", "Courses"]
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

        self.bh = WorkingHours(self.start, self.end, weekends=self.weekends, worktimings=self.worktimings,
                               holidays=self.holidays)
        # Workspace.working_hours = self.bh
        log.info(mk_headline(sgn="="))
        log.info(mk_headline("Resource Planner", "#"))
        log.info(mk_headline(sgn="="))
        log.info("")
        log.info(" Expected working hours in time span %s to %s: %s (%s days)"
                 % (dt.strftime(self.start, "%d.%m.%Y"),
                    dt.strftime(self.end, "%d.%m.%Y"),
                    self.bh.get_actual_working_hours(), self.bh.get_number_of_actual_workdays()))
        log.info(mk_headline(sgn="="))

    def get_working_hours(self, day):
        return self.bh.get_daily_working_hours()

    def get_labor_hours(self, day):
        return self.bh.get_daily_labor_hours()

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
                "Courses": 0.0,
                "Sick": 0.0
            }

            for project in ws_obj.native_projects:
                p_name = project.name
                times = project.time_entries.list()

                for i in times:
                    if not hasattr(i, "stop"):
                        log.warn("Entry %s seems to still be running" % i.description)
                        continue
                    start = i.start.replace(tzinfo=pytz.timezone("UTC"))
                    end = i.stop.replace(tzinfo=pytz.timezone("UTC"))

                    if start.date() < self.start or end.date() > self.end:
                        continue

                    dur = end - start

                    if dur.total_seconds() / 3600. > 11:
                        log.warn("Warning: the entry seems to be too long:")
                        log.warn(f"{p_name} from {start} to {end}; duration {dur}")

                    if start.date() not in self.days:
                        self.days[start.date()] = StrictList(Entry)

                    if p_name not in self.project_seconds:
                        self.project_seconds[p_name] = 0.0

                    e = None

                    tags = list(set([t.lower() for t in i.tags])) if hasattr(i, "tags") else []

                    e = Entry(p_name, start, end, dur, tags)
                    add_dur = not (p_name == "Holidays" or (hasattr(i, "tags") and "Pause" in i.tags))
                    if add_dur:
                        self.project_seconds[p_name] += dur.total_seconds()

                    self.days[start.date()].append(e)

    def checks(self):
        log.info(f"Performing checks on {', '.join([str(s) for s in self.days.keys()])}")
        check_for_expected_hours(self.days, self.get_labor_hours)
        check_for_gaps_and_overlaps(self.days)
        check_for_completeness(self.days, self.bh.get_actual_work_days())
        check_weekends(self.days, self.weekends)

    def apply_holidays(self):
        for h in self.bh.holidays:
            if h[1] == "Holidays":
                continue

            d = h[0]

            if not (self.start <= d <= self.end):
                continue

            weekday = d.weekday()+1
            if weekday in self.bh.weekends:
                log.warning(f"Skipping weekend day {d}")
                continue

            if d not in self.days:
                log.info(f"Adding new day entry list for day {d}")
                self.days[d] = StrictList(Entry)

            dwh = self.bh.get_daily_working_hours() - self.bh.breaks
            dwstart = self.bh.worktimings[0]
            dtime = add_hours(d, dwstart)
            dtime = self.get_timezone().localize(dtime)

            self.project_seconds[h[1]] += tdelta(hours=dwh).total_seconds()
            self.total_time += tdelta(hours=dwh)
            entry = Entry(h[1], dtime, add_hours(dtime, dwh), tdelta(hours=dwh), ["off"])
            pause_entry = Entry(h[1], entry.end, add_hours(entry.end, self.bh.breaks), tdelta(hours = self.bh.breaks), ["pause", "off"])
            log.info(f"Adding entry {entry} to {d}")
            self.days[d].append(entry)
            # log.info(f"Adding pause entry {pause_entry} to {d}")
            # self.days[d].append(pause_entry)

    def output_results(self):
        log.info(mk_headline(f"Resulting resource distribution", "="))
        log.info(mk_headline(sgn="-"))

        project_seconds, total_seconds = self.calc_project_and_total_seconds()

        all_hours = self.bh.get_actual_working_hours()
        log.info(f"Total hours in month {self.start.month}: {all_hours}")
        print(mk_headline(sgn="-"))
        perc_sum = 0.0
        for p in project_seconds:
            perc = round(project_seconds[p] / total_seconds * 100.)
            perc = round(perc / 5) * 5
            perc_sum += perc
            if perc > 0.0:
                print(f"==> Project {p}: {perc}%")
        print(mk_headline(sgn="-"))
        print(f"Sum: {perc_sum}%")
        print(mk_headline(sgn="="))

    def calc_project_and_total_seconds(self):
        all_hours = self.bh.get_actual_working_hours(month=self.start.month)
        project_seconds = DefaultDict(0.0)
        total_seconds = all_hours * 3600
        postponed_seconds = 0.0
        for d in self.days:
            day = self.days[d]
            for e in day:
                if "pause" in e.tags:
                    continue
                if "distribute" in e.tags or "overhead" in e.tags:
                    # postponed_entries[d].append(e)
                    postponed_seconds += e.duration.seconds
                    continue
                if "off" in e.tags:
                    continue

                project = self.projects.get_by_name(e.name)
                project_seconds[project.name] += e.duration.seconds

        sick_days = self.bh.get_sick_days(month=self.start.month, year=self.start.year)
        sick_seconds = self.bh.get_daily_working_hours() * 3600. * len(sick_days)
        postponed_seconds += sick_seconds

        for p in project_seconds:
            project_seconds[p] += postponed_seconds / len(project_seconds)

        distribute_seconds = 0.0
        lt5p_projects = [p for p in project_seconds if
                         project_seconds[p] / total_seconds > 0.0 and project_seconds[
                             p] / total_seconds < 0.05]

        for p in lt5p_projects:
            distribute_seconds += project_seconds[p]
            del project_seconds[p]

        if any(lt5p_projects):
            d_time = distribute_seconds / len(project_seconds)
            for p in project_seconds:
                project_seconds[p] += d_time

        vac_days = self.bh.get_vacations(month=self.start.month, year = self.start.year)
        course_days = self.bh.get_course_days(month=self.start.month)
        project_seconds["Vacations"] = self.bh.get_daily_labor_hours() * 3600. * len(vac_days)
        project_seconds["Courses"] = self.bh.get_daily_labor_hours() * 3600. * len(course_days)
        return project_seconds, total_seconds

    def output_results_old(self):
        log.info(mk_headline(f"Resulting Resource Distribution", "="))
        log.info(mk_headline(sgn="-"))
        perc_sum = 0.0

        percents = {}
        hours = {}

        for p_name in self.project_seconds:
            phours = self.project_seconds[p_name] / 3600.
            percent = phours / self.bh.get_actual_working_hours(self.start.month) * 100.
            perc_sum += percent

            if p_name not in self.special_projects:
                self.total_time += tdelta(hours=phours)

            percents[p_name] = percent
            hours[p_name] = phours

        bigger_5p = [p for p in percents if percents[p] >= 5.0 and p not in self.special_projects]
        smallr_5p = [p for p in percents if percents[p] < 5.0 and p not in self.special_projects]

        sum_bigger = sum([percents[p] for p in bigger_5p])

        for p_name in smallr_5p:
            smallr_perc = percents[p_name]
            smallr_hours = hours[p_name]
            log.info(
                f"Rebooking {smallr_perc:>8.1f}% ({smallr_hours:>8.1f} hours) of project {p_name} to the bigger projects")
            for bigger_p_name in bigger_5p:
                factor = 1. - (percents[bigger_p_name] / sum_bigger)
                hours_plus = smallr_hours * factor
                percs_plus = smallr_perc * factor
                hours[bigger_p_name] += hours_plus
                percents[bigger_p_name] += percs_plus
                log.info(f"  {factor*100.:>8.1f}% of {smallr_hours:>8.1f} hours of {p_name} go to {bigger_p_name}")

        for p_name in bigger_5p:
            log.info(f"    {p_name:<20s}: {percents[p_name]:>3.0f}% (hours: {hours[p_name]:>10.1f})")

        log.info(mk_headline("Total hours in the given period", "-"))
        total_hours = self.total_time.total_seconds() / 3600.
        log.info(f" {total_hours:>3.1f} hours => {total_hours/self.bh.get_actual_working_hours() * 100.:>3.0f}%")
        log.info(mk_headline("Smaller projects", sgn="-"))

        for p_name in smallr_5p:
            log.info(f"    {p_name:<20s}: {percents[p_name]:>3.0f}% (hours: {hours[p_name]:>10.1f})")

        log.info(mk_headline(sgn="="))

    def output_planning(self):
        from string import Template
        import locale
        locale.setlocale(locale.LC_ALL, '')
        mtemp_lines = self.config.templates["mail"]
        mtemp = "\n".join(mtemp_lines)
        temp = Template(mtemp)
        dtemp = Template(self.config.templates["project_line"])
        stemp = Template(self.config.templates["sum_line"])

        pdate = self.start
        _, mdays = monthrange(pdate.year, pdate.month)
        ndate = self.start + tdelta(days=mdays)

        log.info(f"Planning for {pdate} and {ndate}")

        pmonth = dt.strftime(pdate, "%B")
        nmonth = dt.strftime(ndate, "%B")
        pyear = dt.strftime(pdate, "%Y")
        nyear = dt.strftime(ndate, "%Y")
        pyears = dt.strftime(pdate, "%y")
        nyears = dt.strftime(ndate, "%y")

        if pdate.year == ndate.year:
            pyear = ""

        pvacation_days_no = len(self.bh.get_vacations(pdate.month, pdate.year))
        nvacation_days_no = len(self.bh.get_vacations(ndate.month, ndate.year))
        pcourse_days_no = len(self.bh.get_course_days(pdate.month, pdate.year))
        ncourse_days_no = len(self.bh.get_course_days(ndate.month, ndate.year))
        psick_days_no = len(self.bh.get_sick_days(pdate.month, pdate.year))
        nsick_days_no = len(self.bh.get_sick_days(ndate.month, ndate.year))

        pall_days_no = self.bh.get_number_of_actual_workdays(pdate.month, pdate.year)
        nall_days_no = self.bh.get_number_of_actual_workdays(ndate.month, ndate.year)

        pvacation_perc = pvacation_days_no / pall_days_no
        nvacation_perc = nvacation_days_no / nall_days_no
        psick_perc = psick_days_no / pall_days_no
        pcourses_perc = pcourse_days_no / pall_days_no
        ncourses_perc = ncourse_days_no / nall_days_no

        project_seconds, total_seconds = self.calc_project_and_total_seconds()

        pdata = {}
        ndata = {}

        included_prj_count = len(project_seconds)
        for p in project_seconds:
            s = project_seconds[p]
            perc = s / total_seconds * 100.
            pdata[p] = {
                "project": p,
                "perc": (round(perc / 5) * 5)
            }

        pdata["Vacations"] = {
            "project": "Urlaub",
            "perc": (round((pvacation_perc * 100) / 5) * 5)
        }

        pdata["Courses"] = {
            "project": "Seminare/Weiterbildung",
            "perc": (round((pcourses_perc * 100) / 5) * 5)
        }

        # pdata["Sick"] = {
        #     "project": "Krank",
        #     "perc": (round((psick_perc * 100) / 5) * 5)
        # }
        #
        ndata["Courses"] = {
            "project": "Seminare/Weiterbildung",
            "perc": (round((ncourses_perc * 100) / 5) * 5)
        }

        ndata["Vacations"] = {
            "project": "Urlaub",
            "perc": (round((nvacation_perc * 100) / 5) * 5)
        }

        def perc_sum(data):
            return sum([data[p]["perc"] for p in data])

        non_special_pdata = [p for p in pdata if p not in self.special_projects]
        if len(non_special_pdata) > 0:
            while (100 - perc_sum(pdata) > 0):
                diff = int(100 - perc_sum(pdata))
                if diff > included_prj_count:
                    diff = diff // included_prj_count
                    for p in pdata:
                        if p not in self.special_projects:
                            pdata[p]["perc"] += diff
                else:
                    keys = list(pdata.keys())
                    for i in range(diff):
                        key = random.choice(keys)
                        keys.remove(key)
                        pdata[key]["perc"] += 1

        for p in list(pdata.keys()):
            if pdata[p]["perc"] < 5:
                del pdata[p]

        for p in list(ndata.keys()):
            if ndata[p]["perc"] < 5:
                del ndata[p]

        for p in pdata:
            pdata[p]["percentage"] = "%3d" % pdata[p]["perc"]

        for p in ndata:
            ndata[p]["percentage"] = "%3d" % ndata[p]["perc"]

        pdata_str = [dtemp.substitute(pdata[p]) for p in pdata]
        ndata_str = [dtemp.substitute(ndata[p]) for p in ndata]

        psum_str = stemp.substitute({
            "percsum": perc_sum(pdata)
        })

        nsum = perc_sum(ndata)
        rest = 100 - nsum
        d = {
            'pmonth': pmonth,
            'pyear': pyear,
            'nmonth': nmonth,
            'nyear': nyear,
            'pyears': pyears,
            'nyears': nyears,
            'pdata': "\n".join(pdata_str),
            'psum': psum_str,
            'ndata': "\n".join(ndata_str),
            'rest': "%3d" % rest
        }
        result = temp.substitute(d)
        log.info(result)

        md_result = markdown2.markdown(result).replace("\n", "")

        from subprocess import Popen
        recipients = self.config.settings["mail_summary_recipients"]
        recipients = ",".join(recipients)
        p = Popen(["thunderbird", "-compose",
                   f"to='{recipients}',subject='Ressourcenplanung {pmonth} {pyear} und {nmonth} {nyear}',body='{md_result}'"])
        log.info(f"Thunderbird returned: {p.returncode}")

    def days_off(self, *off_type):
        off_type = list(map(str.lower, off_type))

        for d, t in self.holidays:
            if t.lower() in off_type:
                yield d

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
                        mapped_seconds[(prod_proj.code, prod_proj.ccenter)] += ps * m.fraction
                else:
                    mapped_seconds[(prod_proj.code, prod_proj.ccenter)] += ps

            day_sum = 0
            codes = list(mapped_seconds.keys())
            percents = [0] * len(codes)
            percents = dict(zip(codes, percents))

            def ezve_round(v):
                return int(self.ezve_rounding * round(float(v * 100.) / self.ezve_rounding)) / 100.

            for ms in mapped_seconds:
                ps = mapped_seconds[ms]
                percents[ms] = ps / day_seconds
                percents[ms] = ezve_round(percents[ms])

            remains = DefaultDict(0.0)
            for pc in percents:
                c, cc = pc
                prj = self.projects.get_by_code(c)
                remains[pc] = min(1.0, prj.max) - percents[pc]

            underfull_projects = dict([(i, remains[i]) for i in remains if remains[i] > 0.0])
            overfull_projects = dict([(i, remains[i]) for i in remains if remains[i] < 0.0])
            for ofp in overfull_projects:
                c, cc = ofp
                prj = self.projects.get_by_code(c)
                percents[ofp] = prj.max
                if not any(underfull_projects):
                    log.warning(
                        f"There are no unfilled projects on this day that could take the remaining {remains[ofp]*-100}% of {prj.name}"
                    )
                    log.warning(
                        f"Please make sure that at least one other entry is given in Toggl that can take the overflow"
                    )
                    continue

                while remains[ofp] > 0:
                    r = remains[ofp]
                    subt = r / len(underfull_projects)
                    subt = ezve_round(subt)
                    for ufp in underfull_projects:
                        if subt > remains[ufp]:
                            subt = remains[ufp]

                        r -= subt
                        remains[ufp] -= subt
                        percents[ufp] += subt

            for c, cc in percents:
                prj = self.projects.get_by_code(c)
                if prj.ezve_ignore:
                    continue

                p = percents[(c, cc)]
                if p * 100 <= 1e-2:
                    log.info(f"{p:>8.3f}% {c} {cc} skipped")
                    continue

                day_sum += int(p * 100)
                # log.info(f"  {c:15s} -> CC: {str(cc):15s} {p*100:>8.0f}%")
                if outfile is not None:
                    lines.append(f"{d.year}\t{d.month}\t{d.day}\t{cc:05d}\t{p*100}")
                else:
                    if not any(lines):
                        lines.append("Date\t\tProject\t\tPercent")
                        lines.append(mk_headline())

                    lines.append(f"{dt.strftime(d, '%d.%m.%Y')}\t{c:20}\t{cc:8}\t{p*100:5.0f}%")

            if day_sum < 100:
                log.warning(f"This day is only filled to {day_sum}%!")
            elif day_sum > 100:
                log.error(f"This day is overfilled to {day_sum}%!")

            if outfile is None:
                lines.append(mk_headline())

        if outfile is not None:
            with open(outfile, "w") as f:
                for l in lines:
                    f.write(l + "\n")
        else:
            for l in lines:
                log.info(l.strip())

    def add_from_csv(self, csv_file):
        pd = pandas.read_csv(csv_file, index_col=False)
        for i, row in pd.iterrows():
            print(row)
            wid = row["WID"]
            ws_ids = [w.id for w in self.ws]
            if wid not in ws_ids:
                raise Exception(f"WS ID {wid} not in Workspaces ({ws_ids})")
            else:
                assert isinstance(wid, int)
                ws = self.ws.get(wid)

            inf = self.get_timezone()

            start = parse(f"{row['Date']}, {row['From']}+2:00")

            try:
                to = parse(f"{row['To']}").time()
            except ValueError:
                to = None

            try:
                duration = parse_time(row['Duration'])
            except ValueError:
                duration = None

            if duration is not None:
                delta = tdelta(hours = duration.hour, minutes = duration.minute, seconds = duration.second)
            else:
                shours = start.time().hour
                sminut = start.time().minute
                ssecon = start.time().second
                ehours = to.hour
                eminut = to.minute
                esecon = to.second
                delta = tdelta(hours=ehours - shours, minutes=eminut - sminut, seconds=esecon - ssecon)

            end = start + delta

            pname = row["Project"]

            # print(pids)

            log.info(
                f"Adding entry on {start.date().strftime('%d.%m.%Y')} from {start.time()} to {end.time()} (Duration: {duration}")

            project = pname
            projects_by_name = dict([(p.name, p) for p in ws.projects if p.name == project])
            project_obj = projects_by_name[project]

            e_pid = project_obj.id
            e_start = start.isoformat()

            e_dur = delta.total_seconds()
            e_desc = row["Description"]
            e_tags = row["Tags"].split("|")

            log.info(f"Project: {project}")
            log.info(f"Tags   : {', '.join(e_tags)}")
            log.info(f"Description: {e_desc}")
            log.info(f"Creating entry...")

            self.api.time_entries.create(time_entry={
                "wid": wid,
                "pid": e_pid,
                "billable": False,
                "start": e_start,
                "duration": e_dur,
                "description": e_desc,
                "tags": e_tags,
                "created_with": "resource_planner"
            }
            )

    def get_timezone(self):
        return pytz.timezone("Europe/Berlin")

    def _find_ws_from_project_name(self, project):
        """
        Returns a workspace for a given project name

        :param project: Name of the project
        :type project: str
        :return: Workspace object
        :rtype: toggl.workspace.Workspace
        """
        for ws in self.ws:
            print(ws.projects)
            if any([p for p in ws.projects if p.name == project]):
                return ws

    def add(self, project, desc, tags, date_start, date_end):
        ws = self._find_ws_from_project_name(project)
        if ws is None:
            raise ValueError(f"No Workspace for {project} found")

        projects = dict([(p.name, p) for p in ws.projects if p.name == project])  # type: Dict[Project]
        project_object = projects[project]  # type: Project
        wid = ws.id
        pid = project_object.id

        start = date_start.isoformat()

        shours = date_start.time().hour
        sminut = date_start.time().minute
        ssecon = date_start.time().second
        ehours = date_end.time().hour
        eminut = date_end.time().minute
        esecon = date_end.time().second

        delta = tdelta(hours=ehours - shours, minutes=eminut - sminut, seconds=esecon - ssecon)
        duration = delta.total_seconds()

        e_tags = [t.strip() for t in tags.split(",")]

        print(f"Adding Entry: {wid} {pid} {start} {duration} {desc} {e_tags}")
        self.api.time_entries.create(time_entry={
            "wid": wid,
            "pid": pid,
            "billable": False,
            "start": start,
            "duration": duration,
            "description": desc,
            "tags": e_tags,
            "created_with": "resource_planner"
        })


class SubCommandSplitter:
    def __init__(self, rp):
        self.rp = rp  # type: ResourcePlanner

    def summary(self):
        self.rp.output_results()

    def ezve(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--to-file", "-t", nargs="?", default=None, type=str, help="Where to output the EZVE data")
        args, classlist = parser.parse_known_args(sys.argv[2:])
        self.rp.output_ezve(args.to_file)

    def mail(self):
        self.rp.output_planning()

    def imp(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--csv-file", type=str, help="What CSV file to parse")
        args, classlist = parser.parse_known_args()
        self.rp.add_from_csv(args.csv_file)

    def add(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("project", type=str)
        parser.add_argument("description", type=str)
        parser.add_argument("tags", type=str)
        parser.add_argument("date", type=str)
        parser.add_argument("start_time", type=str)
        parser.add_argument("end_time", type=str)

        args, classlist = parser.parse_known_args(sys.argv[2:])

        start_str = f"{args.date} {args.start_time}"
        end_str = f"{args.date} {args.end_time}"

        date_start = parse(start_str)
        date_end = parse(end_str)

        self.rp.add(args.project, args.description, args.tags, date_start, date_end)

    def add_default_break(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("date", type=str)

        args, classlist = parser.parse_known_args(sys.argv[2:])

        start_str = f"{args.date} 12:00:00"
        end_str = f"{args.date} 13:00:00"

        date_start = parse(start_str)
        date_end = parse(end_str)

        self.rp.add("Sonstiges", "Mittagspause", "pause", date_start, date_end)


def main():
    curr_month = int(datetime.datetime.now().strftime("%m"))
    curr_year = int(datetime.datetime.now().strftime("%Y"))

    parser = argparse.ArgumentParser()
    parser.add_argument("command", type=str, help="What to show")
    parser.add_argument("--month", "-m", nargs="?", default=-1, type=int, help="Month of this year to be evaluated")
    parser.add_argument("--year", "-y", nargs="?", default=-1, type=int, help="Year of the given month to be evaluated")
    parser.add_argument("--start", "-s", type=str, default=False, help="Start date of period to be evaluated")
    parser.add_argument("--end", "-e", type=str, default=False, help="End date of period to be evaluated")
    parser.add_argument("--config", "-c", default=config_file, help="File containing configuration")
    parser.add_argument("--no-checks", "-n", action="store_true", help="Skip all checks")

    # parser.add_argument("--ezve-csv", "-zc", type=str, default=False, help="Write EZVE CSV file")
    # parser.add_argument("--ezve", "-z", action="store_true", default=False, help="Print out EZVE data to console")
    # parser.add_argument("--add-from-csv", "-a", default=False, help="Add entries from CSV")
    # parser.add_argument("--mail", "-m", action="store_true", default=False, help="Print out resource planning mail")
    args, classlist = parser.parse_known_args()

    if args.year == -1 and args.month > curr_month:
        args.year = curr_year - 1
    elif args.year == -1:
        args.year = curr_year

    if args.month == -1:
        args.month = curr_month - 1
        if args.month == 0:
            args.month = 12
        elif args.month < 0:
            args.month %= 12

    if args.start and args.end:
        start = parse(args.start)
        end = parse(args.end)
    else:
        (first, last) = monthrange(args.year, args.month)
        start = datetime.date(args.year, args.month, 1)
        end = datetime.date(args.year, args.month, last)

    with open(args.config, "r") as f:
        config = yaml.load(f)

    rp = ResourcePlanner(start, end, config=config)

    # if args.add_from_csv:
    #     rp.add_from_csv(args.add_from_csv)
    #     return

    rp.calculate_percents()
    rp.apply_holidays()
    if not args.no_checks:
        rp.checks()

    s = SubCommandSplitter(rp)
    if not hasattr(s, args.command):
        print(f"Unrecognized command {args.command}")
        parser.print_help()
        exit(1)
    getattr(s, args.command)()

    # if args.mail:
    #     rp.output_planning()
    # elif args.ezve:
    #     rp.output_ezve(None)
    # elif args.ezve_csv:
    #     rp.output_ezve(args.ezve_csv)
    # else:
    #     rp.output_results()
