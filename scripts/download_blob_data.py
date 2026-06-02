import os
from pathlib import Path

from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

# ======================================================
# Azure Blob Download für Netzentgelt MVP
# Lädt nur die relevanten MVP-Dateien
# ====================================================== 

load_dotenv()

ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

if not all([ACCOUNT_NAME, ACCOUNT_KEY, CONTAINER_NAME]):
    raise RuntimeError(
        "Azure-Storage-Konfiguration fehlt. Bitte die lokale .env-Datei prüfen."
    )

# Zielordner im MVP-Projekt
DOWNLOAD_DIR = Path("data/00_raw")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Nur diese Dateien werden heruntergeladen
WANTED_FILES = {
    "locomotivemovement.csv",
    "locomotiveusage.csv",
    "transportdetail.csv",
    "locomotive.csv",
}

account_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net"

blob_service_client = BlobServiceClient(
    account_url=account_url,
    credential=ACCOUNT_KEY
)

container_client = blob_service_client.get_container_client(CONTAINER_NAME)

print(f"Verbunden mit Storage Account: {ACCOUNT_NAME}")
print(f"Container: {CONTAINER_NAME}")
print(f"Download-Ziel: {DOWNLOAD_DIR.resolve()}")
print("-" * 80)

found = []
downloaded = []
skipped = []

for blob in container_client.list_blobs():
    blob_name = blob.name

    # Falls Dateien in Unterordnern liegen, nur Dateiname prüfen
    file_name = Path(blob_name).name.lower()

    if file_name not in WANTED_FILES:
        skipped.append(blob_name)
        continue

    found.append(blob_name)

    local_path = DOWNLOAD_DIR / Path(blob_name).name
    local_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Lade: {blob_name} -> {local_path}")

    blob_client = container_client.get_blob_client(blob_name)

    with open(local_path, "wb") as file:
        stream = blob_client.download_blob()
        file.write(stream.readall())

    downloaded.append(blob_name)

print("-" * 80)
print(f"Gefunden: {len(found)} relevante Datei(en)")
print(f"Heruntergeladen: {len(downloaded)} Datei(en)")
print(f"Übersprungen: {len(skipped)} Datei(en)")
print(f"Ablage: {DOWNLOAD_DIR.resolve()}")

missing = WANTED_FILES - {Path(x).name.lower() for x in found}

if missing:
    print("-" * 80)
    print("WARNUNG: Diese erwarteten Dateien wurden nicht gefunden:")
    for item in sorted(missing):
        print(f" - {item}")

print("-" * 80)
print("Fertig.")