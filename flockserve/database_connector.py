import sqlite3


"""Module for connecting to a database and storing request and response content."""


class DatabaseConnector:
    """
    Base class for a DatabaseConnector.
    """

    def __init__(self, db_name):
        self.db_name = db_name


class SQLiteConnector(DatabaseConnector):
    """
    Connect to a local SQLite database.
    It will create a new database if the database does not exist.
    """

    def __init__(self, db_name="flockserve.db", table_name="requests", extra_schema={}):
        """
        If changing the schema using extra_schema, make sure db_name or path is changed as well so a new db is created. Otherwise the old schema will be used and a new db won't be created.
        """
        super().__init__(db_name)
        self.table_name = table_name

        # Define the schema as a dictionary
        default_schema = {
            "id": "INTEGER PRIMARY KEY",
            "timestamp": "TEXT",
            "request": "TEXT",
            "response": "TEXT",
            "execution_time": "REAL",
        }

        # Add extra schema to the default schema
        self.schema = {**default_schema, **extra_schema}

        # Only creates the table if it doesn't exist already
        self._create_table()

    async def execute(self, sql, *args, **kwargs):
        """Execute a SQL statement."""
        # Connect to the SQLite database (or create it if it doesn't exist)
        async with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            # Execute the sql statement
            cursor.execute(sql, *args, **kwargs)

    def _create_table(self):
        """Create a table in the database."""

        # Convert the schema into a SQL statement
        columns_sql = ", ".join(
            [f"{col_name} {data_type}" for col_name, data_type in self.schema.items()]
        )
        create_table_sql = (
            f"CREATE TABLE IF NOT EXISTS {self.table_name} ({columns_sql});"
        )

        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            # Execute the sql statement
            cursor.execute(create_table_sql)

    async def add_new_column(self, column_name, data_type):
        """Add a new column to the table."""
        await self.execute(
            f"ALTER TABLE {self.table_name} ADD COLUMN {column_name} {data_type};"
        )

    async def insert(self, data_dict):
        """Insert a row or multiple rows into a table."""

        # To insert single row
        if type(data_dict) == dict:
            # Dynamically construct the INSERT INTO statement
            columns = ", ".join(data_dict.keys())
            placeholders = ", ".join(["?" for _ in data_dict])
            insert_sql = (
                f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders});"
            )

            await self.execute(insert_sql, list(data_dict.values()))

        # To insert multiple rows at once
        elif type(data_dict) == list:
            # Ensure all dictionaries have the same keys/columns
            columns = ", ".join(data_dict[0].keys())
            placeholders = ", ".join(["?" for _ in data_dict[0]])
            insert_sql = (
                f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders});"
            )

            # Prepare the list of tuples from the dictionaries
            values_to_insert = [tuple(data.values()) for data in data_dict]

            # Connect to the SQLite database
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                # Use executemany to insert all rows
                cursor.executemany(insert_sql, values_to_insert)
