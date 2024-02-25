from urllib.parse import urlencode, quote

from ros.remarkable import RemarkableDocument
from ros.utils import get_uuids_to_process
from vars import *


def app(remarkables_directory: Path, vault_directory, overwrite: bool = OVERWRITE):
    def save(name: str, content: str) -> bool:
        directory = vault_directory / INGEST_DIRECTORY
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / f"{name}.md"
        if file_path.exists() and not overwrite:
            print(f"File {file_path} already exists, skipping")
            return False

        with open(file_path, "w", encoding='utf8') as f:
            f.write(content)

            if True:
                md = 'obsidian://open?' + urlencode({
                    'vault': VAULT_NAME,
                    'file': f'{INGEST_DIRECTORY}/{name}.md'
                }, quote_via=quote)
                print(f"Opening {md}")
                os.startfile(f'"{md}"')
        return True

    uuids = get_uuids_to_process(remarkables_directory)

    print(uuids)

    rm_docs = [RemarkableDocument(uuid, remarkables_directory) for uuid in uuids]

    saved = 0

    for rm_doc in rm_docs:
        if rm_doc.name == '.ignore':
            continue
        choice = IMPORT_ALL or input(f'Do you want to process "{rm_doc.name}" ? ([y]/n)\n')
        # choice = True
        if choice == 'n':
            continue
        if IMPORT_TAG in rm_doc.tags:
            print(f"Processing {rm_doc.name}")
            obsidian = rm_doc.to_obsidian()
            print(obsidian)
            if save(rm_doc.name, obsidian):
                rm_doc.replace_tag(IMPORT_TAG, 'Obsidian/Imported')
                saved += 1
        else:
            for page in rm_doc.pages:
                if IMPORT_TAG in page.tags:
                    print(f"Processing {page}")
                    template_tags = list(set(page.tags + rm_doc.parents) & available_templates)
                    if len(template_tags) == 1:
                        obsidian = page.to_obsidian(template_tags[0])
                    else:
                        if len(template_tags) > 1:
                            print(f"Multiple templates found for {page}, not using any template")
                        obsidian = page.to_obsidian()
                        if not obsidian:
                            # print(f"No text found for {page}, skipping")
                            continue
                    print(obsidian)
                    if save(page.name, obsidian):
                        page.replace_tag(IMPORT_TAG, 'Obsidian/Imported')
                        saved += 1

    if saved:
        import psutil

        procname = "reMarkable.exe"  # TODO: make this cross-platform

        for proc in psutil.process_iter():
            # check whether the process name matches
            if proc.name() == procname:
                proc.kill()
                # reopen the app
                os.startfile("C:/Program Files/reMarkable/reMarkable.exe")  # TODO: make this cross-platform

    exit(0)


if __name__ == "__main__":
    app(Path(REMARKABLE_DIRECTORY), Path(VAULT_DIRECTORY))
