import os
from src.config import Config
from src.ingestion.csv_reader import CsvReader
from src.database.sqlite_connector import SqliteConnector
from src.processing.engine import ProcessingEngine
from src.egress.csv_writer import CsvWriter

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

def main():
    # Load configuration
    config = Config('config/config.ini')
    db_config = config.get_database_config()
    data_source_config = config.get_data_source_config()

    # Ingest data
    reader = CsvReader(data_source_config['path'])
    header, data = reader.read_data()

    # Process data
    transformations = [uppercase_name, double_value]
    engine = ProcessingEngine(transformations)
    processed_header, processed_data = engine.process((header, data))

    # Store data in database
    if os.path.exists(db_config['path']):
        os.remove(db_config['path'])
    db_connector = SqliteConnector(db_config['path'])
    db_connector.connect()
    db_connector.create_table('processed_data', [f'{col} TEXT' for col in processed_header])
    db_connector.insert_data('processed_data', processed_data)
    db_connector.disconnect()

    # Egress data
    writer = CsvWriter('data/output.csv')
    writer.write_data(processed_header, processed_data)

if __name__ == '__main__':
    main()
