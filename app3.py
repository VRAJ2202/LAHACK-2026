"""
Config loader for SpecMem Demo — intentionally buggy for agent demo.

Bug: KeyError when required keys are missing from config sections.
"""

import json


def load_config(filepath: str) -> dict:
    with open(filepath, "r") as f:
        return json.load(f)


def setup_database(config: dict) -> dict:
    db = config["database"]
    return {
        "host": db["host"],
        "port": db["port"],
        "timeout": db["timeout"],
    }


def setup_email(config: dict) -> dict:
    email = config["email"]
    return {
        "sender": email["sender"],
        "recipients": email["recipients"],
    }


def main():
    config = load_config("config.json")
    db = setup_database(config)
    email = setup_email(config)
    print(f"Database: {db['host']}:{db['port']} (timeout={db['timeout']}s)")
    print(f"Email sender: {email['sender']}")
    print(f"Recipients: {', '.join(email['recipients'])}")
    print("Config loaded successfully.")


if __name__ == "__main__":
    main()
