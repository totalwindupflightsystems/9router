"""A test module with intentional issues for code review."""
import sqlite3

# BUG: SQL injection — concatenating user input into query
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + str(user_id)
    conn = sqlite3.connect(":memory:")
    return conn.execute(query).fetchone()

# ANTI-PATTERN: mutable default argument
def add_item(item, items=[]):
    items.append(item)
    return items

# BUG: bare except swallowing all errors
def parse_config(path):
    try:
        with open(path) as f:
            return f.read()
    except:
        return ""

# SECURITY: hardcoded API key pattern (test-only but flaggable)
DEFAULT_KEY = "sk-test-12345678901234567890"

# STYLE: magic number
def calculate(price):
    return price * 1.0825  # no named constant for tax rate
