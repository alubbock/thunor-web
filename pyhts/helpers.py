#!/usr/bin/env python
# -*- coding: utf-8 -*-
import collections


def format_dose(num, decimals=0):
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
    return '{0} {1}M'.format(num/multiplier,
                                                 _prefix[multiplier])
