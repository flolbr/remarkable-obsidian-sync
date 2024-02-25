import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

IMPORT_TAG = 'Obsidian/Import'
REMARKABLE_DIRECTORY = os.getenv('REMARKABLE_DIRECTORY', 'app/remarkables')
VAULT_DIRECTORY = os.getenv('VAULT_DIRECTORY', 'app/vault')
VAULT_NAME = os.getenv('VAULT_NAME', 'MyVault')
INGEST_DIRECTORY = os.getenv('INGEST_DIRECTORY', '99 - Ingest')
TEMPLATE_DIRECTORY = os.getenv('TEMPLATE_DIRECTORY', '91 - Templates')
OVERWRITE = os.getenv('OVERWRITE', 'False').lower() in ['true', '1', 't', 'y', 'yes']
IMPORT_ALL = os.getenv('IMPORT_ALL', 'False').lower() in ['true', '1', 't', 'y', 'yes']

template_directory = Path(f"{VAULT_DIRECTORY}/{TEMPLATE_DIRECTORY}")
available_templates = set(x.stem for x in template_directory.glob('*.md'))
