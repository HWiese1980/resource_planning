# -*- coding: utf-8 -*-

from .time_entries import *
import logging

__all__ = ["Project"]

log = logging.getLogger(__name__)

class Project:
    def __init__(self, project, workspace = None):
        self.name = project.name
        self.times = project.time_entries.list()
        self.time_entries = []
        self.workspace = workspace

    def load_times(self):
        for te in self.times:
            if not hasattr(te, "stop"):
                log.warn(f"Entry {te} still running")
                continue

            te_obj = TimeEntry(te, self)
            self.time_entries.append(te_obj)
