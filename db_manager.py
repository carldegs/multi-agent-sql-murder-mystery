import sqlite3

class DatabaseManager:
    def __init__(self, db_file):
        self.db_file = db_file
        self.connection = None

    def connect(self):
        self.connection = sqlite3.connect(self.db_file)
        print(f"Connected to database: {self.db_file}")

    def execute_query(self, query):
        if not self.connection:
            raise Exception("Database connection is not established.")
        cursor = self.connection.cursor()
        cursor.execute(query)
        return cursor.fetchall()

    def close(self):
        if self.connection:
            self.connection.close()
            print("Database connection closed.")
