from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from config import settings

ALLOWED_FILENAMES = {"main.py", "requirements.txt"}


def _storage_dir(user_id: int, function_id: int) -> Path:
    return Path(settings.storage_path) / str(user_id) / str(function_id)


def validate_upload(upload: UploadFile, expected_name: str) -> None:
    if expected_name not in ALLOWED_FILENAMES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"File '{expected_name}' is not allowed")
    if expected_name == "main.py" and (not upload.filename or not upload.filename.endswith(".py")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Code file must be a .py file")


async def save_function_files(
    user_id: int,
    function_id: int,
    code_file: UploadFile,
    requirements_file: UploadFile | None,
) -> list[tuple[str, str]]:
    """
    Saves uploaded files to storage/<user_id>/<function_id>/.
    Returns list of (filename, storage_path) tuples for saved files.
    """
    validate_upload(code_file, "main.py")

    storage_dir = _storage_dir(user_id, function_id)
    storage_dir.mkdir(parents=True, exist_ok=True)

    saved: list[tuple[str, str]] = []

    for upload, target_name in [(code_file, "main.py"), (requirements_file, "requirements.txt")]:
        if upload is None:
            continue
        content = await upload.read()
        if len(content) > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"'{target_name}' exceeds the 10MB size limit",
            )
        dest = storage_dir / target_name
        dest.write_bytes(content)
        saved.append((target_name, str(dest)))

    return saved


def delete_function_files(user_id: int, function_id: int) -> None:
    import shutil
    storage_dir = _storage_dir(user_id, function_id)
    if storage_dir.exists():
        shutil.rmtree(storage_dir)


def get_function_path(user_id: int, function_id: int) -> Path:
    return _storage_dir(user_id, function_id)
