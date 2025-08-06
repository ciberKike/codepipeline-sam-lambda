import json
import os
import subprocess
import boto3
import tempfile
from transcoder import process_file

s3 = boto3.client("s3")


def lambda_handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        s3_bucket = body["s3_bucket"]
        s3_key = body["s3_key"]
        output_prefix = body.get("output_prefix", "output/")
        height = body.get("height", 100)
        format = body.get("format", "50")

        filename = os.path.basename(s3_key)
        with tempfile.TemporaryDirectory() as tmpdir:
            local_input = os.path.join(tmpdir, filename)
            local_output_dir = os.path.join(tmpdir, "transcoded_files")

            # Download file
            s3.download_file(s3_bucket, s3_key, local_input)

            # Exec transcode
            process_file(local_input, int(height), local_output_dir, str(format))

            # Upload result
            for root, _, files in os.walk(local_output_dir):
                for f in files:
                    local_out = os.path.join(root, f)
                    rel_path = os.path.relpath(local_out, local_output_dir)
                    output_key = os.path.join(output_prefix, rel_path)
                    s3.upload_file(local_out, s3_bucket, output_key)

    return {"statusCode": 200}
