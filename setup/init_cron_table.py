import sys
import time

import boto3

client = boto3.client('dynamodb')


def create_events_table():
    if len(sys.argv) < 2:
        print('Missing argument for stage.')
    stage = sys.argv[1]

    name = f'aws-scheduler-cron-events-v2-{stage}'
    while True:
        response = client.list_tables()
        if name in response['TableNames']:
            print('Table %s already exists. Please delete it first. Waiting 5 seconds until trying again...' % name)
            time.sleep(5)
        else:
            break
    client.create_table(
        TableName=name,
        AttributeDefinitions=[
            {
                'AttributeName': 'pk',
                'AttributeType': 'S'
            }
        ],
        KeySchema=[
            {
                'AttributeName': 'pk',
                'KeyType': 'HASH'
            }
        ],
        BillingMode='PAY_PER_REQUEST',
    )
    print(f'Creating cron table ...')
    client.get_waiter('table_exists').wait(TableName=name)
    print('%s created' % name)


if __name__ == '__main__':
    create_events_table()
