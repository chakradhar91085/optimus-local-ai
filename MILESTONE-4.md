# Milestone 4: Human-in-the-Loop (HITL) Write Capabilities

## Overview
Added strict, safe, user-approved write access for the AI assistant, ensuring the system cannot modify files autonomously while adding text creation and append functionalities.

## Approved HITL Architecture
- **State Suspension**: When the assistant attempts a WRITE operation, the backend suspends the generation loop and saves an immutable `PendingAction`.
- **Client Prompt**: The client UI displays an "Action Approval Required" box detailing the requested tool, target relative path, character count, and a preview of the content.
- **REST Endpoints**: Approval (`/api/action/approve`) and Denial (`/api/action/reject`) endpoints accept only an `action_id`.
- **Backend Execution**: The backend uses its own internal locked arguments to execute the action securely. No client-side tampering is possible.
- **Agent Resumption**: The tool result (success or denial) is injected into the conversation, and the agent loop seamlessly resumes.

## WRITE Tools Added
1. `create_text_file(path, content)`
2. `append_text_file(path, content)`

**Specifically Excluded:** `delete`, `rename`, `move`, `overwrite`, shell/system commands.

## Sandbox & Write Path Validation
All writes are strictly bounded to `C:\Projects\local_ai_assistant\assistant_files`.

For `create_text_file`:
- Validates the requested parent directory strictly exists.
- Uses path-component validation to ensure the parent is inside the sandbox (defeats `..` and sibling-prefix attacks).
- Refuses to write if the destination file already exists.
- Uses `x` mode (exclusive creation) for OS-level race condition protection.

For `append_text_file`:
- Validates the target strictly exists.
- Checks against `MAX_WRITABLE_FILE_SIZE` to prevent unbounded growth.

## Limits Enforced
- **Writable Extensions**: `.txt, .md, .json, .csv`
- **Max Write Content per Action**: `50,000` characters
- **Max Writable File Size**: `1,000,000` bytes
- **Action TTL**: `15` minutes

## Security Mechanisms
- **Replay & Concurrency Protection**: Single-use action IDs protected by an atomic `asyncio.Lock()`.
- **Audit Logging**: Metadata-only logs recorded in `data/audit.log` indicating every transition without spilling private content.
- **Immutable State**: Client cannot supply arguments during approval.

## RAG Integration
Writing a file does not auto-refresh the RAG index. Explicit update requests are still required.

## Known Limitations
- Restarting the backend clears all pending actions.
- Only text-based file creation and appending are supported. No binary files.
