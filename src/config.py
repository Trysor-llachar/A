import os

# Get the absolute path of the project root directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Define absolute paths for all data files
NOTES_FILE = os.path.join(ROOT_DIR, "notes_data.json")
BACKUP_FILE = os.path.join(ROOT_DIR, "backup_notes.json")
RULES_FILE = os.path.join(ROOT_DIR, "rules.json")
PROCESSES_FILE = os.path.join(ROOT_DIR, "processes.json")
KB_FILE = os.path.join(ROOT_DIR, "knowledge.json")
STATE_MEMORY_FILE = os.path.join(ROOT_DIR, "state_memory.json")
AGENT_DB_FILE = os.path.join(ROOT_DIR, "agent_database.json")
LINES_FILE = os.path.join(ROOT_DIR, "lines_config.json")
NAVIGATION_PATHS_FILE = os.path.join(ROOT_DIR, "navigation_paths.json")
