import csv

class CsvReader:
    def __init__(self, filepath):
        self.filepath = filepath

    def read_data(self):
        with open(self.filepath, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            data = [row for row in reader]
        return header, data
