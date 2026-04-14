import importlib.resources


def get_thunor_test_file(filename):
    return importlib.resources.files('thunor').joinpath(filename)
