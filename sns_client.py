import boto3

client = boto3.client('sns')


def publish_sns(arn, payload):
    print(f"publishing to an event : {arn}")
    client.publish(
        TopicArn=arn,
        Message=payload
    )
