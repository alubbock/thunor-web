import pkg_resources
import os
import thunor


def get_thunor_test_file(filename):
    try:
        return pkg_resources.resource_stream('thunor', filename)
    except OSError:
        # Provide a method to load from filesystem within Docker container
        fn = os.path.join('thunor/thunor', filename)
        if os.path.exists(fn) and os.path.isfile(fn):
            return open(fn, 'rb')

        raise
