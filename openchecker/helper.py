import configparser

def read_config(filename, modulename=None):
    config = configparser.ConfigParser()
    if not config.read(filename):
        # configparser silently ignores a missing file; without this the next
        # line raises KeyError('section') and hides the real cause.
        raise FileNotFoundError(f"config file not found: {filename}")
    
    if modulename is not None:
        section = config[modulename]
        return dict(section)
    else:
        result = {}
        for section_name in config.sections():
            result[section_name] = dict(config[section_name])
        return result