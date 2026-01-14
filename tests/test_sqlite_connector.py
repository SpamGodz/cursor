import unittest
import os
import sqlite3
from src.database.sqlite_connector import SqliteConnector

class TestSqliteConnector(unittest.TestCase):
    def setUp(self):
        self.db_path = 'data/test.db'
        self.connector = SqliteConnector(self.db_path)
        self.connector.connect()

    def tearDown(self):
        self.connector.disconnect()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_table(self):
        self.connector.create_table('test_table', ['id INTEGER', 'name TEXT'])
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'")
        self.assertIsNotNone(cursor.fetchone())
        conn.close()

    def test_insert_data(self):
        self.connector.create_table('test_table', ['id INTEGER', 'name TEXT'])
        self.connector.insert_data('test_table', [(1, 'foo'), (2, 'bar')])
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM test_table")
        data = cursor.fetchall()
        self.assertEqual(data, [(1, 'foo'), (2, 'bar')])
        conn.close()

if __name__ == '__main__':
    unittest.main()
