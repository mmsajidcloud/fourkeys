# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import os
import json

import shared

from flask import Flask, request

app = Flask(__name__)


@app.route("/", methods=["POST"])
def index():
    """
    Receives messages from a push subscription from Pub/Sub.
    Parses the message, and inserts it into BigQuery.
    """
    event = None
    # Check request for JSON
    if not request.is_json:
        raise Exception("Expecting JSON payload")
    envelope = request.get_json()

    # Check that message is a valid pub/sub message
    if "message" not in envelope:
        raise Exception("Not a valid Pub/Sub Message")
    msg = envelope["message"]

    if "attributes" not in msg:
        raise Exception("Missing pubsub attributes")

    try:
        attr = msg["attributes"]

        # Header Event info
        if "headers" in attr:
            headers = json.loads(attr["headers"])

            # Process Gitlab Events
            if "X-Gitlab-Event" in headers:
                event = process_gitlab_event(headers, msg)

        shared.insert_row_into_bigquery(event)

    except Exception as e:
        entry = {
                "severity": "WARNING",
                "msg": "Data not saved to BigQuery",
                "errors": str(e),
                "json_payload": envelope
            }
        print(json.dumps(entry))

    return "", 204


def process_gitlab_event(headers, msg):
    # Unique hash for the event
    signature = shared.create_unique_id(msg)
    source = "gitlab"

    if "Mock" in headers:
        source += "mock"

    types = {"push", "merge_request", "note", "tag_push", "issue", "pipeline", "job"}

    metadata = json.loads(base64.b64decode(msg["data"]).decode("utf-8").strip())

    event_type = metadata["object_kind"]

    if event_type not in types:
        raise Exception("Unsupported Gitlab event: '%s'" % event_type)

    if event_type in ("push", "tag_push"):
        e_id = metadata["checkout_sha"]
        for commit in metadata["commits"]:
            if commit["id"] == e_id:
                time_created = commit["timestamp"]

    if event_type in ("merge_request", "note", "issue", "pipeline"):
        event_object = metadata["object_attributes"]
        e_id = event_object["id"]
        time_created = (
            event_object.get("updated_at") or
            event_object.get("finished_at") or
            event_object.get("created_at"))

    if event_type in ("job"):
        e_id = metadata["build_id"]
        time_created = (
            event_object.get("finished_at") or
            event_object.get("started_at"))

    gitlab_event = {
        "event_type": event_type,
        "id": e_id,
        "metadata": json.dumps(metadata),
        # If time_created not supplied by event, default to pub/sub publishTime
        "time_created": time_created or msg["publishTime"],
        "signature": signature,
        "msg_id": msg["message_id"],
        "source": source,
    }

    return gitlab_event


if __name__ == "__main__":
    PORT = int(os.getenv("PORT")) if os.getenv("PORT") else 8080

    # This is used when running locally. Gunicorn is used to run the
    # application on Cloud Run. See entrypoint in Dockerfile.
    app.run(host="127.0.0.1", port=PORT, debug=True)
