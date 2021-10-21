build_spec = {
    "version": "0.2",
    "phases": {
        "install": {
            "commands": [
                "echo Install phase started",
                "echo $DATA_GENERATOR_REPO",
                "echo $DATA_TRANSFORM_REPO",
                "echo $POSTCODE_CACHE_WARMER_REPO",
                "echo $POSTCODE_CACHE_QUEUER_REPO",
                "echo $HISTORICAL_WRITER",
                "echo $PARQUET_COMPACT"
            ]
        },
        "pre_build": {
            "commands": [
                "echo Logging in to Amazon ECR",
                "aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com"
            ]
        },
        "build": {
            "commands": [
                "echo Starting build number $CODEBUILD_BUILD_NUMBER",
                "echo Building image",
                "BUILD_PREFIX=1.0.",
                "TAG_NAME=$BUILD_PREFIX$CODEBUILD_BUILD_NUMBER",
                "LATEST_IMAGE_TAG=$TAG_NAME",
                "echo $LATEST_IMAGE_TAG",
                "echo $TAG_NAME",
                "echo ££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££",
                "cd src/data_generator",
                "aws ssm put-parameter --name \"/WasteCollection/DataGenerator/LatestImage\" --type \"String\" --value $LATEST_IMAGE_TAG --overwrite",
                "docker build --no-cache -t $DATA_GENERATOR_REPO:$TAG_NAME .",
                "docker tag $DATA_GENERATOR_REPO:$TAG_NAME $DATA_GENERATOR_REPO:latest",
                "echo ££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££",
                "cd ../data_transform",
                "aws ssm put-parameter --name \"/WasteCollection/DataTransform/LatestImage\" --type \"String\" --value $LATEST_IMAGE_TAG --overwrite",
                "docker build --no-cache -t $DATA_TRANSFORM_REPO:$TAG_NAME .",
                "docker tag $DATA_TRANSFORM_REPO:$TAG_NAME $DATA_TRANSFORM_REPO:latest",
                "echo ££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££",
                "cd ../postcode_cache_warmer",
                "aws ssm put-parameter --name \"/WasteCollection/PostcodeCacheWarmer/LatestImage\" --type \"String\" --value $LATEST_IMAGE_TAG --overwrite",
                "docker build --no-cache -t $POSTCODE_CACHE_WARMER_REPO:$TAG_NAME .",
                "docker tag $POSTCODE_CACHE_WARMER_REPO:$TAG_NAME $POSTCODE_CACHE_WARMER_REPO:latest",
                "echo ££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££",
                "cd ../postcode_cache_queuer",
                "aws ssm put-parameter --name \"/WasteCollection/PostcodeCacheQueuer/LatestImage\" --type \"String\" --value $LATEST_IMAGE_TAG --overwrite",
                "docker build --no-cache -t $POSTCODE_CACHE_QUEUER_REPO:$TAG_NAME .",
                "docker tag $POSTCODE_CACHE_QUEUER_REPO:$TAG_NAME $POSTCODE_CACHE_QUEUER_REPO:latest",
                "echo ££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££",
                "cd ../historical_writer",
                "aws ssm put-parameter --name \"/WasteCollection/HistoricalWriter/LatestImage\" --type \"String\" --value $LATEST_IMAGE_TAG --overwrite",
                "docker build --no-cache -t $HISTORICAL_WRITER:$TAG_NAME .",
                "docker tag $HISTORICAL_WRITER:$TAG_NAME $HISTORICAL_WRITER:latest",
                "echo ££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££",
                "cd ../parquet_compact",
                "aws ssm put-parameter --name \"/WasteCollection/ParquetCompact/LatestImage\" --type \"String\" --value $LATEST_IMAGE_TAG --overwrite",
                "docker build --no-cache -t $PARQUET_COMPACT:$TAG_NAME .",
                "docker tag $PARQUET_COMPACT:$TAG_NAME $PARQUET_COMPACT:latest",
            ]
        },
        "post_build": {
            "commands": [
                "echo Pushing Docker images",
                "docker push $DATA_GENERATOR_REPO:$TAG_NAME",
                "docker push $DATA_GENERATOR_REPO:latest",
                "docker push $DATA_TRANSFORM_REPO:$TAG_NAME",
                "docker push $DATA_TRANSFORM_REPO:latest",
                "docker push $POSTCODE_CACHE_WARMER_REPO:$TAG_NAME",
                "docker push $POSTCODE_CACHE_WARMER_REPO:latest",
                "docker push $POSTCODE_CACHE_QUEUER_REPO:$TAG_NAME",
                "docker push $POSTCODE_CACHE_QUEUER_REPO:latest",
                "docker push $HISTORICAL_WRITER:$TAG_NAME",
                "docker push $HISTORICAL_WRITER:latest",
                "docker push $PARQUET_COMPACT:$TAG_NAME",
                "docker push $PARQUET_COMPACT:latest",
                "echo Build complete"
            ]
        }
    }
}
