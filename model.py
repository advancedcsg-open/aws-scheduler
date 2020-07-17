import os

import boto3

table_name = f'aws-scheduler-events-v2-{os.environ.get("STAGE")}'
cron_table_name = f'aws-scheduler-cron-events-v2-{os.environ.get("STAGE")}'
table = boto3.resource('dynamodb').Table(table_name)
cron_table = boto3.resource('dynamodb').Table(cron_table_name)
client = boto3.client('dynamodb')