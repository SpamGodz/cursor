import unittest
import os
from src.egress.csv_writer import CsvWriter

class TestCsvWriter(unittest.TestCase):
    def setUp(self):
        self.filepath = 'data/output.csv'
        self.writer = CsvWriter(self.filepath)

    def tearDown(self):
        if os.path.exists(self.filepath):
            os.remove(self.filepath)

    def test_write_data(self):
        header = ['id', 'name', 'value']
        data = [['1', 'foo', '10'], ['2', 'bar', '20']]
        self.writer.write_data(header, data)
        with open(self.filepath, 'r') as f:
            lines = f.readlines()
            self.assertEqual(lines[0].strip(), 'id,name,value')
            self.assertEqual(lines[1].strip(), '1,foo,10')
            self.assertEqual(lines[2].strip(), '2,bar,20')

if __name__ == '__main__':
    unittest.main()
