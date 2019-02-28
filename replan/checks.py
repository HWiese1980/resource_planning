import datetime
import pytz

from datetime import timedelta as tdelta, datetime as dt

from replan.entry import Entry
from replan.logging import log
from .colour import Colour
from .functions import mk_headline


def check(msg):
    def wrap(func):
        def wrapper(*args, **kwargs):
            m = f"Check: {msg}"
            log.info(mk_headline(m, ">", indent = 5))
            okay = func(*args, **kwargs)
            if not okay:
                log.warn(mk_headline(f"{Colour.RED}{Colour.BOLD}Not OK!{Colour.END}"))
            else:
                log.info(mk_headline(f"{Colour.GREEN}{Colour.BOLD}OK!{Colour.END}"))
            log.info(mk_headline(sgn="<"))
            log.info("")
            return okay
        return wrapper
    return wrap


@check("Expected hours")
def check_for_expected_hours(days, get_working_hours_func):
    days_sorted = sorted(days.keys())
    total_hours = 0.0
    overunder_sum = 0.0
    for d in days_sorted:
        pause_hours = 0.0
        expected_day_hours = get_working_hours_func(d)
        actual_day_hours = 0.0
        special_day_type = None

        for e in days[d]: # type: Entry
            if "pause" in e.tags:
                pause_hours += e.duration.total_seconds()/3600.0
                continue
            if "off" in e.tags:
                special_day_type = e.name

            entry_time = e.duration
            entry_hours = entry_time.total_seconds()/3600.0
            actual_day_hours += entry_hours

        total_hours += actual_day_hours
        overunder = actual_day_hours - expected_day_hours
        if overunder < 0.0:
            p = pause_hours
            overunder += p
            pause_hours -= p

        overunder_sum += overunder

        c = Colour.RED if overunder < 0.0 else Colour.BLUE
        overunder_str = f"{Colour.BOLD}{c}{overunder:>+5.2f}{Colour.END}"

        c = Colour.RED if pause_hours < 1.0 else Colour.BLUE
        pause_str = f"{Colour.BOLD}{c}{pause_hours:>5.2f}{Colour.END}"

        result = [dt.strftime(d, '%d.%m.%Y')]

        if special_day_type is None:
            result.append(f"{actual_day_hours:>5.2f}h")
            result.append(f"breaks: {pause_str}h => +/- {overunder_str}h")
        else:
            if special_day_type == "Vacations" or special_day_type == "Holidays":
                result.append(f"{Colour.GREEN}{Colour.BOLD}is a day off{Colour.END}")
            elif special_day_type == "Sick":
                result.append(f"{Colour.YELLOW}{Colour.BOLD}Hope you got well!{Colour.END}")


        if pause_hours < 1.0 and not special_day_type:
            result.append(f"{Colour.BOLD}You need sufficient breaks!{Colour.END}")

        log.info("; ".join(result))

    log.info(mk_headline("Sum of daily hours"))
    log.info(f" Sum: {total_hours:>6.1f}h")
    log.info(f" +/- {overunder_sum:>6.1f}h")

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
        if d >= datetime.datetime.today().date():
            break
        if d not in days:
            log.warn(f"Workday {dt.strftime(d, '%d.%m.%Y')} has no entry")
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