"""
AWS Lambda handler.

Triggered by S3 ObjectCreated on the input bucket.
Downloads the .sql file, runs the analyzer, uploads the output to S3.

Environment variables (set in template.yaml / Lambda config):
    OUTPUT_BUCKET  —  name of the S3 bucket for results
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
    Lambda entry point.
    event["Records"][0] contains the S3 trigger details.
    """
    record       = event["Records"][0]
    input_bucket = record["s3"]["bucket"]["name"]
    input_key    = record["s3"]["object"]["key"]
    log.info("Triggered by s3://%s/%s", input_bucket, input_key)

    with tempfile.TemporaryDirectory() as tmp:
        local_input = os.path.join(tmp, "data.sql")

        # Download from S3 to Lambda /tmp
        s3.download_file(input_bucket, input_key, local_input)
        log.info("Downloaded to %s", local_input)

        # Run the same logic as the CLI — no code duplication
        parser  = HitDataParser(local_input)
        results = parser.process()

        writer   = ReportWriter()
        out_file = writer.write(results, output_dir=tmp)

        # Upload result to output bucket
        out_key = os.path.basename(out_file)
        s3.upload_file(out_file, OUTPUT_BUCKET, out_key)
        log.info("Uploaded to s3://%s/%s", OUTPUT_BUCKET, out_key)

    return {
        "statusCode"     : 200,
        "rows_processed" : len(results),
        "output_key"     : out_key,
    }