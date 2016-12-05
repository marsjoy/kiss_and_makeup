#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Utilities for working with strings

import re

from bs4 import BeautifulSoup


def remove_escape_characters(value):
    regex = re.compile(r'[\n\r\t]')
    return regex.sub('', value)


def remove_html_tags(value, parser):
    soup = BeautifulSoup(value, parser)
    return soup.text
