from pathlib import Path

from pydantic_settings import BaseSettings

# Koren projekta (oblak/), za default putanje koje ne zavise od cwd-a
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "sqlite:///./oblak.db"
    secret_key: str = "dev-secret-change-in-prod"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    storage_path: str = "./storage"
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10MB

    anthropic_api_key: str = ""

    # Firecracker microVM izvršavanje (dev: svi artefakti u oblak/fc-assets/)
    firecracker_enabled: bool = True
    firecracker_bin: str = "firecracker"  # na PATH-u, ili puna putanja
    # Folder sa 'vmlinux' i 'rootfs.ext4' (kernel/rootfs se izvode iz njega)
    firecracker_assets: str = str(_PROJECT_ROOT / "fc-assets")
    firecracker_vcpu: int = 1
    firecracker_mem_mib: int = 256
    firecracker_exec_timeout: int = 30  # sekundi, guest-side timeout izvršavanja

    class Config:
        env_file = ".env"


settings = Settings()
