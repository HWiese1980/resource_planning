import datetime
import pytz

from datetime import timedelta as tdelta, datetime as dt

from replan.logging import log
from .colour import Colour
from .functions import mk_headline


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


@check("Expected hours")
def check_for_expected_hours(days, get_working_hours_func):
    days_sorted = sorted(days.keys())
    total = 0.0
    overunder_sum = 0.0
    for d in days_sorted:
        dur = tdelta(hours = 0)
        dur_h = 0.0
        for e in days[d]:
            dur += e.duration
            dur_h += e.duration.total_seconds()/3600.0
            total += e.duration.total_seconds()
        overunder = dur_h - get_working_hours_func(d)
        overunder_sum += overunder

        c = Colour.RED if overunder < 0.0 else Colour.BLUE
        overunder_str = f"{Colour.BOLD}{c}{overunder:>4.1f}{Colour.END}"

        log.info(f" {dt.strftime(d, '%d.%m.%Y')}; duration: {dur_h:>5.2f} hours, => +/- {overunder_str} hours")

    log.info(mk_headline("Sum of daily hours"))
    log.info(f" Sum: {total/3600.:>8.1f} hours")
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

            f_end_str = dt.strftime(first.end.astimezone(pytz.timezone("Europe/Berlin")), "%H:%M:%S")
            s_start_str = dt.strftime(second.start.astimezone(pytz.timezone("Europe/Berlin")), "%H:%M:%S")

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
                log.warn(f"    [{stat}] {abs(diff.total_seconds()):>8.0f}s; {first.name:10s} and {second.name:10s} on {first.start.date()}: {f_end_str} -> {s_start_str}")

    return okay


@check("Completeness")
def check_for_completeness(days, actual_work_days):
    okay = True
    for d in actual_work_days:
        if d.date() >= datetime.datetime.today().date():
            break
        if d.date() not in days:
            log.warn(f"Workday {dt.strftime(d.date(), '%d.%m.%Y')} has no entry")
            log.info(f"Entries:{', '.join([str(x) for x in days.keys()])} ")
            okay = False
    return okay


@check("Weekends")
def check_weekends(days, weekends):
    okay = True
    for d in days:
        at_work_entries = [e.name not in ["Vacations", "Sick"] for e in days[d]]
        if d.weekday()+1 in weekends and any(at_work_entries):
            log.warn(f"Seems like {dt.strftime(d, '%d.%m.%Y')} is set as a weekend day. Were you really working then?")
            log.info(f"Entry: {days[d]}")
            okay = False
    return okay


gap_threshold_seconds = 60