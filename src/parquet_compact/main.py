import boto3
import pandas as pd
from datetime import datetime
import secrets
import os
import glob

S3_BUCKET = os.environ.get('DATA_BUCKET')
ROOT_KEY = 'processed/'

CURRENT_YEAR = datetime.now().year
CURRENT_MONTH = datetime.now().month
CURRENT_DAY = datetime.now().day

s3 = boto3.client('s3')

def parquet_compaction(keys):
    print("PARQUETCOMPACT: Starting compaction")
    files = []
    for key in keys:
        full_key = key.split("/")
        if full_key[1] == CURRENT_YEAR and full_key[2] == CURRENT_MONTH and full_key[3] == CURRENT_DAY:
            print("PARQUETCOMPACT: todays files, exiting")
            exit()

        file_name = full_key[-1]
        if file_name.endswith(".parquet"):
            continue

        key_path = full_key[:-1]
        key_path = "/".join(key_path)
        files.append(files)
        print("PARQUETCOMPACT: Downloading S3 files")
        s3.download_file(S3_BUCKET, key, "/tmp/" + file_name + ".parquet")

    print("PARQUETCOMPACT: Combining Parquet")
    data = pd.read_parquet("/tmp")

    combined_file = secrets.token_hex(6)
    data.to_parquet("/tmp/" + combined_file)

    with open("/tmp/" + combined_file, "rb") as f:
        s3.upload_fileobj(f, S3_BUCKET, key_path + "/" + combined_file + ".parquet")

    print("PARQUETCOMPACT: Deleting old files")
    for key in keys:
        s3.delete_object(Bucket=S3_BUCKET, Key=key)

    files = glob.glob('/tmp/*')
    for f in files:
        os.remove(f)

    print(f"PARQUETCOMPACT: Finished compaction for {key_path}, exiting")
    exit()

def get_s3_folders():

    def s3_prefix_response(prefix):
        result = s3.list_objects(Bucket=S3_BUCKET, Prefix=prefix, Delimiter='/')
        if 'CommonPrefixes' in result.keys():
            return result['CommonPrefixes']
        else:
            return None 

    l1_prefixes = []
    for i in s3_prefix_response(ROOT_KEY):
        l1_prefixes.append(i['Prefix'])

    l2_prefixes = [] 
    for i in l1_prefixes:
        result = s3_prefix_response(i)
        if result is not None:
            for j in result:
                l2_prefixes.append(j['Prefix'])   

    l3_prefixes = [] 
    for i in l2_prefixes:
        result = s3_prefix_response(i)
        if result is not None:
            for j in result:
                l3_prefixes.append(j['Prefix'])   

    l4_prefixes = [] 
    for i in l3_prefixes:
        result = s3_prefix_response(i)
        if result is not None:
            for j in result:
                l4_prefixes.append(j['Prefix'])   

    def s3_objects_response(prefix):
        result = s3.list_objects(Bucket=S3_BUCKET, Prefix=prefix, Delimiter='/')
        if 'Contents' in result.keys():
            return result['Contents']
        else:
            return None 

    for prefix in l4_prefixes:
        result = s3_objects_response(prefix)
        keys = []
        for i in result:
            keys.append(i['Key'])
        if len(keys) > 1:
            parquet_compaction(keys)


def handler(event, context):
    get_s3_folders()