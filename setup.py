#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name = "TogglResourceSummary",
    version = "0.0.1",
    author = "Hendrik Wiese",
    author_email = "hendrik.wiese@dfki.de",
    description = ("A tool to process and sum up working times tracked on toggl.com"),
    license = "BSD",
    packages=['replan', 'resource_objects', 'resource_logging'],
    entry_points={
        'console_scripts': [
            'toggl_summary=replan.resource_planning:main'
        ]
    }
)
