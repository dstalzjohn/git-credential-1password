# pycredentialhelper - 1Password Git Credential Helper

## Description

`pycredentialhelper` is a Python-based Git credential helper that securely retrieves Git HTTPS credentials (username and password/token) from your 1Password vault using the 1Password CLI (`op`).

It allows you to manage credentials for multiple accounts on the same Git host (like `dev.azure.com` or `github.com`) by leveraging specific URLs (`git-host` and optionally `git-path`) within your 1Password items.

## Prerequisites

* **Python:** Version 3.9 or higher (specifically tested with 3.11 as per your `.python-version`).
* **1Password CLI (`op`):** The 1Password command-line tool must be installed, configured, and available in your system's PATH. You should be able to run `op --version` successfully. You also need to be signed into your 1Password account via the CLI (`op signin`).
* **`uv` (for development/installation from source):** A fast Python package installer and resolver. ([uv documentation](https://github.com/astral-sh/uv)).

## 1Password Item Setup

To use this helper, you need to structure your 1Password items (typically "Login" items) as follows:

1.  **Create/Edit Item:** For each Git credential (e.g., one per Azure DevOps organization, one for GitHub), create or edit a Login item in 1Password.
2.  **Username/Password:** Fill in the standard username and password fields.
    * For Personal Access Tokens (PATs), the PAT goes into the password field. The username might be optional or a specific value like `pat`, depending on the Git host. The helper defaults to `1password-git-helper` if no username is found in the item.
3.  **Add URLs:** This is the crucial part for the helper to find the correct item. Add custom URL fields with specific **labels**:
    * **`git-host` (Mandatory):**
        * **Label:** `git-host`
        * **URL:** The exact hostname (e.g., `dev.azure.com`, `github.com`). The comparison is case-insensitive.
    * **`git-path` (Optional):**
        * **Label:** `git-path`
        * **URL:** A path prefix that distinguishes this item from others for the *same host*. Examples: `my-azure-org`, `my-github-username`, `my-azure-org/specific-project`. Do *not* include leading/trailing slashes. The comparison is case-insensitive. This is only needed if you have multiple accounts for the same `git-host`.

**Example:**

* **Item 1 (Azure Org A):**
    * Username: `pat`
    * Password: `<PAT_for_Org_A>`
    * URL 1: Label=`git-host`, URL=`dev.azure.com`
    * URL 2: Label=`git-path`, URL=`org-a`
* **Item 2 (Azure Org B):**
    * Username: `pat`
    * Password: `<PAT_for_Org_B>`
    * URL 1: Label=`git-host`, URL=`dev.azure.com`
    * URL 2: Label=`git-path`, URL=`org-b`
* **Item 3 (GitHub):**
    * Username: `your-github-user`
    * Password: `<GitHub_PAT>`
    * URL 1: Label=`git-host`, URL=`github.com`
    * *(No `git-path` needed if it's your only GitHub account)*

## Logic

When Git needs credentials for an HTTPS URL (e.g., `https://dev.azure.com/org-a/project/_git/repo`):

1.  **Input:** Git provides the protocol (`https`), host (`dev.azure.com`), and path (`org-a/project/_git/repo`) to the helper script.
2.  **Host Matching:** The script searches your 1Password vault (via `op item list`) for all items that have a `git-host` URL matching the provided host (case-insensitive).
3.  **Path Matching (if path provided):**
    * If Git provided a non-empty path, the script looks among the host-matching items for those with a `git-path` URL.
    * It finds the item whose `git-path` is the longest prefix of the path provided by Git (case-insensitive comparison). For `org-a/project/_git/repo`, an item with `git-path: org-a` would match. An item with `git-path: org-a/project` would be an even better match.
    * If multiple items have the *same* longest matching prefix, an `AmbiguousItemError` is raised.
    * If items with matching `git-path` prefixes exist, any items matching *only* the host (without a `git-path`) are ignored for this specific request.
    * If no item has a matching `git-path` prefix, but there is exactly one item matching the host that has *no* `git-path` defined, that item is used as a fallback.
4.  **No Path Provided:** If Git does not provide a path (e.g., some GUI clients might not), the script looks for exactly *one* item matching the `git-host`. The `git-path` URLs are ignored. If zero or more than one item matches the host, an error (`ItemNotFoundError` or `AmbiguousItemError`) is raised.
5.  **Credential Retrieval:** Once the unique best-matching item is identified, the script uses `op item get <item_id>` to fetch the username and password fields.
6.  **Output:** If successful, the script prints `username=...` and `password=...` to standard output for Git to consume. All diagnostic and error messages are printed to standard error.

## Installation

### 1. From Source (Recommended)

This method uses `uv` as specified in your `pyproject.toml`.

```bash
# 1. Clone the repository
git clone <your-repository-url>
cd pycredentialhelper

# 2. Ensure you are using the correct Python version (e.g., 3.11)
# If you use a tool like pyenv, it might pick up .python-version automatically.
# Otherwise, activate your Python 3.11 environment manually.
python --version # Verify it's 3.11.x

# 3. Create a virtual environment (Recommended)
python -m venv .venv
source .venv/bin/activate # Linux/macOS
# .\.venv\Scripts\activate # Windows

# 4. Install the package using uv
# This installs the package and its dependencies, making the 'opcred' script available.
uv pip install .

# 5. (Optional) Install development dependencies if you plan to run tests
uv pip install -e ".[dev]"
2. Using pip with Git (Without Cloning First)You can install directly from a Git repository URL 
   if the project is hosted (e.g., on GitHub, GitLab).# Ensure you have Python 3.11 and pip/uv available
# Activate your virtual environment first

# Using uv
uv pip install git+<your-repository-url>

# Or using standard pip
# pip install git+<your-repository-url>
3. From PyPI (If Published)If you decide to publish this package to 
   the Python Package Index (PyPI):# Activate your virtual environment

# Using uv
uv pip install pycredentialhelper

# Or using standard pip
# pip install pycredentialhelper
Git ConfigurationAfter installing the package (which makes the opcred script available in 
your environments PATH), tell Git to use it:# Ensure your virtual environment 
is active OR that the script is globally available

# Find the full path to the installed script (usually needed)
# On Linux/macOS:
which opcred
# On Windows (in Command Prompt):
where opcred
# On Windows (in PowerShell):
Get-Command opcred

# Configure Git globally (or per-repository with --local)
# Replace '/path/to/opcred' with the actual path found above
git config --global credential.helper '/path/to/opcred'

# On Windows, paths might look like 'C:\path\to\.venv\Scripts\opcred.exe'
# Use forward slashes or escaped backslashes in the git config command:
# git config --global credential.helper 'C:/path/to/.venv/Scripts/opcred.exe'
# or
# git config --global credential.helper 'C:\\path\\to\\.venv\\Scripts\\opcred.exe'

# You might need to clear any existing helpers if they conflict:
# git config --global --unset-all credential.helper
# Then add the new one.

```

**Important:** Git needs to be able to find and execute the opcred script. If you installed it in a virtual environment, that environment needs to be active when you run Git commands, or you need to provide the absolute path to the script within the virtual environment in the git config command. Using an absolute path is generally more reliable.

## Usage
Once configured, the credential helper works automatically in the background whenever Git needs to authenticate for an HTTPS remote operation (clone, fetch, pull, push). You don't need to run opcred manually. Git will invoke it, and the script will interact with op to provide the credentials.

## Troubleshooting

* **`op` command not found:** Ensure the 1Password CLI (`op`) is installed and its location is included in your system's PATH environment variable.
* **Authentication Failed:**
    * Verify you are signed in to `op` (`op signin`).
    * Double-check the `git-host` and `git-path` URLs in your 1Password items match the Git remote URL structure exactly (case-insensitivity is handled by the script, but check for typos).
    * Ensure the correct username and password/token are stored in the identified 1Password item.
    * Check `stderr` for error messages from the helper script (Git might hide these unless run with verbose flags, e.g., `GIT_CURL_VERBOSE=1 git pull`).
* **`AmbiguousItemError`:** You have multiple 1Password items that match the criteria.
    * If no path was provided by Git: Ensure only one item exists for that `git-host`.
    * If a path *was* provided: Ensure your `git-path` URLs are specific enough to uniquely identify the correct item, or that only one item lacks a `git-path` if that's the intended fallback. Check the error message for the conflicting item IDs.
* **`ItemNotFoundError`:** No matching item was found based on the `git-host` and `git-path` logic, or the found item doesn't contain a password field. Check your 1Password item setup.
* **Client Doesn't Provide Path:** If using a Git client (like Git Fork, as noted previously) that doesn't provide the path component to the helper, the `git-path` matching logic cannot be used. The helper will fall back to requiring a single, unique item matching only the `git-host`. If multiple items exist for that host, it will result in an `AmbiguousItemError`.
