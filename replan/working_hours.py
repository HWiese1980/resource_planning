from datetime import timedelta as tdelta, datetime as dt
from calendar import monthrange


class WorkingHours:
    def __init__(self, start, end, sum_of_breaks=1, worktimings=None, weekends=None, holidays=None):
        self.start = start
        self.end = end
        self.breaks = sum_of_breaks
        self.worktimings = worktimings or [9, 18]
        self.weekends = weekends or [6, 7]
        self.holidays = holidays or []

    def get_holidays(self, month=-1, year=-1):
        return self._get_days_by_type("Holidays", month, year)

    def get_vacations(self, month=-1, year=-1):
        by_type = self._get_days_by_type("Vacations", month, year)
        print(f"Vacation days {len(by_type)} in {month}/{year}")
        return by_type

    def get_sick_days(self, month=-1, year=-1):
        return self._get_days_by_type("Sick", month, year)

    def get_course_days(self, month=-1, year=-1):
        return self._get_days_by_type("Courses", month, year)

    def _get_days_by_type(self, day_type, month, year):
        return [d[0] for d in self.holidays if (d[0].month == month or month == -1)
                                                   and (d[0].year == year or year == -1)
                                                   and d[1] == day_type and d[0].weekday() + 1 not in self.weekends]

    def get_daily_working_hours(self):
        return self.worktimings[1] - self.worktimings[0]

    def get_daily_labor_hours(self):
        return self.worktimings[1] - self.worktimings[0] - self.breaks

    def get_all_work_days(self, month=-1, year=-1):
        if month != -1:
            if year == -1:
                year = self.start.year

            _, diff_days = monthrange(year, month)
            diff_s_dt = dt(self.start.year, month, 1)
            diff_e_dt = dt(self.end.year, month, diff_days)
            diff = (diff_e_dt + tdelta(days=1)) - diff_s_dt
        else:
            diff = (self.end + tdelta(days=1)) - self.start

        for i in range(diff.days):
            day = self.start + tdelta(i)
            wd = day.weekday() + 1
            if wd not in self.weekends:
                yield day

    def get_actual_work_days(self, month=-1, year = -1):
        for d in self.get_all_work_days(month, year):
            if d not in self.get_holidays(month, year):
                yield d

    def get_number_of_all_workdays(self, month=-1, year = -1):
        return len(list(self.get_all_work_days(month, year)))

    def get_number_of_actual_workdays(self, month=-1, year = -1):
        return len(list(self.get_actual_work_days(month, year)))

    def get_all_working_hours(self, month=-1, year = -1):
        days = self.get_number_of_all_workdays(month, year)
        worktiming = self.worktimings[1] - self.worktimings[0] - self.breaks
        return days * worktiming

    def get_actual_working_hours(self, month=-1, year = -1):
        days = self.get_number_of_actual_workdays(month, year)
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
                        for d in range(day[0], day[1] + 1):
                            date_time_object = dt(y, month, d)
                            holidays.append((date_time_object.date(), htype))
                    elif isinstance(day, int):
                        date_time_object = dt(y, month, day)
                        holidays.append((date_time_object.date(), htype))
    return holidays
