import boto3
import secrets
import os
import datetime
import uuid

def write_to_s3(message, time_slot):

    file_path = "/tmp/" + secrets.token_hex(6)
    with open(file_path,'w') as f:
        f.write(message)
    f.close()

    ts = datetime.datetime.strptime(time_slot, "%Y-%m-%dT%H:%M:%S")
    ts_str = ts.strftime("%Y-%m-%d-%H-%M-%S")
    uuid_str = uuid.uuid4()
    s3_file = f"WasteCollectionDeliveryStream-1-{ts_str}-{uuid_str}"
    ts_str = ts.strftime("%Y/%m/%d/%H/")
    s3_key = f"{ts_str}"
    print(s3_key + s3_file)

    s3_bucket = os.environ.get('DATA_BUCKET', 'no-bucket')

    def upload_to_s3(s3_bucket, s3_key, file_path):
        s3 = boto3.client('s3')
        with open(file_path, "rb") as f:
            s3.upload_fileobj(f, s3_bucket, "raw/" + s3_key + s3_file)
        os.remove(file_path)

    upload_to_s3(s3_bucket, s3_key, file_path)

# Lambda handler
def handler(event, context):
    if event["Records"][0]["eventSource"] == "aws:sqs":
        print("SQSEVENT : New message notification")
        message_body = event["Records"][0]["body"]
        time_slot = event["Records"][0]["messageAttributes"]["timeslot"]["stringValue"]
        write_to_s3(message_body, time_slot)