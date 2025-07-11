# jobs/stills_autolog_01_get_file_info.py
import sys, os, subprocess
from pathlib import Path
from PIL import Image
import requests
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
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        r = requests.get(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token))
        r.raise_for_status()
        import_path = r.json()['response']['data'][0]['fieldData'][FIELD_MAPPING["import_path"]]

        img = Image.open(import_path)
        dimensions = f"{img.width}x{img.height}"
        file_size_mb = f"{os.path.getsize(import_path) / (1024*1024):.2f} Mb"
        source = Path(import_path).parent.name

        thumb_path = f"/tmp/thumb_{stills_id}.jpg"
        subprocess.run(['magick', import_path, '-resize', '588x588>', thumb_path], check=True)
        with open(thumb_path, 'rb') as f:
            container_url = f"layouts/Stills/records/{record_id}/containers/{FIELD_MAPPING['thumbnail']}/1"
            requests.post(config.url(container_url), headers={"Authorization": f"Bearer {token}"}, files={'upload': f})
        os.remove(thumb_path)
        
        field_data = {
            FIELD_MAPPING["dimensions"]: dimensions,
            FIELD_MAPPING["size"]: file_size_mb,
            FIELD_MAPPING["source"]: source
        }
        
        requests.patch(config.url(f"layouts/Stills/records/{record_id}"), headers=config.api_headers(token), json={"fieldData": field_data}).raise_for_status()
        print(f"SUCCESS [get_file_info]: {stills_id}")
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"ERROR [get_file_info] on {stills_id}: {e}\n")
        sys.exit(1)