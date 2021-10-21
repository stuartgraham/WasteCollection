import pandas as pd
import os
import boto3

MESSAGE_SIZE = 400

def write_to_sqs(payload, csv):
    print("PUBLISHSQS: Pubish message to SQS")
    sqs = boto3.client('sqs')
    queue_url = os.environ['SQS_URL']
    response = sqs.send_message(
        QueueUrl=queue_url,
        DelaySeconds=10,
        MessageAttributes={
            'csv': {
                'DataType': 'String',
                'StringValue': csv
            }
        },
        MessageBody=(str(payload))
    )

def csv_to_sqs(csv):
    df = pd.read_csv('refdata/' + csv)
    for i in range(0, len(df.index), MESSAGE_SIZE):
        batch = df.loc[i:i+MESSAGE_SIZE]
        msg_payload = []
        for _, row in batch.iterrows():
            postcode = row["postcode"]
            lat = row["latitude"]
            lon = row["longitude"]
            msg_payload.append({'postcode' : postcode, 'lon': lon, 'lat': lat})
        print(f"SQSMESSAGE: Sending batch of {MESSAGE_SIZE} starting record {i}")
        write_to_sqs(msg_payload, csv)

def handler(event, context):
    csv_to_sqs('outcodes.csv')
    csv_to_sqs('postcodes.csv')
