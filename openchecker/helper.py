import configparser
import os

# Path of the repository root (the parent of the `openchecker` package). Every
# module in the package loads its configuration with
# read_config('config/config.ini', ...), which used to resolve against the
# current working directory only: starting the service (or importing a module)
# from anywhere else silently read no file at all and then failed deep inside
# the lookup with a misleading `KeyError: '<section>'`.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_config_path(filename):
    """Return an existing path for `filename`, preferring the current directory.

    An absolute path, or a relative path that exists from the current working
    directory, is returned untouched. Otherwise the path is re-anchored on the
    repository root; the original value is returned when neither exists, so the
    caller still sees an error that names the path it asked for.
    """
    if os.path.isabs(filename) or os.path.exists(filename):
        return filename

    anchored = os.path.join(PROJECT_ROOT, filename)
    if os.path.exists(anchored):
        return anchored
    return filename


def read_config(filename, modulename=None):
    path = resolve_config_path(filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"configuration file not found: {path}")

    config = configparser.ConfigParser()
    config.read(path)

    if modulename is not None:
        section = config[modulename]
        return dict(section)
    else:
        result = {}
        for section_name in config.sections():
            result[section_name] = dict(config[section_name])
        return result
