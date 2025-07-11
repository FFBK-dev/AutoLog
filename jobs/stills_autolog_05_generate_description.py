# jobs/stills_autolog_05_generate_description.py
import sys, os, json, base64
from pathlib import Path
import openai
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "metadata": "INFO_Metadata",
    "user_prompt": "AI_Prompt",
    "description": "INFO_Description",
    "date": "INFO_Date",
    "server_path": "SPECS_Filepath_Server",
    "globals_api_key": "SystemGlobals_AutoLog_OpenAI_API_Key"
}

def load_prompts():
    prompts_path = Path(__file__).resolve().parent.parent / "prompts.json"
    with open(prompts_path, 'r') as f:
        return json.load(f)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    stills_id = sys.argv[1]
    token = config.get_token()
    
    try:
        system_globals = config.get_system_globals(token)
        api_key = system_globals.get(FIELD_MAPPING["globals_api_key"])
        if not api_key: raise ValueError("OpenAI API Key not found in SystemGlobals.")
        openai.api_key = api_key

        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        
        metadata_from_fm = record_data.get(FIELD_MAPPING["metadata"], '')
        user_prompt = record_data.get(FIELD_MAPPING["user_prompt"], '')
        server_path = record_data.get(FIELD_MAPPING["server_path"], '')
        existing_description = record_data.get(FIELD_MAPPING["description"], '')

        # Check if image file exists
        if not server_path or not os.path.exists(server_path):
            raise ValueError(f"Image file not found at: {server_path}")

        # Read and encode the image
        with open(server_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Load and format the prompt
        prompts = load_prompts()
        prompt_template = prompts["stills_ai_description"]
        
        # Format the prompt with dynamic fields
        prompt_text = prompt_template.format(
            AI_Prompt=user_prompt if user_prompt else "",
            INFO_Metadata=metadata_from_fm if metadata_from_fm else "",
            INFO_Description=existing_description if existing_description else ""
        )

        # Create the message with image
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ]
        
        response = openai.chat.completions.create(
            model="gpt-4o", 
            messages=messages, 
            response_format={"type": "json_object"}
        )
        content = json.loads(response.choices[0].message.content)
        
        print(f"DEBUG: OpenAI response content: {content}")
        
        update_data = {
            FIELD_MAPPING["description"]: content.get("description") or content.get("Description", "Error: No description returned."),
            FIELD_MAPPING["date"]: content.get("date") or content.get("Date", "")
        }
        
        print(f"DEBUG: Update data: {update_data}")
        
        config.update_record(token, "Stills", record_id, update_data)
        print(f"SUCCESS [generate_description]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        sys.stderr.write(f"ERROR [generate_description] on {stills_id}: {e}\n")
        sys.exit(1)