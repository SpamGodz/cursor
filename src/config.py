import configparser

class Config:
    def __init__(self, config_file):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)

    def get_database_config(self):
        return dict(self.config['database'])

    def get_data_source_config(self):
        return dict(self.config['data_source'])
