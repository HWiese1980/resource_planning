from datetime import timedelta as tdelta, datetime as dt


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
        for i in range(diff.days):
            day = self.start + tdelta(i)
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