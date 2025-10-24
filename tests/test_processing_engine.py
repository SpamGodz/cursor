import unittest
from src.processing.engine import ProcessingEngine

def uppercase_name(data):
    header, rows = data
    name_index = header.index('name')
    new_rows = []
    for row in rows:
        new_row = list(row)
        new_row[name_index] = new_row[name_index].upper()
        new_rows.append(tuple(new_row))
    return header, new_rows

def double_value(data):
    header, rows = data
    value_index = header.index('value')
    new_rows = []
    for row in rows:
        new_row = list(row)
        new_row[value_index] = str(int(new_row[value_index]) * 2)
        new_rows.append(tuple(new_row))
    return header, new_rows

class TestProcessingEngine(unittest.TestCase):
    def test_process(self):
        transformations = [uppercase_name, double_value]
        engine = ProcessingEngine(transformations)
        data = (['id', 'name', 'value'], [('1', 'foo', '10'), ('2', 'bar', '20')])
        processed_data = engine.process(data)
        expected_data = (['id', 'name', 'value'], [('1', 'FOO', '20'), ('2', 'BAR', '40')])
        self.assertEqual(processed_data, expected_data)

if __name__ == '__main__':
    unittest.main()
