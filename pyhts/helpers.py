#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.utils.cache import get_conditional_response
from calendar import timegm


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
