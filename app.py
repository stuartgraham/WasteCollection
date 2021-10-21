#!/usr/bin/env python3
from aws_cdk import core
from _cdk_app.pipeline import PipelineStack

app = core.App()
aws_env = core.Environment(account="811799881965", region="eu-west-1")

PipelineStack(app, "WasteCollectionPipeline", 
    env=aws_env
    )

app.synth()
