#!/usr/bin/env python3

import sys
import subprocess
import json
from typing import Tuple, Optional, List, Dict, Any

# --- Custom Exceptions ---

class CredentialHelperError(Exception):
    """Base exception for credential helper errors."""
    pass

class ItemNotFoundError(CredentialHelperError):
    """Raised when no suitable 1Password item can be found."""
    pass

class AmbiguousItemError(CredentialHelperError):
    """Raised when multiple 1Password items match ambiguously."""
    pass

class OpCommandError(CredentialHelperError):
    """Raised when the 'op' CLI command fails."""
    pass

# --- Helper Functions ---

def _run_op_command(op_args: List[str]) -> List[Any]:
    """
    Runs an 'op' CLI command and returns the parsed JSON output.

    Args:
        op_args: A list of arguments to pass to the 'op' command
                 (e.g., ["item", "list", "--format", "json"]).

    Returns:
        The parsed JSON output as list.

    Raises:
        OpCommandError: If the command fails or returns invalid JSON.
    """
    try:
        # Ensure 'op' is in the PATH and executable
        result = subprocess.run(
            ["op"] + op_args,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8' # Ensure correct decoding
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        # Print command errors to stderr
        error_message = f"Error running 'op {' '.join(op_args)}': {e}. Stderr: {e.stderr.strip()}"
        print(error_message, file=sys.stderr)
        raise OpCommandError(error_message) from e
    except json.JSONDecodeError as e:
        # Print JSON parsing errors to stderr
        error_message = f"Error parsing JSON output from 'op {' '.join(op_args)}': {e}"
        print(error_message, file=sys.stderr)
        raise OpCommandError(error_message) from e
    except FileNotFoundError:
        # Print 'op not found' error to stderr
        error_message = "Error: 'op' command not found. Is the 1Password CLI installed and in your PATH?"
        print(error_message, file=sys.stderr)
        raise OpCommandError(error_message)


def _find_best_matching_item_id(host: str, path: Optional[str]) -> str:
    """
    Finds the most specific 1Password item ID based on host and path.

    It first filters items by matching 'git-host' URL (case-insensitive).

    If a non-empty path is provided by Git, it selects the item whose
    'git-path' URL (case-insensitive) is the longest prefix of the input path.
    If multiple items have the same longest matching prefix, it raises AmbiguousItemError.
    If path-matching items exist, items without a 'git-path' are ignored for this host.

    If the path provided by Git is empty or None, it looks for exactly one
    item matching the host. If zero or multiple items match the host, it raises
    ItemNotFoundError or AmbiguousItemError respectively. The 'git-path' URL
    is ignored in this case.

    Args:
        host: The hostname (e.g., 'dev.azure.com').
        path: The repository path provided by Git (e.g., 'org/project/_git/repo'),
              or None.

    Returns:
        The item ID of the best matching 1Password item.

    Raises:
        ItemNotFoundError: If no item matches the host or criteria.
        AmbiguousItemError: If multiple items match ambiguously.
        OpCommandError: If the 'op' command fails.
    """
    # Debug output goes to stderr
    print(f"Debug: Searching for host='{host}', path='{path}'", file=sys.stderr)
    # Normalize path case-insensitively and check if it's effectively empty
    normalized_input_path_lower = (path or "").strip('/').lower()
    is_input_path_empty = not normalized_input_path_lower
    print(f"Debug: Normalized lower path='{normalized_input_path_lower}', Is empty: {is_input_path_empty}", file=sys.stderr)

    # 1. Get all items
    all_items = _run_op_command(["item", "list", "--format", "json"])

    # 2. Filter items matching the host (case-insensitive)
    candidate_items = []
    host_lower = host.lower() # Lowercase host for comparison
    for item_summary in all_items:
        item_id = item_summary.get("id")
        if not item_id:
            continue

        urls = item_summary.get("urls", [])
        item_host = None
        item_path = None # Path associated with this specific item

        for url_info in urls:
            label = url_info.get("label")
            href = url_info.get("href")
            if not href: continue

            # Compare host case-insensitively
            if label == "git-host" and href.strip().lower() == host_lower:
                item_host = href.strip() # Store original casing if needed later
            elif label == "git-path":
                item_path = href.strip('/') # Normalize stored path (remove slashes)

        if item_host: # Must have a matching git-host
            candidate_items.append({
                "id": item_id,
                "title": item_summary.get("title", "Unknown Title"),
                "git_host": item_host,
                "git_path": item_path # Can be None
            })

    # Initial check: Did we find *any* candidates for the host?
    if not candidate_items:
        raise ItemNotFoundError(f"No 1Password item found with git-host URL '{host}'.")

    # Debug output to stderr
    print(f"Debug: Found {len(candidate_items)} candidates matching host '{host}': {[c['id'] for c in candidate_items]}", file=sys.stderr)

    # 3. Select the best match based on path presence
    best_match_id = None

    if is_input_path_empty:
        # --- Case: No path provided by Git ---
        # Ignore 'git-path' URLs. Require exactly one match for the host.
        print(f"Debug: Input path is empty. Looking for exactly one match for host '{host}'.", file=sys.stderr)
        if len(candidate_items) == 1:
            best_match_id = candidate_items[0]["id"]
            print(f"Debug: Found unique host match (no path needed): ID={best_match_id}", file=sys.stderr)
        elif len(candidate_items) > 1:
            ids = [item['id'] for item in candidate_items]
            raise AmbiguousItemError(
                f"Multiple items found for host '{host}' ({ids}). "
                f"Provide a 'path' in the Git URL or ensure only one item exists for this host in 1Password "
                f"to use it without a path."
            )
        else:
             # This case should have been caught earlier, but defensively:
             raise ItemNotFoundError(f"No 1Password item found for host '{host}'.")

    else:
        # --- Case: Path provided by Git ---
        # Perform the specific path matching logic.
        print(f"Debug: Input path '{normalized_input_path_lower}' provided. Performing path matching.", file=sys.stderr)
        path_matching_candidates = []
        no_path_candidates = [] # Candidates matching host but having no git-path URL

        for item in candidate_items:
            stored_path = item.get("git_path")
            if stored_path is None:
                no_path_candidates.append(item)
            # Compare paths case-insensitively
            elif normalized_input_path_lower.startswith(stored_path.lower()):
                path_matching_candidates.append(item)

        # Debug output to stderr
        print(f"Debug: Path matching candidates: {[c['id'] for c in path_matching_candidates]}", file=sys.stderr)
        print(f"Debug: No path candidates: {[c['id'] for c in no_path_candidates]}", file=sys.stderr)

        if path_matching_candidates:
            # Find the best among those with a matching path prefix
            if len(path_matching_candidates) == 1:
                best_match_item = path_matching_candidates[0]
            else:
                # Multiple matches, find the one with the longest path prefix
                best_candidates_by_len = []
                current_max_len = -1
                for item in path_matching_candidates:
                    path_len = len(item["git_path"]) # git_path is not None here
                    if path_len > current_max_len:
                        current_max_len = path_len
                        best_candidates_by_len = [item]
                    elif path_len == current_max_len:
                        best_candidates_by_len.append(item)

                if len(best_candidates_by_len) == 1:
                    best_match_item = best_candidates_by_len[0]
                else:
                    # Ambiguity: multiple items have the same longest matching path prefix
                    ids = [item['id'] for item in best_candidates_by_len]
                    ambiguous_path = best_candidates_by_len[0]['git_path']
                    raise AmbiguousItemError(
                        f"Multiple items found for host '{host}' with the same longest matching "
                        f"git-path prefix ('{ambiguous_path}', compared case-insensitively): IDs {ids}."
                    )
            best_match_id = best_match_item["id"]
            print(f"Debug: Selected best path match: ID={best_match_id}, Title='{best_match_item['title']}', GitPath='{best_match_item.get('git_path')}'", file=sys.stderr)

        elif no_path_candidates:
            # No path matched, but items without a path exist. Use one ONLY if it's unique.
             print(f"Debug: No matching git-path found, checking items without a git-path.", file=sys.stderr)
             if len(no_path_candidates) == 1:
                 best_match_item = no_path_candidates[0]
                 best_match_id = best_match_item["id"]
                 print(f"Debug: Selected unique host match with no git-path: ID={best_match_id}, Title='{best_match_item['title']}'", file=sys.stderr)
             else:
                 # Ambiguity: Multiple items match the host but have no git-path defined.
                 # This is ambiguous when a path *was* provided but didn't match any specific git-path.
                 ids = [item['id'] for item in no_path_candidates]
                 raise AmbiguousItemError(
                     f"Path '{path}' provided, but no item with a matching 'git-path' prefix found. "
                     f"Multiple items exist for host '{host}' without a 'git-path': IDs {ids}. "
                     f"Define a 'git-path' for the correct item."
                 )
        else:
             # No candidates matched the path prefix, and no candidates without a path were found either.
             raise ItemNotFoundError(
                 f"No item found for host '{host}' whose git-path (case-insensitive) matches the prefix of '{path or ''}' "
                 f"and no fallback item without a git-path was found either."
             )

    # Ensure we have a best_match_id before returning
    if best_match_id is None:
         # This should not happen if logic is correct, but acts as a safeguard
         print("Error: Internal logic error - failed to determine best_match_id.", file=sys.stderr)
         raise CredentialHelperError("Internal error selecting 1Password item.")

    return best_match_id



def _fetch_credentials_for_item(item_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetches username and password from a specific 1Password item.

    Args:
        item_id: The ID of the 1Password item.

    Returns:
        A tuple containing (username, password). Either can be None if not found.

    Raises:
        OpCommandError: If the 'op' command fails.
        ItemNotFoundError: If the password field cannot be found.
    """
    item_details = _run_op_command(["item", "get", item_id, "--format", "json"])

    username = None
    password = None

    # Prioritize fields marked with purpose USERNAME or PASSWORD
    for field in item_details.get("fields", []):
        field_purpose = field.get("purpose")
        if field_purpose == "USERNAME":
            username = field.get("value")
        elif field_purpose == "PASSWORD":
            password = field.get("value")

    # Fallback to common labels/IDs if purpose is not set
    if username is None or password is None:
        for field in item_details.get("fields", []):
            field_id = field.get("id")
            field_label = field.get("label")

            if username is None and (field_id == "username" or field_label == "username"):
                username = field.get("value")
            if password is None and (field_id == "password" or field_label == "password"):
                password = field.get("value")

    # Simple heuristic fallback if standard fields aren't found (less reliable)
    if username is None and password is None:
         for field in item_details.get("fields", []):
             field_type = field.get("type")
             # Avoid overwriting if already found via purpose/label
             if username is None and field_type in ["STRING", "EMAIL"] and not field.get("purpose"):
                  username = field.get("value")
             elif password is None and field_type == "CONCEALED" and not field.get("purpose"):
                  password = field.get("value")

    if password is None:
         # If still no password, we cannot proceed. Error to stderr.
         error_msg = f"Password field not found in item {item_id}."
         print(f"Error: {error_msg}", file=sys.stderr)
         raise ItemNotFoundError(error_msg) # Raise exception to stop processing

    return username, password

# --- Main Function ---

def main():
    """
    Main function for the Git credential helper.
    Parses input from Git, finds credentials in 1Password, and prints them
    ONLY to stdout upon success. Errors/debug info go to stderr.
    """
    # Check if the action is 'get'. Exit silently for other actions.
    if len(sys.argv) < 2 or sys.argv[1] != 'get':
        sys.exit(0) # Exit normally, do nothing for 'store'/'erase'

    # Read credential data from stdin
    input_data = sys.stdin.read()
    print(f"Debug: Input Data='{input_data}'", file=sys.stderr)
    credential = {}
    for line in input_data.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            credential[key.strip()] = value.strip()

    protocol = credential.get('protocol')
    host = credential.get('host')
    path = credential.get('path') # Path can be None or empty string

    # Only proceed for https protocol with a host
    if protocol == 'https' and host:
        try:
            # Find the most specific item ID matching host and path
            item_id = _find_best_matching_item_id(host, path)

            # Fetch the credentials for that specific item
            username, password = _fetch_credentials_for_item(item_id)

            # --- CRITICAL SECTION ---
            # Only print to STDOUT if password was found successfully.
            # Git requires a username. Provide one if found, otherwise a default.
            print(f"username={username if username else '1password-git-helper'}")
            print(f"password={password}")
            sys.exit(0) # Success - credentials provided to Git

        except (ItemNotFoundError, AmbiguousItemError, OpCommandError) as e:
            # Log the specific error to stderr
            print(f"Credential helper error: {e}", file=sys.stderr)
            sys.exit(1) # Failure - signifies no credentials found or error occurred
        except Exception as e:
            # Catch any unexpected errors and log to stderr
            print(f"Unexpected credential helper error: {e}", file=sys.stderr)
            sys.exit(1) # Failure

    # If protocol wasn't https or host was missing, or any other failure path
    # not caught above, exit indicating failure.
    # No output should be printed to stdout in failure cases.
    sys.exit(1)


if __name__ == '__main__':
    main()
