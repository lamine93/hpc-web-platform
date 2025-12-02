import os
import logging

# Assurez-vous d'initialiser le logger ici ou de l'importer si vous utilisez un système de logger central
logger = logging.getLogger(__name__) 

def get_jwt() -> str:
    """
    Retrieves the Slurm JWT token from environment variables or a file.
    """
    path = os.getenv("SLURM_JWT_FILE")
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except IOError as e:
            logger.error(f"Failed to read JWT file at {path}: {e}")
            pass

    return (os.getenv("SLURMRESTD_TOKEN") or os.getenv("SLURM_JWT") or "").strip()