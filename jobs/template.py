#!/usr/bin/env python3
"""
Generic update template.
"""
__ARGS__ = ["layout", "key_field", "key_value", "update_field", "update_value"]

import sys, os, json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config as cfg

def build_field_data(update_field, update_value):
    return {update_field: update_value}

def main(args):
    if len(args) != 6:
        sys.exit("Usage: template.py <layout> <key_field> <key_value> <update_field> <update_value>")

    _, layout, key_field, key_value, update_field, update_value = args
    tok    = cfg.get_token()
    rec_id = cfg.find_record_id(tok, layout, {key_field: key_value})
    data   = build_field_data(update_field, update_value)

    resp = cfg.update_record(tok, layout, rec_id, data)   # ← capture Response
    if resp.status_code != 200:
        try:
            print("FM reply:", json.dumps(resp.json(), indent=2))
        except ValueError:
            print("FM reply:", resp.text)
        sys.exit(1)                                       # fail fast

    print(f"✅ {layout}: {key_field}={key_value} → {data}")

if __name__ == "__main__":
    main(sys.argv)