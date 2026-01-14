import unittest
from src.ingestion.csv_reader import CsvReader

class TestCsvReader(unittest.TestCase):
    def setUp(self):
        self.filepath = 'data/input.csv'
        self.reader = CsvReader(self.filepath)

    def test_read_data(self):
        header, data = self.reader.read_data()
        self.assertEqual(header, ['id', 'name', 'value'])
        self.assertEqual(data, [['1', 'foo', '10'], ['2', 'bar', '20'], ['3', 'baz', '30']])

if __name__ == '__main__':
    unittest.main()
