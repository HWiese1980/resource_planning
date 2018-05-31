# -*- coding: utf-8 -*-

from .project import *
from datetime import datetime as dt, timedelta as tdelta, timezone as tz

__all__ = ["Workspace"]

class Workspace:
    working_hours = None

    def __init__(self, ws):
        self.ws = ws
        self.days = {}
        self.seconds = {}
        self.total_time = tdelta(0)
        self.project_durations_in_secs = {
            "Vacations": 0.0,
            "Sick": 0.0
        }
        self.projects = []
        self.native_projects = []
        self.load_projects()

    def load_projects(self):
        for project in self.ws.projects:
            p = Project(project, self)
            self.projects.append(p)
            self.native_projects.append(project)
