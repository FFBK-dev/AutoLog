# jobs/stills_autolog_05_generate_description.py
import sys, os, json
from pathlib import Path
import openai
import requests
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "metadata": "INFO_Metadata",
    "user_prompt": "AI_Prompt",
    "description": "INFO_Description",
    "date": "INFO_Date",
    "globals_api_key": "SystemGlobals_AutoLog_OpenAI_API_Key"
}

def load_prompts():
    # ... (same as before)

def get_system_globals(fm_session):
    # ... (same as before)

if __name__ == "__main__":
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        fm_session = requests.Session()
        fm_session.headers.update(config.api_headers(token))
        
        system_globals = get_system_globals(fm_session)
        api_key = system_globals.get(FIELD_MAPPING["globals_api_key"])
        if not api_key: raise ValueError("OpenAI API Key not found in SystemGlobals.")
        openai.api_key = api_key

        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        r = fm_session.get(config.url(f"layouts/Stills/records/{record_id}"))
        r.raise_for_status()
        field_data_fm = r.json()['response']['data'][0]['fieldData']
        
        metadata_from_fm = field_data_fm.get(FIELD_MAPPING["metadata"], '')
        user_prompt = field_data_fm.get(FIELD_MAPPING["user_prompt"], '')

        prompts = load_prompts()
        system_prompt = prompts.get("stills_description_json", "Error: Prompt not found.")
        
        # ... (prompt construction logic is the same) ...
        
        response = openai.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": final_prompt}], response_format={"type": "json_object"})
        content = json.loads(response.choices[0].message.content)
        
        update_data = {
            FIELD_MAPPING["description"]: content.get("description", "Error: No description returned."),
            FIELD_MAPPING["date"]: content.get("date", "")
        }
        
        fm_session.patch(config.url(f"layouts/Stills/records/{record_id}"), json={"fieldData": update_data}).raise_for_status()
        print(f"SUCCESS [generate_description]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        sys.stderr.write(f"ERROR [generate_description] on {stills_id}: {e}\n")
        sys.exit(1)