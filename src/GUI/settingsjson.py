import json


settings_json = json.dumps(
    [
        {"type": "title", "title": "Settings WitnessWard"},
        {
            "type": "string",
            "title": "URL IP camera",
            "desc": "Path description text",
            "section": "example",
            "key": "urlcamera",
        },
        {
            "type": "numeric",
            "title": "number of escrow",
            "desc": "the number of people with a USB key",
            "section": "example",
            "key": "number_escrow",
        },
        {
            "type": "numeric",
            "title": "Minimum number of shares",
            "desc": "minimum number of people to collect their USB key",
            "section": "example",
            "key": "min_number_shares",
        },
        {
            "type": "numeric",
            "title": "Retention time",
            "desc": "number of days, videos ( containers)  would be saved in the system",
            "section": "example",
            "key": "retention_days",
        },
        {
            "type": "string",
            "title": "Recording directory",
            "desc": "the absolute path to the directory where the videos will be saved",
            "section": "example",
            "key": "recordingdirectory",
        },
    ]
)
