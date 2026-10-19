import configparser

def read_config(filename, modulename=None):
    config = configparser.ConfigParser()
    config.read(filename)
    
    if modulename is not None:
        if not config.has_section(modulename):
            raise KeyError(
                f"section [{modulename}] is not in {filename}; available sections: {config.sections()}"
            )
        section = config[modulename]
        return dict(section)
    else:
        result = {}
        for section_name in config.sections():
            result[section_name] = dict(config[section_name])
        return result