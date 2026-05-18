import sys
from pathlib import Path

# Add app to path if needed
sys.path.append(str(Path(__file__).parent))

from app.services.storage_service import StorageService


def cleanup_duplicate_documents():
    storage = StorageService()
    projects = storage.list_projects()

    total_removed = 0
    for proj in projects:
        project_id = proj.ProjectID
        try:
            metadata = storage.get_project(project_id)
        except Exception as e:
            print(f"Skipping project {project_id}: {e}")
            continue

        seen_filenames = set()
        unique_docs = []
        duplicate_docs = []

        for doc in metadata.Documents:
            fname_key = doc.FileName.lower().strip()
            if fname_key in seen_filenames:
                duplicate_docs.append(doc)
            else:
                seen_filenames.add(fname_key)
                unique_docs.append(doc)

        if duplicate_docs:
            print(
                f"\nCleaning project {project_id} ({metadata.ProjectName}): found {len(duplicate_docs)} duplicates."
            )
            for d in duplicate_docs:
                print(f"  Removing duplicate: {d.FileName} (ID: {d.DocumentID})")
                try:
                    storage.delete_document(project_id, d.DocumentID)
                    total_removed += 1
                except Exception as e:
                    print(f"  Error deleting files for {d.DocumentID}: {e}")

            # Ensure metadata reflects unique docs precisely
            metadata.Documents = unique_docs
            metadata.LastUpdatedOn = storage.now()
            storage._write_metadata(metadata)

    print(
        f"\nCleanup complete. Total duplicate documents removed across all projects: {total_removed}"
    )


if __name__ == "__main__":
    cleanup_duplicate_documents()
