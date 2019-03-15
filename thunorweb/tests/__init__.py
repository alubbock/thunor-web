import pkg_resources
import os


def get_thunor_test_file(filename):
    try:
        return pkg_resources.resource_stream('thunor', filename)
    except OSError:
        # Provide a method to load from filesystem within Docker container
        if 'THUNORHOME' in os.environ:
            fn = os.path.join(os.environ['THUNORHOME'],
                              'thunor/thunor',
                              filename)
            if os.path.exists(fn) and os.path.isfile(fn):
                return open(fn, 'rb')

        raise
