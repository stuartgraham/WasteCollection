from attr import attrib, s
from aws_cdk import (
    core as cdk,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_ssm as ssm,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
    aws_iot as iot,
    aws_s3 as s3,
    aws_kinesisfirehose_destinations as destinations,
    aws_kinesisfirehose as firehose,
    aws_lambda_event_sources as _lambda_event_sources,
    aws_sqs as sqs,
    aws_glue as glue,
    aws_elasticache as elasticache,
    aws_ec2 as ec2, 
    aws_s3_deployment as s3_deploy,
    aws_quicksight as quicksight,
    aws_cloudwatch as cloudwatch,
    aws_sns as sns,
    aws_cloudwatch_actions as cw_actions
)
from os import name, path


class WasteCollectionStage(cdk.Stage):
    def __init__(self, scope: cdk.Construct, id: str, ecr_repo = None, **kwargs):
        super().__init__(scope, id, **kwargs)
        self.ecr_repo = ecr_repo
        WasteCollectionStack(self, "PoC", ecr_repo = self.ecr_repo)


class WasteCollectionStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, ecr_repo = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # PWD
        this_dir = path.dirname(__file__)


# __      _______   _____ 
# \ \    / /  __ \ / ____|
#  \ \  / /| |__) | |     
#   \ \/ / |  ___/| |     
#    \  /  | |    | |____ 
#     \/   |_|     \_____|

        vpc = ec2.Vpc(self, "WasteCollectionVPC",
            cidr = '10.20.0.0/16',
            subnet_configuration = [
                ec2.SubnetConfiguration(
                    subnet_type = ec2.SubnetType.PRIVATE,
                    name = "Internal",
                    cidr_mask = 24),
                ec2.SubnetConfiguration(
                    subnet_type = ec2.SubnetType.PUBLIC,
                    name = "Public",
                    cidr_mask = 24)
            ]
        )

        private_subnets = vpc.select_subnets(
            subnet_type = ec2.SubnetType.PRIVATE
        )

        private_subnet_selection = ec2.SubnetSelection(subnet_type = ec2.SubnetType.PRIVATE)

        private_subnet_ids = []
        for subnet in private_subnets.subnets:
            private_subnet_ids.append(subnet.subnet_id)

        internal_security_group = ec2.SecurityGroup(self, "WasteCollectionInternalSG",
            vpc = vpc,
            description = "Allow internal traffic only",
            allow_all_outbound = True
        )
        internal_security_group.connections.allow_from(ec2.Peer.ipv4('10.20.0.0/16'), ec2.Port.all_traffic(), 
            "Allow internal traffic only")


#   _____ ____  
#  / ____|___ \ 
# | (___   __) |
#  \___ \ |__ < 
#  ____) |___) |
# |_____/|____/ 

        # S3 Buckets
        keys_bucket = s3.Bucket(self, "WasteCollectionKeys", bucket_name = "stugraha-wastecollection-keys")
        data_bucket = s3.Bucket(self, "WasteCollectionData", 
            bucket_name = "stugraha-wastecollection-data",
            lifecycle_rules = [s3.LifecycleRule(
                enabled = True,
                expiration = cdk.Duration.days(1),
                prefix = "raw/"
            )]
        )

        # Asset upload
        s3_deploy.BucketDeployment(self, "DeployWebsite",
            sources = [s3_deploy.Source.asset("./src/postcode_cache_queuer/refdata/")
            ],
            destination_bucket = data_bucket,
            destination_key_prefix = "reference"
        )


#   _____  ____   _____ 
#  / ____|/ __ \ / ____|
# | (___ | |  | | (___  
#  \___ \| |  | |\___ \ 
#  ____) | |__| |____) |
# |_____/ \___\_\_____/ 

        # SQS Queue
        historical_queue = sqs.Queue(self, "WasteCollectionHistoricalQueue",
            queue_name = "WasteCollectionHistoricalQueue",
            visibility_timeout = cdk.Duration.seconds(1000))

        # SQS Queue
        cache_warmer_queue = sqs.Queue(self, "WasteCollectionCacheWarmerQueue",
            queue_name = "WasteCollectionCacheWarmerQueue",
            visibility_timeout = cdk.Duration.seconds(1000))


#  ______ _           _   _                _          
# |  ____| |         | | (_)              | |         
# | |__  | | __ _ ___| |_ _  ___ __ _  ___| |__   ___ 
# |  __| | |/ _` / __| __| |/ __/ _` |/ __| '_ \ / _ \
# | |____| | (_| \__ \ |_| | (_| (_| | (__| | | |  __/
# |______|_|\__,_|___/\__|_|\___\__,_|\___|_| |_|\___|


        # Subnet Group
        elasticache_subnet_group = elasticache.CfnSubnetGroup(self, "WasteCollectionSubnetGroup",
            description = "MainVPC Private Subnets",
            subnet_ids = private_subnet_ids
        )

        # Cluster
        elasticache_cluster = elasticache.CfnCacheCluster(self, "WasteCollectionElasticache",
            cache_node_type = "cache.m6g.large",
            engine = "redis",
            engine_version="6.x",
            num_cache_nodes = 1,
            auto_minor_version_upgrade = True,
            cache_subnet_group_name = elasticache_subnet_group.ref,
            vpc_security_group_ids = [internal_security_group.security_group_id],
            port = 6379,
        )

        elasticache_endpoint = elasticache_cluster.attr_redis_endpoint_address
        elasticache_port = elasticache_cluster.attr_redis_endpoint_port


#  _                     _         _
# | |                   | |       | |
# | |     __ _ _ __ ___ | |__   __| | __ _
# | |    / _` | '_ ` _ \| '_ \ / _` |/ _` |
# | |___| (_| | | | | | | |_) | (_| | (_| |
# |______\__,_|_| |_| |_|_.__/ \__,_|\__,_|

###################################################################

        # IOT DATA GENERATOR FUNCTION
        ## Param store to track latest build number
        data_generator_latest_image = ssm.StringParameter.from_string_parameter_name(self, "DataGeneratorLatestImage",
            string_parameter_name = "/WasteCollection/DataGenerator/LatestImage").string_value

        ## Function def
        data_generator_lambda = _lambda.DockerImageFunction(self, "WasteCollection-DataGenerator",
            code = _lambda.DockerImageCode.from_ecr(
                repository = ecr_repo[0],
                tag = data_generator_latest_image),
            architectures = [_lambda.Architecture.X86_64],
            function_name = "WasteCollection-DataGenerator",
            log_retention = logs.RetentionDays.ONE_DAY,
            timeout = cdk.Duration.seconds(900),
            memory_size = 512,
            environment = {
                'SQS_URL': historical_queue.queue_url,
                'KEYS_BUCKET': keys_bucket.bucket_name
            },
        )

        ## Grant to S3 buckets for IoT keys
        keys_bucket.grant_read_write(data_generator_lambda)

        ## Grant to ECR for container pull
        data_generator_lambda.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly"))

        ## SQS Grant
        historical_queue.grant_send_messages(data_generator_lambda)

###################################################################

        # IOT HISTORICAL DATA WRITER FUNCTION
        ## Param store to track latest build number
        historical_writer_latest_image = ssm.StringParameter.from_string_parameter_name(self, "HistoricalWriterLatestImage",
            string_parameter_name = "/WasteCollection/HistoricalWriter/LatestImage").string_value

        ## Function
        historical_writer_lambda = _lambda.DockerImageFunction(self, 'WasteCollection-HistoricalWriter',
            code = _lambda.DockerImageCode.from_ecr(
                repository = ecr_repo[4],
                tag = historical_writer_latest_image),
            architectures = [_lambda.Architecture.X86_64],
            timeout = cdk.Duration.seconds(900),
            memory_size = 512,
            environment = {
                'DATA_BUCKET': data_bucket.bucket_name
            },
            function_name = "WasteCollection-HistoricalWriter",
            log_retention = logs.RetentionDays.ONE_DAY
        )


        ## SQS grant
        historical_queue.grant_consume_messages(historical_writer_lambda)

        ## S3 Grant
        data_bucket.grant_read_write(historical_writer_lambda)

        ## SQS Trigger
        historical_writer_lambda.add_event_source(_lambda_event_sources.SqsEventSource(historical_queue, batch_size = 1))

###################################################################

        # POSTCODE ENRICHMENT FUNCTION
        data_transform_latest_image = ssm.StringParameter.from_string_parameter_name(self, "DataTransformLatestImage",
            string_parameter_name = "/WasteCollection/DataTransform/LatestImage").string_value

        ## Function def
        data_transform_lambda = _lambda.DockerImageFunction(self, "WasteCollection-DataTransform",
            code = _lambda.DockerImageCode.from_ecr(
                repository = ecr_repo[1],
                tag = data_transform_latest_image),
            architectures = [_lambda.Architecture.X86_64],
            function_name = "WasteCollection-DataTransform",
            environment = {
                'REDIS_ENDPOINT': elasticache_endpoint,
                'REDIS_PORT' : elasticache_port
            },
            log_retention = logs.RetentionDays.ONE_DAY,
            timeout = cdk.Duration.seconds(900),
            memory_size = 1024,
            vpc_subnets = private_subnet_selection,
            security_group = internal_security_group,
            vpc = vpc
        )

        ## Grant to ECR for container pull
        data_transform_lambda.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly"))

        ## Grant to S3 bucket for IoT data
        data_bucket.grant_read_write(data_transform_lambda)


        ## S3 create object event ot trigger lambda
        data_transform_lambda.add_event_source(_lambda_event_sources.S3EventSource(data_bucket,
            events = [s3.EventType.OBJECT_CREATED], filters = [s3.NotificationKeyFilter(prefix = "raw/")]))

###################################################################

        # POSTCODE CACHE WARMER LAMBDA
        ## Param store to track latest build number
        postcode_cache_warmer_latest_image = ssm.StringParameter.from_string_parameter_name(self, 
            "CacheWarmerLatestImage",
            string_parameter_name = "/WasteCollection/PostcodeCacheWarmer/LatestImage").string_value

        # Lambda - Postcode cache warmer
        postcode_cache_warmer_lambda = _lambda.DockerImageFunction(self, "WasteCollection-PostcodeCacheWarmer",
            code = _lambda.DockerImageCode.from_ecr(
                repository = ecr_repo[2],
                tag = postcode_cache_warmer_latest_image),
            architectures = [_lambda.Architecture.X86_64],
            function_name = "WasteCollection-PostcodeCacheWarmer",
            environment = {
                'REDIS_ENDPOINT': elasticache_endpoint,
                'REDIS_PORT' : elasticache_port
            },
            log_retention = logs.RetentionDays.ONE_DAY,
            timeout = cdk.Duration.seconds(900),
            memory_size = 512,
            vpc_subnets = private_subnet_selection,
            security_group = internal_security_group,
            vpc = vpc
        )

        ## SQS Trigger
        postcode_cache_warmer_lambda.add_event_source(_lambda_event_sources.SqsEventSource(cache_warmer_queue, 
        batch_size = 1))

        
        ## SQS grant
        cache_warmer_queue.grant_consume_messages(postcode_cache_warmer_lambda)


###################################################################

        #  POSTCODE CACHE QUEUER LAMBDA
        ## Param store to track latest build number
        postcode_cache_queuer_latest_image = ssm.StringParameter.from_string_parameter_name(self, 
            "CacheQueuerLatestImage",
            string_parameter_name = "/WasteCollection/PostcodeCacheQueuer/LatestImage").string_value

        # Lambda - Postcode cache queuer
        postcode_cache_queuer_lambda = _lambda.DockerImageFunction(self, "WasteCollection-PostcodeCacheQueuer",
            code = _lambda.DockerImageCode.from_ecr(
                repository = ecr_repo[3],
                tag = postcode_cache_queuer_latest_image),
            architectures = [_lambda.Architecture.X86_64],
            function_name = "WasteCollection-PostcodeCacheQueuer",
            environment = {
                'SQS_URL': cache_warmer_queue.queue_url
            },
            log_retention = logs.RetentionDays.ONE_DAY,
            timeout = cdk.Duration.seconds(900),
            memory_size = 2048
        )

        ## SQS grant
        cache_warmer_queue.grant_send_messages(postcode_cache_queuer_lambda)

###################################################################

        # PARQUET COMPACTER FUNCTION
        ## Param store to track latest build number
        parquet_compact_latest_image = ssm.StringParameter.from_string_parameter_name(self, "ParquetCompactLatestImage",
            string_parameter_name = "/WasteCollection/ParquetCompact/LatestImage").string_value

        ## Function
        parquet_compact_lambda = _lambda.DockerImageFunction(self, 'WasteCollection-ParquetCompact',
            code = _lambda.DockerImageCode.from_ecr(
                repository = ecr_repo[5],
                tag = parquet_compact_latest_image),
            architectures = [_lambda.Architecture.X86_64],
            timeout = cdk.Duration.seconds(900),
            memory_size = 512,
            environment = {
                'DATA_BUCKET': data_bucket.bucket_name
            },
            function_name = "WasteCollection-ParquetCompact",
            log_retention = logs.RetentionDays.ONE_DAY
        )

        ## S3 Grant
        data_bucket.grant_read_write(parquet_compact_lambda)


#   _______          __  ______               _       
#  / ____\ \        / / |  ____|             | |      
# | |     \ \  /\  / /  | |____   _____ _ __ | |_ ___ 
# | |      \ \/  \/ /   |  __\ \ / / _ \ '_ \| __/ __|
# | |____   \  /\  /    | |___\ V /  __/ | | | |_\__ \
#  \_____|   \/  \/     |______\_/ \___|_| |_|\__|___/

        # Targets
        data_generator_lambda_target = (targets.LambdaFunction(data_generator_lambda))
        parquet_compact_lambda_target = (targets.LambdaFunction(parquet_compact_lambda))
        postcode_cache_queuer_lambda_target = (targets.LambdaFunction(postcode_cache_queuer_lambda))

        # Cloudwatch Event to trigger lambda every minute
        events.Rule(self, "RunEvery1Minute",
            schedule = events.Schedule.rate(cdk.Duration.minutes(1)),
            targets = [data_generator_lambda_target]
        )

        # Cloudwatch Event to trigger lambda every 5 minutes
        events.Rule(self, "RunEvery5Minutes",
            schedule = events.Schedule.rate(cdk.Duration.minutes(5)),
            targets = []
        )

        # Cloudwatch Event to trigger lambda every 60 minutes
        events.Rule(self, "RunEvery1Hour",
            schedule = events.Schedule.rate(cdk.Duration.minutes(60)),
            targets = [postcode_cache_queuer_lambda_target]
        )

#  ______ _          _                    
# |  ____(_)        | |                   
# | |__   _ _ __ ___| |__   ___  ___  ___ 
# |  __| | | '__/ _ \ '_ \ / _ \/ __|/ _ \
# | |    | | | |  __/ | | | (_) \__ \  __/
# |_|    |_|_|  \___|_| |_|\___/|___/\___|


        # Firehose Delivery Stream for IoT rule
        waste_collection_firehose = firehose.DeliveryStream(self, "WasteCollectionDeliveryStream",
            destinations = [destinations.S3Bucket(data_bucket,
                data_output_prefix = "raw/!{timestamp:yyyy}/!{timestamp:MM}/!{timestamp:dd}/!{timestamp:HH}/",
                error_output_prefix = "err/!{firehose:error-output-type}/",
                buffering_interval = cdk.Duration.minutes(1)
                )],
            delivery_stream_name = "WasteCollectionDeliveryStream"
        )

#  _____   _______ 
# |_   _| |__   __|
#   | |  ___ | |   
#   | | / _ \| |   
#  _| || (_) | |   
# |_____\___/|_|   

        # IoT thing security policy
        thing_policy = iot.CfnPolicy(self, "WasteCollectionThingPolicy",
            policy_name = "WasteCollectionThingPolicy",
            policy_document = {
                "Version":"2012-10-17",
                "Statement":[
                    {
                    "Effect":"Allow",
                    "Action":[
                        "iot:Publish",
                        "iot:Subscribe",
                        "iot:Connect",
                        "iot:Receive"
                    ],
                    "Resource":[
                        "*"
                    ]
                    }
                ] 
            }
        )

        # IoT thing defintion
        thing = iot.CfnThing(self, "WasteCollectionIngest",
            thing_name = "WasteCollectionIngest",
            attribute_payload = {
                "Attributes" : {"Name" : "WasteCollectionIngest"}
            }
        )

        # IoT certificate ARN
        # Todo - move this to parameter store
        thing_cert_arn = "arn:aws:iot:eu-west-1:811799881965:cert/1e6a88bcb8c82aeb51c27a89a7e31eebd7df0f75a5859d853e5a90b4b90e9acc"

        # Attach IoT policy to certificate
        thing_policy_attach = iot.CfnPolicyPrincipalAttachment(self, "WasteCollectionPolicyAttachment",
            policy_name = thing_policy.policy_name,
            principal = thing_cert_arn
        )
        thing_policy_attach.add_depends_on(thing_policy)

        # Attach IoT certificate to thing
        thing_cert_attach = iot.CfnThingPrincipalAttachment(self, "WasteCollectionCertificateAttachment",
            principal = thing_cert_arn,
            thing_name = thing.thing_name
        )
        thing_cert_attach.add_depends_on(thing)

        # IAM role for IoT to access Firehose 
        iot_firehose_iam_role = iam.Role(self, "IotFireholeIamRole",
            role_name = "WasteCollectionIotToFirehoseRole",
            assumed_by = iam.ServicePrincipal("iot.amazonaws.com"),
            inline_policies = [iam.PolicyDocument.from_json(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "VisualEditor0",
                                "Effect": "Allow",
                                "Action": [
                                    "firehose:DeleteDeliveryStream",
                                    "firehose:PutRecord",
                                    "firehose:PutRecordBatch",
                                    "firehose:UpdateDestination"
                                ],
                                "Resource": "*"
                            }
                        ]
                        } 
            )]
        )

        # IoT rule to move topic to Firehose
        iot.CfnTopicRule(self, "WasteCollectionTopicRule_Firehose",
            rule_name = "WasteCollectionTopicRuleFirehose",
            topic_rule_payload = iot.CfnTopicRule.TopicRulePayloadProperty(
                actions = [iot.CfnTopicRule.ActionProperty(
                    firehose = iot.CfnTopicRule.FirehoseActionProperty(
                        role_arn = iot_firehose_iam_role.role_arn,
                        delivery_stream_name = waste_collection_firehose.delivery_stream_name,
                        separator = ","
                ))],
                sql = "SELECT * FROM 'waste/household/+/collection'",
                aws_iot_sql_version = "2016-03-23"
            )
        )


        # IAM role for IoT to access Cloudwatch
        iot_cloudwatch_iam_role = iam.Role(self, "IotCloudwatchIamRole",
            role_name = "WasteCollectionIotToCloudwatchRole",
            assumed_by = iam.ServicePrincipal("iot.amazonaws.com"),
            inline_policies = [iam.PolicyDocument.from_json(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "VisualEditor0",
                                "Effect": "Allow",
                                "Action": [
                                    "cloudwatch:PutMetricData",
                                ],
                                "Resource": "*"
                            }
                        ]
                        } 
            )]
        )

        # IoT to Cloudwatch metrics rule
        iot.CfnTopicRule(self, f"WasteCollectionTopicRuleAll",
            rule_name = f"WasteCollectionTruckMetrics_All",
            topic_rule_payload = iot.CfnTopicRule.TopicRulePayloadProperty(
                actions = [iot.CfnTopicRule.ActionProperty(
                    cloudwatch_metric = iot.CfnTopicRule.CloudwatchMetricActionProperty(
                        role_arn = iot_cloudwatch_iam_role.role_arn,
                        metric_name = "${truck_id}",
                        metric_namespace = "WasteCollectionTrucks",
                        metric_value = "${load}",
                        metric_unit = "None"
                ))],
                sql = f"SELECT load, truck_id FROM 'waste/household/+/collection'",
                aws_iot_sql_version = "2016-03-23"
            )
        )

#   _____ _            
#  / ____| |           
# | |  __| |_   _  ___ 
# | | |_ | | | | |/ _ \
# | |__| | | |_| |  __/
#  \_____|_|\__,_|\___|        

        # IAM role for glue
        glue_crawler_iam_role = iam.Role(self, "GlueCrawlerIamRole",
            role_name = "WasteCollectionGlueCrawler",
            assumed_by = iam.ServicePrincipal("glue.amazonaws.com"),
            inline_policies = [iam.PolicyDocument.from_json(
                {
                "Version": "2012-10-17",
                "Statement": [
                    {
                    "Sid": "s0",
                    "Effect": "Allow",
                    "Action": [
                        "s3:PutObject",
                        "s3:GetObject",
                        "s3:ListBucket",
                        "s3:DeleteObject"
                    ],
                    "Resource": [
                        "arn:aws:s3:::stugraha*",
                    ]
                    }
                ]
                }
            )]
        )
        glue_crawler_iam_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name = 'service-role/AWSGlueServiceRole'))


        # Glue Databases
        waste_collection_db = glue.Database(self, "WasteCollectionDatabase",
            database_name = "wastecollection"
        )

        # Glue Crawler
        long_term_data_path = f"s3://{data_bucket.bucket_name}/processed"

        glue.CfnCrawler(self, "WasteCollectionCrawlerLongTerm",
            role = glue_crawler_iam_role.role_name,
            database_name = waste_collection_db.database_name,
            schedule = glue.CfnCrawler.ScheduleProperty(schedule_expression = 'cron(1 * * * ? *)'),
            targets = glue.CfnCrawler.TargetsProperty(
                s3_targets = [glue.CfnCrawler.S3TargetProperty(
                    path = long_term_data_path
                )
                ])
        )

        outcode_data_path = f"s3://{data_bucket.bucket_name}/reference/outcodes.csv"

        glue.CfnCrawler(self, "WasteCollectionCrawlerOutcodes",
            role = glue_crawler_iam_role.role_name,
            database_name = waste_collection_db.database_name,
            schedule = glue.CfnCrawler.ScheduleProperty(schedule_expression = 'cron(1 14 1 * ? *)'),
            targets = glue.CfnCrawler.TargetsProperty(
                s3_targets = [glue.CfnCrawler.S3TargetProperty(
                    path = outcode_data_path
                )
                ])
        )


#   ____        _      _        _       _     _   
#  / __ \      (_)    | |      (_)     | |   | |  
# | |  | |_   _ _  ___| | _____ _  __ _| |__ | |_ 
# | |  | | | | | |/ __| |/ / __| |/ _` | '_ \| __|
# | |__| | |_| | | (__|   <\__ \ | (_| | | | | |_ 
#  \___\_\\__,_|_|\___|_|\_\___/_|\__, |_| |_|\__|
#                                  __/ |          
#                                 |___/           


        # Quicksight data source
        aws_account_number = ssm.StringParameter.from_string_parameter_name(self, "WasteCollectionAccountId",
            string_parameter_name = "/WasteCollection/AccountId").string_value

        qs_datasource = quicksight.CfnDataSource(self, "WasteCollectionQSDataSource",
            name = "WasteCollectionAthena",
            aws_account_id = aws_account_number,
            data_source_id = "wastecollectiondatasource", 
            type = "ATHENA",
            data_source_parameters = quicksight.CfnDataSource.DataSourceParametersProperty(
                athena_parameters= quicksight.CfnDataSource.AthenaParametersProperty(
                    work_group = "primary"
                )
            )
        )


#   _____ _   _  _____ 
#  / ____| \ | |/ ____|
# | (___ |  \| | (___  
#  \___ \| . ` |\___ \ 
#  ____) | |\  |____) |
# |_____/|_| \_|_____/ 

        sns_topic = sns.Topic(self, "WasteCollectionSNSTopic",
            display_name="Used to alert WasteCollection matters"
        )



#   _____ _                 _               _       _     
#  / ____| |               | |             | |     | |    
# | |    | | ___  _   _  __| |_      ____ _| |_ ___| |__  
# | |    | |/ _ \| | | |/ _` \ \ /\ / / _` | __/ __| '_ \ 
# | |____| | (_) | |_| | (_| |\ V  V / (_| | || (__| | | |
#  \_____|_|\___/ \__,_|\__,_| \_/\_/ \__,_|\__\___|_| |_|


        # Cloudwatch Alarms
        TRUCK_QUANTITY = {"glasgow" : 41, "edinburgh": 32, "dundee" : 20, "aberdeen" : 20, "inverness" : 20}

        for city, volume in TRUCK_QUANTITY.items():
            unique_id = 0
            for _ in range(0, volume):
                unique_id += 1
                truck_id = city[0:3] + str(unique_id).zfill(4)

                truck_metric = cloudwatch.Metric(
                    metric_name = f"{truck_id}",
                    namespace = "WasteCollectionTrucks"
                )
                
                truck_excess_load_alarm = truck_metric.create_alarm(self, f"WasteCollectionCWAlarm_{truck_id}",
                    alarm_name = f"WasteCollectionTruckAlarm_{truck_id}",
                    threshold = 3800,
                    evaluation_periods = 1,
                    period = cdk.Duration.days(1),
                    statistic = "sum"
                )

                truck_excess_load_alarm.add_alarm_action(cw_actions.SnsAction(sns_topic))



