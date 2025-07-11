# jobs/stills_autolog_01_get_file_info.py
import sys, os, subprocess
from pathlib import Path
from PIL import Image
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "import_path": "SPECS_Filepath_Import",
    "dimensions": "SPECS_File_Dimensions",
    "size": "SPECS_File_Size",
    "source": "INFO_Source",
    "thumbnail": "SPECS_Thumbnail"
}

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        import_path = record_data[FIELD_MAPPING["import_path"]]

        img = Image.open(import_path)
        dimensions = f"{img.width}x{img.height}"
        file_size_mb = f"{os.path.getsize(import_path) / (1024*1024):.2f} Mb"
        
        # Extract archive name from path after "2 By Archive/"
        path_parts = Path(import_path).parts
        try:
            archive_index = path_parts.index("2 By Archive")
            if archive_index + 1 < len(path_parts):
                source = path_parts[archive_index + 1]
            else:
                source = "Unknown Archive"
        except ValueError:
            source = "Unknown Archive"

        thumb_path = f"/tmp/thumb_{stills_id}.jpg"
        subprocess.run(['magick', import_path, '-resize', '588x588>', thumb_path], check=True)
        
        # Upload thumbnail using config function
        config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], thumb_path)
        os.remove(thumb_path)
        
        field_data = {
            FIELD_MAPPING["dimensions"]: dimensions,
            FIELD_MAPPING["size"]: file_size_mb,
            FIELD_MAPPING["source"]: source
        }
        
        config.update_record(token, "Stills", record_id, field_data)
        print(f"SUCCESS [get_file_info]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        sys.stderr.write(f"ERROR [get_file_info] on {stills_id}: {e}\n")
        sys.exit(1)