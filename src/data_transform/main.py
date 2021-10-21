from dataclasses import dataclass, field
import boto3
import json as json
import os
import redis
import secrets
from operator import itemgetter
import pandas as pd


@dataclass
class CodeDB:

    def __post_init__(self):
        self.connect_redis()

    def connect_redis(self):
        endpoint : str = os.environ.get('REDIS_ENDPOINT')
        port : int = os.environ.get('REDIS_PORT')

        try:
            self.conn = redis.Redis(
                host=endpoint,
                port=port,
                db=2,
                charset="utf-8",
                decode_responses=True)
            self.conn.ping()
            print('Connected to Elasticache')

        except Exception as ex:
            print(f"Error: {ex}")
            exit("Failed to connect, terminating")

    def find_closest_postcode(self, lon, lat):
        postcodes = []
        miles = 1
        while postcodes == [] or miles == 1000:
            postcodes = self.conn.georadius("postcodes", lon, lat, miles, unit="mi", withdist=True)
            miles +=1 
        sorted_postcodes = sorted(postcodes, key=itemgetter(1))
        return sorted_postcodes[0][0]

    
    def find_closest_outcode(self, lon, lat):
        outcodes = []
        miles = 1
        while outcodes == [] or miles == 1000:
            outcodes = self.conn.georadius("outcodes", lon, lat, miles, unit="mi", withdist=True)
            miles +=1 
        sorted_outcodes= sorted(outcodes, key=itemgetter(1))
        return sorted_outcodes[0][0]

    def lookup_postcode(self, postcode):
        return self.conn.geopos("postcodes", postcode)

    def lookup_outcode(self, outcode):
        return self.conn.geopos("outcodes", outcode)


@dataclass
class DataFile:
    bucket : str
    key : str
    file_name : str = ""
    temp_dir : str = "/tmp/"

    def __post_init__(self):
        self.get_file_name()
    
    def get_file_name(self):
        key_list = self.key.split("/")
        self.file_name = key_list[-1]


    def download_from_s3(self):
        s3 = boto3.client('s3')
        self.file_name = secrets.token_hex(6)
        s3.download_file(self.bucket, self.key, self.temp_dir + self.file_name)
        self.key = self.key.split("/")
        # Removes suffix and prefix in original key
        del self.key[-1]
        del self.key[0]
        self.key = "/".join(self.key)
        print(f"WORKINGKEY: {self.key}/{self.file_name}")


    def upload_to_s3(self):
        s3 = boto3.client('s3')
        print(f"UPLOADTOS3: Uploading {self.file_name} to bucket: {self.bucket}, key: processed/{self.key}/{self.file_name}")
        with open(self.temp_dir + self.file_name, "rb") as f:
            s3.upload_fileobj(f, self.bucket, "processed/" + self.key + "/" + self.file_name)


    def transform_to_parquet(self):
        print(f"PARQUETCONVERT: Converting {self.temp_dir + self.file_name}")
        data = pd.read_json(self.temp_dir + self.file_name)
        data.to_parquet(self.temp_dir + self.file_name)



    def transform_to_json(self):
        with open(self.temp_dir + self.file_name, "r") as f:
            data = f.read()
            data = data[:-1]
            data = f'[{data}]'
            json_data = json.loads(data)
        f.close()

        with open(self.temp_dir + self.file_name, "w", encoding="utf-8") as f:
            f.write(json.dumps(json_data, ensure_ascii=False))
        f.close()


    def postcode_enrich_json(self):
        with open(self.temp_dir + self.file_name, "r") as f:
            data = f.read()
            json_data = json.loads(data)
        f.close()
        updated_json = []
        code_db = CodeDB()
        for i in json_data:
            postcode = ""
            outcode = ""
            postcode = code_db.find_closest_postcode(i['lon'], i['lat'])
            print(f"FOUNDPOSTCODE: {postcode}")
            postcode_detail = code_db.lookup_postcode(postcode)

            try:
                postcode_lat = postcode_detail[0][1]
                postcode_lon = postcode_detail[0][0]
            except:
                postcode = "XX99 9ZZ"
                postcode_lat = 56.816918399
                postcode_lon = -4.1826492694

            outcode = postcode.split(" ")
            outcode = outcode[0]
            print(f"FOUNDOUTCODE: ✅ {outcode}")
            outcode_detail = code_db.lookup_outcode(outcode)

            try:
                outcode_lat = outcode_detail[0][1]
                outcode_lon = outcode_detail[0][0]
            except:
                outcode = "XX99"
                outcode_lat = 56.816918399
                outcode_lon = -4.1826492694

            postcode_update = {"postcode" : postcode, "postcode_lat" : postcode_lat, "postcode_lon" : postcode_lon}
            outcode_update = {"outcode" : outcode, "outcode_lat" : outcode_lat, "outcode_lon" : outcode_lon}
            i.update(postcode_update)
            i.update(outcode_update)
            updated_json.append(i)
        
        with open(self.temp_dir + self.file_name, "w", encoding="utf-8") as f:
            f.write(json.dumps(updated_json, ensure_ascii=False))
        f.close()


@dataclass
class Application:
    file_obj : DataFile

    def __post_init__(self):
        self.file_obj.download_from_s3()
        self.file_obj.transform_to_json()
        self.file_obj.postcode_enrich_json()
        self.file_obj.transform_to_parquet()
        self.file_obj.upload_to_s3()


# Lambda handler
def handler(event, context):
    if event["Records"][0]["eventSource"] == "aws:s3":
        print("S3EVENT : New object notification")
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = event["Records"][0]["s3"]["object"]["key"]
        s3_obj = DataFile(bucket, key)
        Application(s3_obj)