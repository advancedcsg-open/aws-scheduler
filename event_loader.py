import json
import os
from datetime import datetime
from croniter import croniter

from boto3.dynamodb.types import TypeDeserializer

from lambda_client import invoke_lambda
from model import client, table_name, cron_table_name, cron_table
from util import make_chunks
from scheduler import schedule_cron_events

deserializer = TypeDeserializer()


def run():
    current_segment = int(datetime.utcnow().replace(second=0, microsecond=0).timestamp() + 10 * 60)  # scan the minute that is 10 minutes away, not the one that is already progressing

    count = 0

    # get events which match the current time and add those to ids
    for page in client.get_paginator('scan').paginate(
        TableName=cron_table_name,
    ):
        items = []
        items_to_execute = []
        current_date = datetime.utcnow().replace(second=0, microsecond=0)
        next_date = ''
        current_date_str = datetime.utcnow().replace(second=0, microsecond=0).isoformat()
        for item in page.get('Items', []):
            event = {k: deserializer.deserialize(v) for k, v in item.items()}
            items.append({
                'pk': event['pk'],
                'eventIdentifier': event['eventIdentifier'],
                'application': event['application'],
                'last_date': event['last_date'],
                'cronExpression': event['cronExpression'],
                'payload': event['payload'],
                'target': event['target'],
                'end_date': event['end_date'] if 'end_date' in event else "",
                'start_date': event['start_date'],
            })

        for item in items:
            print(f"current date time : {datetime.utcnow()}  {datetime.fromisoformat(item['start_date'])}")
            if croniter.is_valid(item['cronExpression']) and datetime.fromisoformat(item['start_date']) < datetime.utcnow():
                iter = croniter(item['cronExpression'], datetime.fromisoformat(item['last_date']))
                next_date = iter.get_next(datetime)
                while next_date < current_date:
                    next_date = iter.get_next(datetime)
                if (next_date - current_date).total_seconds() <= 60:
                    if (len(item['end_date']) > 0 and next_date < datetime.fromisoformat(item['end_date'])) or (len(item['end_date']) == 0):
                        item['next_date'] = next_date.isoformat()
                        print(f" item : {item}")
                        items_to_execute.append(item)

        print('Items needs to be executed: ')
        print(items_to_execute)
        for item in items_to_execute:
            response = cron_table.update_item(
                Key= {
                    'pk': item['pk']
                },
                UpdateExpression="set last_date=:l",
                ExpressionAttributeValues={
                    ':l': item['next_date'],
                },
                ReturnValues="UPDATED_NEW"
            )
        schedule_cron_events(items_to_execute)

    for page in client.get_paginator('query').paginate(
            TableName=table_name,
            ProjectionExpression='pk,sk',
            KeyConditionExpression='pk = :s',
            ExpressionAttributeValues={
                ':s': {
                    'N': str(current_segment)
                }
            }):
        ids = []
        for item in page.get('Items', []):
            event = {k: deserializer.deserialize(v) for k, v in item.items()}
            ids.append({
                'pk': int(event['pk']),
                'sk': event['sk']
            })

        for chunk in make_chunks(ids, 200):
            invoke_lambda(os.environ.get('SCHEDULE_FUNCTION'), json.dumps(chunk).encode('utf-8'))

        count += page['Count']

    print('Batched %d entries' % count)
