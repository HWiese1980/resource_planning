# -*- coding: utf-8 -*-

class BucketFullException(Exception):
    pass


class Bucket:
    def __init__(self, name, max_level = 100.0, flow_rate = 0.1, start_level = 0.0, other_bucket = None):
        self.name = name
        self.max = max_level
        self.level = start_level
        self.flow_rate = flow_rate
        self.other_bucket = other_bucket

    def connect_overflow(self, other_bucket):
        self.other_bucket = other_bucket

    def tick(self):
        if self.other_bucket is not None:
            self.other_bucket.tick()
            pressure = (self.level - self.other_bucket.level) * self.flow_rate
            if pressure > 0.0:
                self._flow_to_other(pressure)

    def _flow_to_other(self, amount):
        if self.level > 0.0:
            self.level -= min(self.level, amount)
            self.other_bucket.fill(min(self.level, amount))

    def fill(self, amount):
        self.level += amount
        if self.level > self.max:
            self.level = self.max
            if self.other_bucket is None:
                raise BucketFullException("Bucket {self.name} is full and there's no other bucket available")