import importlib.resources
import os


def get_thunor_test_file(filename):
    try:
        return importlib.resources.files('thunor').joinpath(filename)
    except OSError:
        # Provide a method to load from filesystem within Docker container
        fn = os.path.join('thunorcore/thunor', filename)
        if os.path.exists(fn) and os.path.isfile(fn):
            return fn

        raise
