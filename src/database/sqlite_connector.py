import sqlite3

class SqliteConnector:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def execute_query(self, query, params=()):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        self.conn.commit()
        return cursor

    def create_table(self, table_name, columns):
        columns_str = ', '.join(columns)
        query = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_str})"
        self.execute_query(query)

    def insert_data(self, table_name, data):
        if not data:
            return
        placeholders = ', '.join(['?'] * len(data[0]))
        query = f"INSERT INTO {table_name} VALUES ({placeholders})"
        cursor = self.conn.cursor()
        cursor.executemany(query, data)
        self.conn.commit()
