import os
import pathlib

# Only ONE explicitly allowed root for Milestone 2
ALLOWED_ROOT = r"C:\Projects\local_ai_assistant\assistant_files"

def get_resolved_allowed_root() -> pathlib.Path:
    # Ensure it's absolute and strictly resolved
    path = pathlib.Path(ALLOWED_ROOT).resolve()
    # Create the sandbox if it doesn't exist
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return path

def validate_path(requested_path: str, expected_type: str = None) -> pathlib.Path:
    """
    Validates that a path is safe, normalized, and strictly contained within the allowed root.
    """
    if not isinstance(requested_path, str):
        raise ValueError("Error: Path must be a string.")
    
    # Reject UNC paths and device paths
    if requested_path.startswith(r"\\") or requested_path.startswith("//"):
        raise ValueError("Error: UNC, network, or device paths are not permitted.")
        
    # Prevent drive-relative escapes on Windows (e.g., C:folder)
    if len(requested_path) >= 2 and requested_path[1] == ":" and (len(requested_path) == 2 or requested_path[2] not in ["\\", "/"]):
        raise ValueError("Error: Drive-relative paths are not permitted.")

    try:
        req_path = pathlib.Path(requested_path)
    except Exception:
        raise ValueError("Error: Invalid path format.")

    # Must resolve strict to defeat symlinks, junctions, and relative segments.
    # Note: If the file doesn't exist, resolve(strict=True) will raise FileNotFoundError.
    # We require the path to exist for read-only tools.
    try:
        target = req_path.resolve(strict=True)
    except FileNotFoundError:
        raise ValueError("Error: Path does not exist.")
    except Exception:
        raise ValueError("Error: Cannot resolve path safely.")

    root = get_resolved_allowed_root()

    # Check boundaries carefully (normcase for Windows case-insensitivity)
    target_norm = os.path.normcase(str(target))
    root_norm = os.path.normcase(str(root))

    # To prevent prefix trick (C:\Project vs C:\Project_Secret), use commonpath
    try:
        common = os.path.commonpath([root_norm, target_norm])
        if common != root_norm:
            raise ValueError("Error: Access denied. Path is outside the allowed sandbox.")
    except ValueError:
        # commonpath raises ValueError if paths are on different drives
        raise ValueError("Error: Access denied. Different drives are not permitted.")

    # Type checking if requested
    if expected_type == "dir" and not target.is_dir():
        raise ValueError("Error: Path exists but is not a directory.")
    if expected_type == "file" and not target.is_file():
        raise ValueError("Error: Path exists but is not a file.")

    return target
