import json
import math
import os
import time
from datetime import datetime
import pytz
from uuid import uuid4

from model import table, cron_table
from scheduler import schedule_events
from sns_client import publish_sns
utc = pytz.utc

def handle(events):
    received = datetime.utcnow()
    to_be_scheduled = []
    to_be_saved = []
    cron_to_be_saved = []
    for event in events:
        if 'date' not in event and 'cronExpression' not in event:
            print('error.date_required %s' % (json.dumps({'event': event})))
            publish_to_failure_topic(event, 'date is required')
            continue
        if ('eventIdentifier' not in event or 'application' not in event):
            print('error.event_id_app_required %s' % (json.dumps({'event': event})))
            publish_to_failure_topic(event, 'date is required')
            continue
        if 'payload' not in event:
            print('error.payload_required %s' % (json.dumps({'event': event})))
            publish_to_failure_topic(event, 'payload is required')
            continue
        if 'target' not in event:
            print('error.target_required %s' % (json.dumps({'event': event})))
            publish_to_failure_topic(event, 'target is required')
            continue

        if not isinstance(event['payload'], str):
            publish_to_failure_topic(event, 'payload must be a string')
            print('error.payload_is_not_string %s' % (json.dumps({'event': event})))
            continue

        if 'cronExpression' in event:
            # It's cron event - store it in cron_table
            if 'start_date' not in event:
                event['start_date'] = received.replace(second=0, microsecond=0).isoformat()
            event_wrapper = {
                'pk': f"{event['application']}-{event['eventIdentifier']}",
                'eventIdentifier': str(event['eventIdentifier']),
                'application': event['application'],
                'start_date': event['start_date'],
                'target': event['target'],
                'payload': event['payload'],
                'cronExpression': event['cronExpression'],
                'last_date': received.replace(second=0, microsecond=0).isoformat(),
            }
            if 'end_date' in event:
                event_wrapper['end_date'] = event['end_date']
                date = datetime.fromisoformat(event['end_date'])
                dt_utc = utc.localize(date)
                dt_bst = dt_utc.astimezone(pytz.timezone('Europe/London'))
                str_bst = dt_bst.isoformat()
                len_bst = len(str_bst)
                new_dt = str_bst[:len_bst - 6]
                ndate = datetime.fromisoformat(new_dt)
                event_wrapper['time_to_live'] = int(ndate.timestamp() + 10 * 60)
            if 'failure_topic' in event:
                event_wrapper['failure_topic'] = event['failure_topic']
            cron_to_be_saved.append(event_wrapper)
        else:
            date = datetime.fromisoformat(event['date'])
            event_wrapper = {
                'pk': int(date.replace(second=0, microsecond=0).timestamp()),
                # the id separator has to be an underscore, because sqs IDs can only contain alphanumeric characters, hyphens and underscores
                'sk': f"{int(date.timestamp() * 1000)}_{str(uuid4())}",
                'time_to_live': int(date.timestamp() + 10 * 60),  # wait at least 10 minutes after the event should have gone out
                'eventIdentifier': str(event['eventIdentifier']),
                'application': event['application'],
                'date': event['date'],
                'payload': event['payload'],
                'target': event['target']
            }

            if 'failure_topic' in event:
                event_wrapper['failure_topic'] = event['failure_topic']

            if 'user' in event:
                event_wrapper['user'] = event['user']
            #     if os.environ.get('ENFORCE_USER'):
            #         publish_to_failure_topic(event, 'user is required')
            #         print('error.event_has_no_user %s' % (json.dumps({'event': event})))
            #         continue
            # else:
            #     event_wrapper['user'] = event['user']

            # if the event has less than 10 minutes until execution, then fast track it
            if has_less_then_ten_minutes(event_wrapper['date']):
                to_be_scheduled.append(event_wrapper)
            else:
                to_be_saved.append(event_wrapper)
            print('event.consumed %s' % (json.dumps({'id': event_wrapper['eventIdentifier'], 'application': event_wrapper['application'], 'timestamp': str(received)})))

    # we must save before delegating, because the downstream function will access the DB entity
    save_with_retry(to_be_saved)
    save_cron_with_retry(cron_to_be_saved)

    print('Fast track scheduling for %d entries' % len(to_be_scheduled))
    schedule_events(to_be_scheduled)

    print('Processed %d entries' % len(events))


def has_less_then_ten_minutes(date):
    minutes = int(get_seconds_remaining(date) / 60)
    return minutes < 10


def get_seconds_remaining(date):
    now = datetime.utcnow()
    target = datetime.fromisoformat(date)
    delta = target - now
    return math.ceil(delta.total_seconds())


def publish_to_failure_topic(event, reason):
    # todo: prepare against failure of publish sns
    print('Event failed: %s' % event)
    if 'failure_topic' in event:
        payload = {
            'error': reason,
            'event': event
        }
        publish_sns(event['failure_topic'], json.dumps(payload))


def save_with_retry(items):
    while True:
        if len(items) == 0:
            break
        item = items.pop(0)
        try:
            table.put_item(Item=item)
        except Exception as e:
            print(str(e))
            print('Delaying put of %s' % item.id)
            items.append(item)
            time.sleep(.200)

def save_cron_with_retry(items):
    while True:
        if len(items) == 0:
            break
        item = items.pop(0)
        try:
            cron_table.put_item(Item=item)
        except Exception as e:
            print(str(e))
            print('Delaying put of %s' % item.id)
            items.append(item)
            time.sleep(.200)
