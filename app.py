from flask import Flask, request
from sns_client import publish_sns
from model import cron_table, table
from boto3.dynamodb.conditions import Key
from croniter import croniter

import os
import json

app = Flask(__name__)


@app.route("/api/schedule", methods=['POST'])
def scheduleTask():
    event = request.get_json(force=True)
    validationRes = validateEvent(event) 
    if len(validationRes) > 0:
        return validationRes, 400
    identifier = f"{event['application']}-{event['eventIdentifier']}"
    items = cron_table.query(
        KeyConditionExpression=Key('pk').eq(identifier)
    ).get('Items', [])
    if ('cronExpression' in event and len(items) == 0) or 'date' in event:
        try:
            publish_sns(os.environ.get('TOPIC_URL'), json.dumps(event))
            return "Event successfully created", 201
        except Exception as e:
            print(f"Failed to create event")
            return "Event cannot be created.", 400
    else:
        return "Event already exist. You need to update it.", 400


@app.route("/api/schedule", methods=['GET'])
def getTask():
    args = request.args
    print(args)
    app = ""
    eid = ""
    if "application" in args:
        app = args["application"]
    if "eventIdentifier" in args:
        eid = args.get("eventIdentifier")
    if app == "" or eid == "":
        return "application and eventIdentifier are required as query string parameters.", 400
    else:
        identifier = f"{app}-{eid}"
        items = cron_table.query(
            KeyConditionExpression=Key('pk').eq(identifier),
            ProjectionExpression='#d, target, #u, eventIdentifier, application, failure_topic, payload, start_date, end_date, cronExpression, last_date',
            ExpressionAttributeNames={'#d': 'date', '#u': 'user'}
        ).get('Items', [])
        date_items = table.query(
            IndexName='appEventIndex',
            KeyConditionExpression=Key('application').eq(
                app) & Key('eventIdentifier').eq(eid),
            ProjectionExpression='#d, target, eventIdentifier, application, failure_topic, payload',
            ExpressionAttributeNames={'#d': 'date'}
        ).get('Items', [])
        if len(items) == 0 and len(date_items) > 0:
            items = date_items
        elif len(date_items) > 0:
            for item in date_items:
                items.append(item)
        print(items)
        if len(items) == 0:
            return "No such event exist.", 400
        else:
            return {"Count": len(items), "Items": json.loads(json.dumps(items))}, 200


@app.route("/api/schedule/<app>/<id>", methods=['PUT'])
def updateTask(app, id):
    args = request.view_args['app']
    event = request.get_json(force=True)
    validationRes = validateEvent(event) 
    if len(validationRes) > 0:
        return validationRes, 400
    try:
        publish_sns(os.environ.get('TOPIC_URL'), json.dumps(event))
        return "Event updated successfully", 200
    except Exception as e:
        print(f"Failed to update event")
        return "Event cannot be created.", 400


@app.route("/api/schedule/<app>/<id>", methods=['DELETE'])
def deleteTask(app, id):
    cron_table.delete_item(
        Key={
            'pk': f"{app}-{id}",
        },
    )
    date_items = table.query(
            IndexName='appEventIndex',
            KeyConditionExpression=Key('application').eq(app) & Key('eventIdentifier').eq(id),
            ProjectionExpression='application, eventIdentifier, pk, sk'
        ).get('Items', [])
    for item in date_items:
        print(item)
        table.delete_item(
            Key={
                'pk': item['pk'],
                'sk': item['sk']
            },
        )
    return "Date and cron events deleted successfully.", 200


def validateEvent(event):
    if 'cronExpression' in event:
        # if 'start_date' not in event:
        #     print('error.start_date %s' %
        #         (json.dumps({'event': event})))    
        #     return "start_date is required."
        if not(croniter.is_valid(event['cronExpression'])):
            print('error.event_id_app_required %s' %
                (json.dumps({'event': event})))
            return "cron expression is not valid"
    if ('eventIdentifier' not in event or 'application' not in event):
        print('error.event_id_app_required %s' %
              (json.dumps({'event': event})))
        return "eventIdentifier and application is required."
    if 'date' not in event and 'cronExpression' not in event:
        print('error.date_required %s' % (json.dumps({'event': event})))
        return "date or cronExpression is required."
    if 'payload' not in event:
        print('error.payload_required %s' %
                (json.dumps({'event': event})))
        return "payload is required."
    if 'target' not in event:
        print('error.target_required %s' %
                (json.dumps({'event': event})))
        return "target is required."
    return ""    
