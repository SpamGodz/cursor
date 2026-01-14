import unittest
import os
from src.config import Config

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.config_file = 'config/config.ini'
        self.config = Config(self.config_file)

    def test_get_database_config(self):
        db_config = self.config.get_database_config()
        self.assertEqual(db_config['type'], 'sqlite')
        self.assertEqual(db_config['path'], 'data/mydatabase.db')

    def test_get_data_source_config(self):
        data_source_config = self.config.get_data_source_config()
        self.assertEqual(data_source_config['type'], 'csv')
        self.assertEqual(data_source_config['path'], 'data/input.csv')

if __name__ == '__main__':
    unittest.main()
