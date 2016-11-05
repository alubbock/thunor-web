#!/usr/bin/env python
# -*- coding: utf-8 -*-
import collections
import re


def format_dose(num):
    """
    Formats a numeric dose like 1.2e-9 into 1.2 nM
    """
    if not isinstance(num, str) and isinstance(num, collections.Iterable):
        return [format_dose(each_num) for each_num in num]

    num = float(num)

    _prefix = {1e-12: 'p',
               1e-9: 'n',
               1e-6: 'μ',
               1e-3: 'm',
               1: ''}
    multiplier = 1
    for i in sorted(_prefix.keys()):
        if num >= i:
            multiplier = i
    return '{0} {1}M'.format(num/multiplier, _prefix[multiplier])


def guess_timepoint_hrs(string):
    """
    Tries to extract a numeric time point from a string
    """
    tp_guess = re.search(r'(?i)([0-9]+)[-_\s]*(h\W|hr|hour)', string)
    return int(tp_guess.group(1)) if tp_guess else None
