FROM public.ecr.aws/lambda/python:latest
COPY . ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt && rm requirements.txt
CMD [ "main.handler" ]
