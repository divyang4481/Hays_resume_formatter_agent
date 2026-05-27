import argparse
import zipfile
from pathlib import Path
import json

def extract_xml(docx_path: Path, output_dir: Path) -> None:
    """Extract the main document XML from a DOCX file.

    DOCX files are zip archives containing a collection of XML parts.
    The primary document content lives in ``word/document.xml``.
    This function extracts that XML and writes it to ``output_dir`` with a
    ``_document.xml`` suffix.
    """
    if not docx_path.is_file():
        raise FileNotFoundError(f"DOCX file not found: {docx_path}")

    with zipfile.ZipFile(docx_path, "r") as zip_ref:
        try:
            xml_bytes = zip_ref.read("word/document.xml")
        except KeyError as e:
            raise KeyError(f"'{docx_path}' does not contain 'word/document.xml'") from e

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{docx_path.stem}_document.xml"
    out_file.write_bytes(xml_bytes)
    print(f"[INFO] Extracted XML saved to: {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Extract the main document XML from a DOCX file.")
    parser.add_argument("docx", type=Path, help="Path to the source .docx file")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("SampleData/output"),
        help="Directory to write the extracted XML (default: ./local_store)",
    )
    args = parser.parse_args()

    # Handle escaped spaces (e.g., "UK\ Worldwide\ London.docx")
    docx_path = args.docx
    if isinstance(docx_path, Path):
        path_str = str(docx_path)
        # Replace escaped spaces ("\ ") with actual spaces
        path_str = path_str.replace("\\ ", " ")
        docx_path = Path(path_str)
    else:
        docx_path = Path(str(docx_path).replace("\\ ", " "))

    try:
        extract_xml(docx_path, args.out_dir)
    except FileNotFoundError as e:
        print(e)
        # Show available DOCX files in the templates folder for guidance
        tmpl_dir = Path("SampleData/templates")
        print("Available DOCX files in templates:")
        for p in tmpl_dir.glob("*.docx"):
            print(f"  - {p.name}")
        raise


if __name__ == "__main__":
    main()
