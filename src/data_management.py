import json
from datetime import datetime
from src.config import STATE_MEMORY_FILE, AGENT_DB_FILE, LINES_FILE

class StateManager:
    def __init__(self):
        self.memory = {}
        self.load_memory()

    def load_memory(self):
        try:
            with open(STATE_MEMORY_FILE, 'r') as f:
                self.memory = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.memory = {}

    def save_memory(self):
        with open(STATE_MEMORY_FILE, 'w') as f:
            json.dump(self.memory, f, indent=4)

    def check_status(self, identifier):
        return self.memory.get(identifier)

    def update_status(self, identifier):
        timestamp = datetime.now().strftime("%H:%M %d/%b/%Y")
        self.memory[identifier] = timestamp
        self.save_memory()

class DatabaseManager:
    def __init__(self):
        self.database = []
        self.load_database()

    def load_database(self):
        try:
            with open(AGENT_DB_FILE, 'r') as f:
                self.database = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.database = []

    def save_database(self):
        with open(AGENT_DB_FILE, 'w') as f:
            json.dump(self.database, f, indent=4)

    def get_record(self, identifier):
        """Finds a record by its primary identifier."""
        for record in self.database:
            if record.get('identifier') == identifier:
                return record
        return None

    def identifier_exists(self, identifier):
        """Checks if a record with the given identifier already exists."""
        return self.get_record(identifier) is not None

    def add_record(self, identifier, data={}):
        """Adds a new record if the identifier doesn't exist."""
        if not self.identifier_exists(identifier):
            record = {'identifier': identifier, **data}
            record['last_updated'] = datetime.now().isoformat()
            self.database.append(record)
            self.save_database()
            return True
        return False

    def update_record(self, identifier, data):
        """Updates an existing record with new data."""
        record = self.get_record(identifier)
        if record:
            record.update(data)
            record['last_updated'] = datetime.now().isoformat()
            self.save_database()
            return True
        return False

    def delete_record(self, identifier):
        """Deletes a record by its identifier."""
        record = self.get_record(identifier)
        if record:
            self.database.remove(record)
            self.save_database()
            return True
        return False

class LineManager:
    def __init__(self):
        self.lines = {}
        self.load_lines()

    def load_lines(self):
        try:
            with open(LINES_FILE, 'r') as f:
                self.lines = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.lines = {}

    def save_lines(self):
        with open(LINES_FILE, 'w') as f:
            json.dump(self.lines, f, indent=4)

    def get_all_lines(self):
        return self.lines.keys()

    def get_line(self, name):
        return self.lines.get(name)

    def add_line(self, line_data):
        self.lines[line_data["name"]] = line_data
        self.save_lines()

    def update_line(self, old_name, line_data):
        if old_name in self.lines:
            del self.lines[old_name]
        self.lines[line_data["name"]] = line_data
        self.save_lines()

    def delete_line(self, name):
        if name in self.lines:
            del self.lines[name]
            self.save_lines()
