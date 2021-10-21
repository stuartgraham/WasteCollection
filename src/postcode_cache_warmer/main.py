import redis
import os
import json

endpoint : str = os.environ.get('REDIS_ENDPOINT')
port : int = os.environ.get('REDIS_PORT')

try:
    conn = redis.Redis(
        host=endpoint,
        port=port,
        db=2,
        charset="utf-8",
        decode_responses=True)
    print(conn)
    conn.ping()
    print('Connected')
    redis_ = conn
except Exception as ex:
    print(f"Error: {ex}")
    exit("Failed to connect, terminating")


def write_to_elasticache(lon, lat, postcode, csv, redis_):
    if csv == 'outcodes.csv':
        redis_.geoadd("outcodes", lon, lat, postcode)

    if csv == 'postcodes.csv':
        redis_.geoadd("postcodes", lon, lat, postcode)


def handler(event, context):
    if event["Records"][0]["eventSource"] == "aws:sqs":
        print("SQSEVENT : New message notification")
        message_body = event["Records"][0]["body"]
        message_body = message_body.replace("\'", "\"")
        message_body = json.loads(message_body)
        csv = event["Records"][0]["messageAttributes"]["csv"]["stringValue"]
        
        for i in message_body:
            print(f"WRITECACHE: Writing {i['postcode']} from {csv}")
            write_to_elasticache(i['lon'], i['lat'], i['postcode'], csv, redis_)
