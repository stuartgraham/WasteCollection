from dataclasses import dataclass, field
from random import uniform, randint
from decimal import Decimal
from datetime import datetime, timedelta, time
import boto3
import json
import secrets
import paho.mqtt.client as paho
import os
import ssl
from pprint import pprint
from time import sleep

TRUCK_QUANTITY = {"glasgow" : 41, "edinburgh": 32, "dundee" : 20, "aberdeen" : 20, "inverness" : 20}

@dataclass
class Waste:

    def get_waste(self):
        return float(format(Decimal(uniform(0.1, 15)), '.2f'))


@dataclass
class TruckInventory:
    city_name : str
    inventory : dict = field(default_factory=dict)

    def __post_init__(self):
        self.inventory = self.get_inventory()

    def get_inventory(self):
        inventories = {}
        for city, volume in TRUCK_QUANTITY.items():
            id_list = []
            unique_id = 0
            for _ in range(0, volume):
                unique_id += 1
                id_list.append({"id" : city[0:3] + str(unique_id).zfill(4)})
            inventories.update({city : id_list})

        return inventories[self.city_name]


@dataclass
class City:
    name : str
    boundary : dict = field(default_factory=dict)

    def __post_init__(self):
        self.boundary = self.get_boundary()

    def get_boundary(self):
        boundaries =  {"glasgow": {"lat": {"min" : 55.800818, "max" : 55.905653},
            "lon": {"min" : -4.457350 , "max" : -4.118427}},
            "edinburgh": {"lat": {"min" : 55.897569, "max" : 55.973145},
            "lon": {"min" : -3.306988 , "max" : -3.091925}},
            "aberdeen": {"lat": {"min" : 57.127780, "max" : 57.174114},
            "lon": {"min" : -2.167156 , "max" : -2.088483}},
            "inverness": {"lat": {"min" : 57.453927, "max" : 57.489870},
            "lon": {"min" : -4.250410 , "max" : -4.195785}},
            "dundee": {"lat": {"min" : 56.456193, "max" : 56.481492},
            "lon": {"min" : -3.049765 , "max" : -2.974970}}}
        return boundaries[self.name]

    def get_random_boundary_position(self):
        return [round(uniform(self.boundary["lat"]["min"], self.boundary["lat"]["max"]),6),
                round(uniform(self.boundary["lon"]["min"], self.boundary["lon"]["max"]),6)]


@dataclass
class BinTruck:
    id : str
    boundary : City
    position : list = field(default_factory=list)

    def __post_init__(self):
        self.position = self.boundary.get_random_boundary_position()

    def move_down_road(self):
        self.position = self.boundary.get_random_boundary_position()


@dataclass
class TimeSlot:
    time_slot : datetime = datetime(2018, 12, 31, 0, 0)
    work_day_start = time(hour=0, minute=1)
    work_day_end = time(hour=23, minute=59)

    def increment_time_slot(self):
        if self.work_day_start <= self.time_slot.time() < self.work_day_end:
            self.time_slot = self.time_slot + timedelta(minutes=1)
        else:
            self.time_slot = datetime.combine(self.time_slot.date(), self.work_day_start)
            self.time_slot = self.time_slot + timedelta(days=1)

    def time_to_ms(self, dt):
        return int(dt.timestamp()*1000)


@dataclass
class MqttMessage:
    topic : str = "/"
    payload : dict = field(default_factory=dict)

    def send(self, truck, time_slot, waste, weighting):
        self.topic = f"waste/household/{truck.id}/collection"
        self.payload = {}
        self.payload.update({"timestamp" : time_slot.time_to_ms(time_slot.time_slot)})
        self.payload.update({"truck_id" : truck.id})
        self.payload.update({"lat" : truck.position[0]})
        self.payload.update({"lon" : truck.position[1]})
        self.payload.update({"load" : waste.get_waste() * weighting})
        self.send_to_aws_iot()

    def send_to_aws_iot(self):
        print("MQTTSTATUS: Settings MQTT variables")
        ENDPOINT = "a4nbpn9s9e1mr-ats.iot.eu-west-1.amazonaws.com"
        CLIENT_ID = "WasteCollectionIngest-" + secrets.token_hex(6)
        PATH_TO_CERT = "/tmp/1e6a88bcb8-certificate.pem.crt"
        PATH_TO_KEY = "/tmp/1e6a88bcb8-private.pem.key"
        PATH_TO_ROOT = "/tmp/AmazonRootCA1.pem"
        MESSAGE = self.payload
        TOPIC = self.topic

        def on_message(clients, userdata, message):
                print("message received " ,str(message.payload.decode("utf-8")))
                print("message topic=",message.topic)
                print("message qos=",message.qos)
                print("message retain flag=",message.retain)

        def on_log(client,userdata,level,buff):
            print(buff)

        print("MQTTSTATUS: Instantiate MQTT Client")
        mqttc = paho.Client(CLIENT_ID)
        mqttc.tls_set(PATH_TO_ROOT,
            certfile=PATH_TO_CERT,
            keyfile=PATH_TO_KEY,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2,
            ciphers=None
            )


        print(TOPIC)
        print(json.dumps(MESSAGE))
        mqttc.on_message = on_message
        mqttc.on_log = on_log

        print("MQTTSTATUS: Connecting to MQTT Broker")
        mqttc.connect(ENDPOINT, 8883, keepalive=10)
        mqttc.loop_start()
        mqttc.subscribe(TOPIC)
        mqttc.publish(TOPIC, json.dumps(MESSAGE), qos=0)
        sleep(0.4)
        mqttc.loop_stop()


@dataclass
class Application:
    historical_begin_time : str = "2018-12-31T00:00:00"
    historical_end_time : str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    weighting : float = 1.0

    def __post_init__(self):
        self.collection_process()
        self.init_certs()


    def collection_process(self):
        CITY_LABELS = ["glasgow", "edinburgh", "dundee", "inverness", "aberdeen"]

        self.cities = []
        for city in CITY_LABELS:
            locals()[city] = City(city)
            self.cities.append(locals()[city])

        self.trucks = []
        for city in self.cities:
            city_inventory = TruckInventory(city.name)
            for truck in city_inventory.inventory:
                self.trucks.append(BinTruck(truck["id"], city))


    def init_certs(self):
        BUCKET_NAME = os.environ.get('KEYS_BUCKET', 'no-bucket')
        OBJECTS_ = ["1e6a88bcb8-certificate.pem.crt",
            "1e6a88bcb8-private.pem.key",
            "AmazonRootCA1.pem"
        ]

        s3 = boto3.resource('s3')
        for object_ in OBJECTS_:
            try:
                s3.Bucket(BUCKET_NAME).download_file(object_, "/tmp/" + object_)
            except:
                print("COPYFILE: Could not copy file from S3")


            if os.path.isfile("/tmp/" + object_):
                print(f"CHECKFILE: {object_} exists")
            else:
                print(f"CHECKFILE: {object_} doesnt exist")


    def process_live(self):
        waste = Waste()
        time_slot = TimeSlot(datetime.now())
        if time_slot.work_day_start <= time_slot.time_slot.time() < time_slot.work_day_end:
            for truck in self.trucks:
                truck.move_down_road()
                mqtt_message = MqttMessage()
                mqtt_message.send(truck, time_slot, waste, self.weighting)
                del mqtt_message


    def process_historical(self):
        ts = datetime.strptime(self.historical_begin_time, "%Y-%m-%dT%H:%M:%S")
        historical_slot =  TimeSlot(ts)
        end_time = datetime.strptime(self.historical_end_time, "%Y-%m-%dT%H:%M:%S")
        waste = Waste()

        def send_sqs(time_slot, payloads):
            print("PUBLISHSQS: Pubish message to SQS")
            sqs = boto3.client('sqs')
            queue_url = os.environ['SQS_URL']
            message_id = None
            while message_id is None:
                result = sqs.send_message(
                    QueueUrl=queue_url,
                    DelaySeconds=10,
                    MessageAttributes={
                        'timeslot': {
                            'DataType': 'String',
                            'StringValue': time_slot.isoformat()
                        }
                    },
                    MessageBody=(payloads)
                )
                message_id = result['MessageId']
                print(f"SENTSQS: Messsage received as MessageID: {message_id}")


        def do_work(timestamp):
            payloads : str = ""
            for truck in self.trucks:
                truck.move_down_road()
                payload = {}
                payload.update({"timestamp" : timestamp})
                payload.update({"truck_id" : truck.id})
                payload.update({"lat" : truck.position[0]})
                payload.update({"lon" : truck.position[1]})
                payload.update({"load" : waste.get_waste() * self.weighting})
                payloads = payloads + (json.dumps(payload)) + ","
            send_sqs(historical_slot.time_slot, payloads)


        while end_time - timedelta(minutes=1) > historical_slot.time_slot :
            historical_slot.increment_time_slot()
            timestamp = historical_slot.time_to_ms(historical_slot.time_slot)
            do_work(timestamp)


# Lambda handler
def handler(event, context):
    if "detail-type" and "source" in event:
        if event["detail-type"] == "Scheduled Event" and event["source"] == "aws.events":
            print("PROCESS: Processing live data")
            app = Application()
            app.process_live()

    if "historical-process" in event:
        if event["historical-process"] == True:
            print("PROCESS: Processing historical data")
            if "timeslot" in event:
                app = Application(event["timeslot"], event["endtime"])
                app.process_historical()
            else:
                app.process_historical()


# Non Lambda Execution
def main():
    event = { "historical-process" : True, 
                "timeslot" : "2020-12-31T20:00:00",
                "endtime" :  "2021-10-19T17:31:00",
                "weighting" : 0.9}
    handler(event, "")


if __name__ == "__main__":
    main()
