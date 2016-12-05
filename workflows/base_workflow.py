#!/usr/bin/env python
# -*- coding: utf-8 -*-
from abc import abstractmethod
from abc import ABCMeta
import configparser


class BaseWorkflow:
    __metaclass__ = ABCMeta

    def __init__(self):
        self.data_path = '/Users/mars_williams/kiss_and_makeup/data'
        self.config = configparser.ConfigParser()
        self.config.read('/Users/mars_williams/kiss_and_makeup/config/makeup.conf')

    @abstractmethod
    def process(self):
        pass
