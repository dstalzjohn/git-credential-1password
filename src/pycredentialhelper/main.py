#!/usr/bin/env python3

import sys
import subprocess
import json
from typing import Tuple


class ItemNotFoundError(Exception):
    pass

def get_item_id_for_git_host(git_host: str) -> str:
    result = subprocess.run(
        ["op", "item", "list", "--format", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    item_list = json.loads(result.stdout)
    for item in item_list:
        # check urls:
        urls = item.get("urls", [])
        for url in urls:
            if url.get("label") == "git-url" and url.get("href") == git_host:
                return item.get("id")

    raise ItemNotFoundError("Could not find git host {}".format(git_host))


def get_password_from_1password(git_host: str) -> Tuple[str, str]:
    try:
        item_id = get_item_id_for_git_host(git_host)
        # Run the `op` CLI command to fetch the item
        result = subprocess.run(
            ["op", "item", "get", item_id, "--format", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        item = json.loads(result.stdout)
        username = None
        password = None
        # Extract the password field
        for field in item.get("fields", []):
            if field.get("id") == "username":
                username = field.get("value")
            if field.get("id") == "password":
                password = field.get("value")

        return username, password
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving item from 1Password: {e}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON output from 1Password: {e}", file=sys.stderr)
    raise ItemNotFoundError("Could not get password from 1Password")

def main():
    input_data = sys.stdin.read()
    credential = dict(line.split('=', 1) for line in input_data.splitlines() if '=' in line)
    action = sys.argv[1] if len(sys.argv) > 1 else None
    if action == 'get':
        if credential.get('protocol') == 'https':
            host = credential.get('host')
            # Replace 'Azure DevOps PAT' and 'Your Vault Name' with your actual item name and vault
            username, password = get_password_from_1password(host)
            if password is not None:
                print(f'username={username}')
                print(f'password={password}')

if __name__ == '__main__':
    main()


"""
protocol=https
host=dev.azure.com
path=your_organization/your_project/_git/your_repository
"""