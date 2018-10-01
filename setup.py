#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-

from setuptools import setup
import sys
if sys.version_info < (3,6):
    sys.exit('Sorry, Python < 3.6 is not supported')

setup(
    name = "TogglResourceSummary",
    version = "0.0.3",
    author = "Hendrik Wiese",
    author_email = "hendrik.wiese@dfki.de",
    description = ("A tool to process and sum up working times tracked on toggl.com"),
    license = "BSD",
    packages=['replan', 'resource_logging', 'resource_objects'],
    entry_points={
        'console_scripts': [
            'toggl_summary=replan.resource_planning:main'
        ]
    }
)
