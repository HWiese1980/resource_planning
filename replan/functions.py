from datetime import timedelta as tdelta
import datetime


def add_days(date, number):
    return date + tdelta(days = number)


def add_hours(date, number):
    """

    :param date:
    :type date: datetime.date or datetime.datetime
    :param number:
    :return:
    """
    if not hasattr(date, "time"):
        date = datetime.datetime.combine(date, datetime.datetime.min.time())
    return date + tdelta(hours = number)


def add_minutes(date, number):
    return date + tdelta(minutes = number)


def add_seconds(date, number):
    return date + tdelta(seconds = number)


def format_td(td):
    s = td.seconds
    dh = s // 3600
    s -= dh*3600
    dm = s // 60
    s -= dm*60
    return f"{dh:02d}:{dm:02d}"


def mk_headline(msg = "", sgn = "-", l = 90, indent = 3):
    h = [sgn]*l
    if msg != "":
        h[indent:indent+len(msg)+2] = list(f" {msg} ")
    h = "".join(h)
    return h