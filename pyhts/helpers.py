#!/usr/bin/env python
# -*- coding: utf-8 -*-
import collections
from django.utils.cache import get_conditional_response
from calendar import timegm


def format_dose(num, sig_digits=12):
    """
    Formats a numeric dose like 1.2e-9 into 1.2 nM
    """
    if not isinstance(num, str) and isinstance(num, collections.Iterable):
        return [format_dose(each_num) for each_num in num]

    if num is None:
        return 'N/A'

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
    return ('{0:.' + str(sig_digits) + 'g} {1}M').format(
        num/multiplier, _prefix[multiplier])


def not_modified(request, etag=None, last_modified=None):
    return get_conditional_response(
        request,
        etag=etag,
        last_modified=timegm(last_modified.utctimetuple())
    ) is not None


class AutoExtendList(list):
    def __setitem__(self, index, value):
        size = len(self)
        if index >= size:
            self.extend(None for _ in range(size, index + 1))

        super(AutoExtendList, self).__setitem__(index, value)
