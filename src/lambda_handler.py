"""
AWS Lambda handler.

Triggered by EventBridge when a .tab or .sql file lands in the input bucket.
EventBridge event shape (NOT the old S3 direct-trigger "Records" format):

{
  "source": "aws.s3",
  "detail-type": "Object Created",
  "detail": {
    "bucket": { "name": "adobe-de-input-123456789" },
    "object": { "key": "data/data.sql" }
  }
}

Environment variables (set in template.yaml):
    OUTPUT_BUCKET  — name of the S3 bucket where results are written
"""

import os
import tempfile
import logging
import boto3

from search_keyword_performance import HitDataParser, ReportWriter

log = logging.getLogger()
log.setLevel(logging.INFO)

s3 = boto3.client("s3")

OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]


def handler(event: dict, context) -> dict:
    """
    Lambda entry point — handles EventBridge S3 ObjectCreated events.

    EventBridge puts bucket and key inside event["detail"],
    not inside event["Records"] like the old S3 direct trigger did.
    """
    log.info("Received event: %s", event)

    # --- parse the EventBridge event -----------------------------------------
    try:
        detail       = event["detail"]
        input_bucket = detail["bucket"]["name"]
        input_key    = detail["object"]["key"]
    except KeyError as exc:
        # Log the full event so we can debug unexpected shapes
        log.error("Unexpected event shape — missing key %s. Full event: %s", exc, event)
        raise

    log.info("Processing s3://%s/%s", input_bucket, input_key)

    # --- download, process, upload -------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        local_input = os.path.join(tmp, "input.tab")

        s3.download_file(input_bucket, input_key, local_input)
        log.info("Downloaded to %s", local_input)

        parser  = HitDataParser(local_input)
        results = parser.process()

        writer   = ReportWriter()
        out_file = writer.write(results, output_dir=tmp)

        out_key = os.path.basename(out_file)
        s3.upload_file(out_file, OUTPUT_BUCKET, out_key)
        log.info("Uploaded result to s3://%s/%s", OUTPUT_BUCKET, out_key)

    return {
        "statusCode"     : 200,
        "input_key"      : input_key,
        "rows_processed" : len(results),
        "output_key"     : out_key,
    }