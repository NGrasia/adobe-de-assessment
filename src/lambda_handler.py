#!/usr/bin/env python3

"""
Lambda entry point — triggered by EventBridge on S3 ObjectCreated.

Event shape expected:
  event["detail"]["bucket"]["name"]
  event["detail"]["object"]["key"]
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
    log.info("Event received: %s", event)

    # EventBridge puts bucket/key under detail — not under Records like the old S3 trigger
    try:
        detail  = event["detail"]
        input_bucket = detail["bucket"]["name"]
        input_key    = detail["object"]["key"]
    except KeyError as exc:
        log.error("Unexpected event shape, missing: %s — full event: %s", exc, event)
        raise

    log.info("Processing s3://%s/%s", input_bucket, input_key)

    with tempfile.TemporaryDirectory() as tmp:
        local_file = os.path.join(tmp, "input.tab")

        s3.download_file(input_bucket, input_key, local_file)

        parser  = HitDataParser(local_file)
        results = parser.process()

        # tried writing straight to /tmp root first — ran into permission issues on some runtimes
        # tempfile.TemporaryDirectory() is cleaner
        writer   = ReportWriter()
        out_file = writer.write(results, output_dir=tmp)

        out_key = os.path.basename(out_file)
        s3.upload_file(out_file, OUTPUT_BUCKET, out_key)
        log.info("Uploaded -> s3://%s/%s", OUTPUT_BUCKET, out_key)

    return {
        "statusCode"     : 200,
        "input_key"      : input_key,
        "rows_processed" : len(results),
        "output_key"     : out_key,
    }