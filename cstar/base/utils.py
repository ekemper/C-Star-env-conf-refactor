import re
import subprocess
from math import ceil
from typing import Tuple
from pathlib import Path
from cstar.base.environment import _CSTAR_CONFIG_FILE


def _write_to_config_file(config_file_str: str) -> None:
    """Write config_file_str to C-Star config file to configure environment on
    import."""

    if not Path(_CSTAR_CONFIG_FILE).exists():
        print(f"Updating environment in C-Star configuration file {_CSTAR_CONFIG_FILE}")
        base_conf_str = (
            "# This file was generated by C-Star and is specific to your machine. "
            + "# It contains environment information related to your cases & their dependencies. "
            + "# You can safely delete this file, but C-Star may prompt you to re-install things if so."
        )

        base_conf_str += "\nimport os\nfrom cstar.base.environment import _CSTAR_ENVIRONMENT_VARIABLES\n"
        base_conf_str += "def get_user_environment():\n"
        config_file_str = base_conf_str + config_file_str

    with open(_CSTAR_CONFIG_FILE, "a") as f:
        f.write(config_file_str)


def _clone_and_checkout(
    source_repo: str, local_path: str | Path, checkout_target: str
) -> None:
    """Clone `source_repo` to `local_path` and checkout `checkout_target`."""
    clone_result = subprocess.run(
        f"git clone {source_repo} {local_path}",
        shell=True,
        capture_output=True,
        text=True,
    )
    if clone_result.returncode != 0:
        raise RuntimeError(
            f"Error {clone_result.returncode} when cloning repository "
            + f"{source_repo} to {local_path}. Error messages: "
            + f"\n{clone_result.stderr}"
        )
    print(f"Cloned repository {source_repo} to {local_path}")

    checkout_result = subprocess.run(
        f"git checkout {checkout_target}",
        cwd=local_path,
        shell=True,
        capture_output=True,
        text=True,
    )
    if checkout_result.returncode != 0:
        raise RuntimeError(
            f"Error {checkout_result.returncode} when checking out "
            + f"{checkout_target} in git repository {local_path}. Error messages: "
            + f"\n{checkout_result.stderr}"
        )
    print(f"Checked out {checkout_target} in git repository {local_path}")


def _get_repo_remote(local_root: str | Path) -> str:
    """Take a local repository path string (local_root) and return as a string the
    remote URL."""
    return subprocess.run(
        f"git -C {local_root} remote get-url origin",
        shell=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _get_repo_head_hash(local_root: str | Path) -> str:
    """Take a local repository path string (local_root) and return as a string the
    commit hash of HEAD."""
    return subprocess.run(
        f"git -C {local_root} rev-parse HEAD",
        shell=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _get_hash_from_checkout_target(repo_url: str, checkout_target: str) -> str:
    """Take a git checkout target (any `arg` accepted by `git checkout arg`) and return
    a commit hash.

    If the target is a 7 or 40 digit hexadecimal string, it is assumed `checkout_target`
    is already a git hash, so `checkout_target` is returned.

    Otherwise, `git ls-remote` is used to obtain the hash associated with `checkout_target`.

    Parameters:
    -----------
    repo_url: str
        URL pointing to a git-controlled repository
    checkout_target: str
        Any valid argument that can be supplied to `git checkout`

    Returns:
    --------
    git_hash: str
        A git commit hash associated with the checkout target
    """

    # First check if the checkout target is a 7 or 40 digit hexadecimal string
    is_potential_hash = bool(re.match(r"^[0-9a-f]{7}$", checkout_target)) or bool(
        re.match(r"^[0-9a-f]{40}$", checkout_target)
    )

    # Then try ls-remote to see if there is a match
    # (no match if either invalid target or a valid hash):
    ls_remote = subprocess.run(
        "git ls-remote " + repo_url + " " + checkout_target,
        shell=True,
        capture_output=True,
        text=True,
    ).stdout

    if len(ls_remote) == 0:
        if is_potential_hash:
            # just return the input target assuming a hash, but can't validate
            return checkout_target
        else:
            raise ValueError(
                f"supplied checkout_target ({checkout_target}) does not appear "
                + f"to be a valid reference for this repository ({repo_url})"
            )
    else:
        return ls_remote.split()[0]


def _calculate_node_distribution(
    n_cores_required: int, tot_cores_per_node: int
) -> Tuple[int, int]:
    """Determine how many nodes and cores per node to request from a job scheduler.

    For example, if requiring 192 cores for a job on a system with 128 cores per node,
    this method advises requesting 2 nodes with 96 cores each.

    Parameters:
    -----------
    n_cores_required: int
        The number of cores required for the job
    tot_cores_per_node: int
        The number of cores per node on the target system

    Returns:
    --------
    n_nodes_to_request: int
        The number of nodes to request from the scheduler
    cores_to_request_per_node: int
        The number of cores per node to request from the scheduler
    """
    n_nodes_to_request = ceil(n_cores_required / tot_cores_per_node)
    cores_to_request_per_node = ceil(
        tot_cores_per_node
        - ((n_nodes_to_request * tot_cores_per_node) - n_cores_required)
        / n_nodes_to_request
    )

    return n_nodes_to_request, cores_to_request_per_node


def _replace_text_in_file(file_path: str | Path, old_text: str, new_text: str) -> bool:
    """Find and replace a string in a text file.

    This function creates a temporary file where the changes are written, then
    overwrites the original file.

    Parameters:
    -----------
    file_path: str | Path
        The local path to the text file
    old_text: str
        The text to be replaced
    new_text: str
        The text that will replace `old_text`

    Returns:
    --------
    text_replaced: bool
       True if text was found and replaced, False if not found
    """
    text_replaced = False
    file_path = Path(file_path).resolve()
    temp_file_path = Path(str(file_path) + ".tmp")

    with open(file_path, "r") as read_file, open(temp_file_path, "w") as write_file:
        for line in read_file:
            if old_text in line:
                text_replaced = True
            new_line = line.replace(old_text, new_text)
            write_file.write(new_line)

    temp_file_path.rename(file_path)

    return text_replaced


def _list_to_concise_str(
    input_list, item_threshold=4, pad=16, items_are_strs=True, show_item_count=True
):
    """Take a list and return a concise string representation of it.

    Parameters:
    -----------
    input_list (list of str):
       The list of to be represented
    item_threshold (int, default = 4):
       The number of items beyond which to truncate the str to item0,...itemN
    pad (int, default = 16):
       The number of whitespace characters to prepend newlines with
    items_are_strs (bool, default = True):
       Will use repr formatting ([item1,item2]->['item1','item2']) for lists of strings
    show_item_count (bool, default = True):
       Will add <N items> to the end of a truncated representation

    Returns:
    -------
    list_str: str
       The string representation of the list

    Examples:
    --------
    In: print("my_list: "+_list_to_concise_str(["myitem0","myitem1",
                             "myitem2","myitem3","myitem4"],pad=11))
    my_list: ['myitem0',
              'myitem1',
                  ...
              'myitem4']<5 items>
    """
    list_str = ""
    pad_str = " " * pad
    if show_item_count:
        count_str = f"<{len(input_list)} items>"
    else:
        count_str = ""
    if len(input_list) > item_threshold:
        list_str += f"[{repr(input_list[0]) if items_are_strs else input_list[0]},"
        list_str += (
            f"\n{pad_str}{repr(input_list[1]) if items_are_strs else input_list[1]},"
        )
        list_str += f"\n{pad_str}   ..."
        list_str += f"\n{pad_str}{repr(input_list[-1]) if items_are_strs else input_list[-1]}] {count_str}"
    else:
        list_str += "["
        list_str += f",\n{pad_str}".join(
            (repr(listitem) if items_are_strs else listitem) for listitem in input_list
        )
        list_str += "]"
    return list_str


def _dict_to_tree(input_dict: dict, prefix: str = "") -> str:
    """Recursively converts a dictionary into a tree-like string representation.

    Parameters:
    -----------
     input_dict (dict):
        The dictionary to convert. Takes the form of nested dictionaries with a list
        at the lowest level
    prefix (str, default=""):
        Used for internal recursion to maintain current branch position

    Returns:
    --------
    tree_str:
       A string representing the tree structure.

    Examples:
    ---------
    print(_dict_to_tree({'branch1': {'branch1a': ['twig1ai','twig1aii']},
                         'branch2': {'branch2a': ['twig2ai','twig2aii'],
                                     'branch2b': ['twig2bi',]}
                 }))

    ├── branch1
    │   └── branch1a
    │       ├── twig1ai
    │       └── twig1aii
    └── branch2
        ├── branch2a
        │   ├── twig2ai
        │   └── twig2aii
        └── branch2b
            └── twig2bi
    """
    tree_str = ""
    keys = list(input_dict.keys())

    for i, key in enumerate(keys):
        # Determine if this is the last key at this level
        branch = "└── " if i == len(keys) - 1 else "├── "
        sub_prefix = "    " if i == len(keys) - 1 else "│   "

        # If the value is a dictionary, recurse into it
        if isinstance(input_dict[key], dict):
            tree_str += f"{prefix}{branch}{key}\n"
            tree_str += _dict_to_tree(input_dict[key], prefix + sub_prefix)
        # If the value is a list, print each item in the list
        elif isinstance(input_dict[key], list):
            tree_str += f"{prefix}{branch}{key}\n"
            for j, item in enumerate(input_dict[key]):
                item_branch = "└── " if j == len(input_dict[key]) - 1 else "├── "
                tree_str += f"{prefix}{sub_prefix}{item_branch}{item}\n"

    return tree_str
