import json
import math
import os
from datetime import datetime

from boto3.dynamodb.conditions import Key

from model import table
from sns_client import publish_sns
from sqs_client import publish_sqs


def handle(event_ids):
    print(f"Scheduling {event_ids}")
    events = []
    for event_id in event_ids:
        items = table.query(
                KeyConditionExpression=Key('pk').eq(event_id['pk']) & Key('sk').eq(event_id['sk'])
            ).get('Items', [])
        if len(items) == 0:
            print('Event %s doesn\'t exist anymore' % event_id)
            continue
        events.append(items[0])

    schedule_events(events)


def schedule_cron_events(events):
    failed_cron_event = []
    for item in events:
        try:
            publish_sns(item['target'], item['payload'])
            now = datetime.utcnow()
            print('cron event.emitted %s' % (json.dumps({'pk': item['pk'], 'timestamp': str(now), 'scheduled': str(item['cronExpression'])})))
        except Exception as e:
            print(f"Failed to emit cron event {item['pk']}: {str(e)}")
            failed_cron_event.append(item)   

    for event in failed_cron_event:
        try:
            if 'failure_topic' not in event:
                payload = {
                    'error': 'ERROR',
                    'event': event['payload']
                }
                publish_sns(event.failure_topic, json.dumps(payload))
        except Exception as e:
            print(f"Failed to emit event {event['pk']} to failure topic: {str(e)}") 


def schedule_events(events):
    successful_ids = []
    failed_ids = []
    to_be_scheduled = []
    events_by_id = {}
    for event in events:
        events_by_id[event['sk']] = event

        # check for cronjob using croniter

        delta = datetime.fromisoformat(event['date']) - datetime.utcnow()
        delay = delta.total_seconds()
        rounded_delay = math.ceil(delay)

        # schedule the event a second earlier to help with delays in sqs/lambda cold start
        # the emitter will wait accordingly
        rounded_delay -= 1
        if rounded_delay < 0:
            rounded_delay = 0

        print(f'ID {event["sk"]} is supposed to emit in {rounded_delay}s which is {delay - rounded_delay}s before target.')

        event = {
            'payload': event['payload'],
            'target': event['target'],
            'sk': event['sk'],
            'pk': int(event['pk']),
            'date': event['date']
        }
        if 'failure_topic' in event:
            event['failure_topic'] = event['failure_topic']
        sqs_message = {
            'Id': event['sk'],
            'MessageBody': json.dumps(event),
            'DelaySeconds': rounded_delay
        }
        to_be_scheduled.append(sqs_message)

        if len(to_be_scheduled) == 10:
            successes, failures = publish_sqs(os.environ.get('QUEUE_URL'), to_be_scheduled)
            failed_ids.extend(failures)
            successful_ids.extend(successes)
            to_be_scheduled = []
    successes, failures = publish_sqs(os.environ.get('QUEUE_URL'), to_be_scheduled)
    failed_ids.extend(failures)
    successful_ids.extend(successes)
    print(f'Success: {len(successful_ids)}, Failed: {len(failed_ids)}')
    for id in failed_ids:
        print(f"Failed to schedule the following events: {failures}")
        item = events_by_id[id]
        # todo: instead of publishing the error we should reschedule it automatically
        # can happen if sqs does not respond
        if 'failure_topic' in item:
            payload = {
                'error': 'ERROR',
                'event': item['payload']
            }
            publish_sns(item['failure_topic'], json.dumps(payload))
