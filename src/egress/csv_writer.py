import csv

class CsvWriter:
    def __init__(self, filepath):
        self.filepath = filepath

    def write_data(self, header, data):
        with open(self.filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(data)
