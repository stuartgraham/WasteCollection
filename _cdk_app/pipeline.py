from .application import WasteCollectionStage
from aws_cdk import (
    core as cdk,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_codebuild as codebuild,
    pipelines as pipelines
)
from .buildspec import build_spec as linked_build_spec

class PipelineStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

#  ______ _____ _____  
# |  ____/ ____|  __ \ 
# | |__ | |    | |__) |
# |  __|| |    |  _  / 
# | |___| |____| | \ \ 
# |______\_____|_|  \_\

        # ECR
        ecr_repo_data_generator = ecr.Repository(self, "ecr_data_generator",
            repository_name="waste_collection_data_generator"
        )
        ecr_repo_data_generator.add_lifecycle_rule(max_image_count=10)

        ecr_repo_data_transform = ecr.Repository(self, "ecr_data_transform",
            repository_name="waste_collection_data_transform"
        )
        ecr_repo_data_transform.add_lifecycle_rule(max_image_count=10)

        ecr_repo_postcode_cache_warmer = ecr.Repository(self, "ecr_repo_postcode_cache_warmer",
            repository_name="waste_collection_postcode_cache_warmer"
        )
        ecr_repo_postcode_cache_warmer.add_lifecycle_rule(max_image_count=10)

        ecr_repo_postcode_cache_queuer = ecr.Repository(self, "ecr_repo_postcode_cache_queuer",
            repository_name="waste_collection_postcode_cache_queuer"
        )
        ecr_repo_postcode_cache_queuer.add_lifecycle_rule(max_image_count=10)

        ecr_repo_historical_writer = ecr.Repository(self, "ecr_repo_historical_writer",
            repository_name="waste_collection_historical_writer"
        )
        ecr_repo_historical_writer.add_lifecycle_rule(max_image_count=10)

        ecr_repo_parquet_compact = ecr.Repository(self, "ecr_repo_parquet_compact",
            repository_name="waste_collection_parquet_compact"
        )
        ecr_repo_parquet_compact.add_lifecycle_rule(max_image_count=10)


#   _____ _ _   _           _     
#  / ____(_) | | |         | |    
# | |  __ _| |_| |__  _   _| |__  
# | | |_ | | __| '_ \| | | | '_ \ 
# | |__| | | |_| | | | |_| | |_) |
#  \_____|_|\__|_| |_|\__,_|_.__/ 

        # Github Source
        git_hub = pipelines.CodePipelineSource.git_hub(
                    "stuartgraham/WasteCollection",
                    "main",
                    authentication=cdk.SecretValue.secrets_manager("github-token")
                )

#   _____          _            _            _ _            
#  / ____|        | |          (_)          | (_)           
# | |     ___   __| | ___ _ __  _ _ __   ___| |_ _ __   ___ 
# | |    / _ \ / _` |/ _ \ '_ \| | '_ \ / _ \ | | '_ \ / _ \
# | |___| (_) | (_| |  __/ |_) | | |_) |  __/ | | | | |  __/
#  \_____\___/ \__,_|\___| .__/|_| .__/ \___|_|_|_| |_|\___|
#                        | |     | |                        
#                        |_|     |_|                        

        # Pipeline
        ## Synth
        pipeline = pipelines.CodePipeline(self, "Pipeline",
            synth = pipelines.ShellStep("Synth",
                input = git_hub,
                commands=[
                    "pip install -r requirements.txt", "npm install -g aws-cdk", "cdk synth"
                ]
            ),
            pipeline_name="WasteCollectionPipeline"
        )

#   _____          _      _           _ _     _ 
#  / ____|        | |    | |         (_) |   | |
# | |     ___   __| | ___| |__  _   _ _| | __| |
# | |    / _ \ / _` |/ _ \ '_ \| | | | | |/ _` |
# | |___| (_) | (_| |  __/ |_) | |_| | | | (_| |
#  \_____\___/ \__,_|\___|_.__/ \__,_|_|_|\__,_|

        ## Container build
        build_spec = codebuild.BuildSpec.from_object(linked_build_spec)
        build_role = iam.Role(self, "CodeBuildRole", 
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryPowerUser")
            ]
        )
        build_role.add_to_policy(iam.PolicyStatement(
                resources=["*"],
                actions=["ssm:PutParameter"]
        ))

        build_environment = codebuild.BuildEnvironment(
            build_image=codebuild.LinuxBuildImage.STANDARD_5_0,
            privileged=True
            )

        container_build = pipelines.CodeBuildStep("ContainerBuild",
            build_environment = build_environment,
            input = git_hub,
            partial_build_spec=build_spec,
            commands=[],
            role=build_role,
            env={
                "AWS_ACCOUNT_ID": self.account,
                "DATA_GENERATOR_REPO":  f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{ecr_repo_data_generator.repository_name}",
                "DATA_TRANSFORM_REPO":  f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{ecr_repo_data_transform.repository_name}",
                "POSTCODE_CACHE_WARMER_REPO":  f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{ecr_repo_postcode_cache_warmer.repository_name}",
                "POSTCODE_CACHE_QUEUER_REPO":  f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{ecr_repo_postcode_cache_queuer.repository_name}",
                "HISTORICAL_WRITER":  f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{ecr_repo_historical_writer.repository_name}",
                "PARQUET_COMPACT":  f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{ecr_repo_parquet_compact.repository_name}",
            }
        )

#  _____             _             
# |  __ \           | |            
# | |  | | ___ _ __ | | ___  _   _ 
# | |  | |/ _ \ '_ \| |/ _ \| | | |
# | |__| |  __/ |_) | | (_) | |_| |
# |_____/ \___| .__/|_|\___/ \__, |
#             | |             __/ |
#             |_|            |___/ 

        # App deploy
        waste_collection_app = WasteCollectionStage(self, "WasteCollectionApp",
        ecr_repo=[ecr_repo_data_generator, 
            ecr_repo_data_transform, 
            ecr_repo_postcode_cache_warmer,
            ecr_repo_postcode_cache_queuer,
            ecr_repo_historical_writer,
            ecr_repo_parquet_compact
        ])
        pipeline.add_stage(waste_collection_app, pre=[container_build])




