import boto3
import json
import os
import urllib3
from datetime import datetime, timedelta

# 전역 캐시 딕셔너리
instance_name_cache = {}

def get_instance_name(instance_id):
    if instance_id in instance_name_cache:
        return instance_name_cache[instance_id]

    ec2 = boto3.client('ec2')
    try:
        reservations = ec2.describe_instances(InstanceIds=[instance_id])['Reservations']
        for reservation in reservations:
            for instance in reservation['Instances']:
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        instance_name_cache[instance_id] = name
                        return name
    except Exception as e:
        print(f"[WARNING] 인스턴스 이름 조회 실패 (InstanceId: {instance_id}) - 권한 없음 또는 기타 오류: {e}")

    instance_name_cache[instance_id] = instance_id
    return instance_id

def get_alarm_history(cloudwatch, alarm_name):
    try:
        history = cloudwatch.describe_alarm_history(
            AlarmName=alarm_name,
            HistoryItemType='StateUpdate',
            MaxRecords=3,
            ScanBy='TimestampDescending'
        )
        items = history.get('AlarmHistoryItems', [])
        if not items:
            print(f"[INFO] 알람 이력이 없습니다: {alarm_name}")
        return [
            f"- {h['Timestamp'].isoformat()} : `{h['HistorySummary']}`"
            for h in items
        ]
    except Exception as e:
        print(f"[ERROR] 알람 이력 조회 실패 ({alarm_name}): {e}")
        return []

def lambda_handler(event, context):
    aws_console_region = os.getenv('AWS_CONSOLE_REGION', 'ap-northeast-2')
    cloudwatch = boto3.client('cloudwatch')
    slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not slack_webhook_url:
        raise ValueError("환경 변수 'SLACK_WEBHOOK_URL'이 설정되지 않았습니다.")

    # Validate event structure
    if not event.get('Records') or not isinstance(event['Records'], list) or not event['Records']:
        raise ValueError("Invalid SNS message structure in event: 'Records' is missing, not a list, or empty.")
    
    record = event['Records'][0]
    if not record.get('Sns') or not record['Sns'].get('Message'):
        raise ValueError("Invalid SNS message structure in event: 'Sns' or 'Sns.Message' is missing.")

    sns_message = json.loads(record['Sns']['Message'])
    alarm_name = sns_message['AlarmName']
    new_state = sns_message.get('NewStateValue', 'UNKNOWN')
    alarm_description = sns_message.get('AlarmDescription', '')

    trigger = sns_message.get('Trigger', {})
    metrics = trigger.get('Metrics', [])
    metric_results = []

    try:
        state_change_time = datetime.strptime(sns_message['StateChangeTime'], "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError as e:
        raise ValueError(f"StateChangeTime 포맷 오류: {sns_message['StateChangeTime']}") from e

    start_time = state_change_time - timedelta(seconds=600)
    end_time = state_change_time

    for metric in metrics:
        try:
            if 'MetricStat' in metric:
                metric_name = metric['MetricStat']['Metric']['MetricName']
                namespace = metric['MetricStat']['Metric']['Namespace']
                dimensions = metric['MetricStat']['Metric']['Dimensions']
                expression = metric.get('Expression', '')
                unit = metric['MetricStat'].get('Unit', '')

                formatted_dimensions = [
                    {'Name': d['name'], 'Value': d['value']} if 'name' in d and 'value' in d else d
                    for d in dimensions
                ]

                response = cloudwatch.get_metric_data(
                    MetricDataQueries=[
                        {
                            'Id': 'm1',
                            'MetricStat': {
                                'Metric': {
                                    'Namespace': namespace,
                                    'MetricName': metric_name,
                                    'Dimensions': formatted_dimensions
                                },
                                'Period': metric['MetricStat']['Period'],
                                'Stat': metric['MetricStat']['Stat'],
                                'Unit': unit if unit else 'None'
                            }
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time
                )
                metric_value = response['MetricDataResults'][0]['Values']
                metric_results.append({
                    'Type': 'MetricStat',
                    'MetricName': metric_name,
                    'Namespace': namespace,
                    'Dimensions': formatted_dimensions,
                    'Value': max(metric_value) if metric_value else 'No Data',
                    'Expression': expression,
                    'Unit': unit
                })

        except KeyError as e:
            print(f"KeyError while processing metric: '{e}' not found in metric item. Check alarm configuration.")
            print(f"Faulty metric data: {json.dumps(metric, indent=2)}")

    header_text = f"*[{new_state}]* `{alarm_name}`"
    detail_lines = []

    if alarm_description:
        detail_lines.append(f"*설명:* {alarm_description}")

    for metric in metric_results:
        if metric['Type'] == 'MetricStat':
            instance_id = next((d['Value'] for d in metric['Dimensions'] if d['Name'] == 'InstanceId'), "Unknown")
            instance_name = get_instance_name(instance_id)
            value = metric['Value']
            value_str = f"{round(value, 1)}" if isinstance(value, (int, float)) else str(value)
            expression = metric['Expression'] or metric['MetricName']
            unit = metric['Unit']
            metric_line = f"*{expression}*: `{value_str}` {unit} : `{instance_name}`"
            if len(metric_line) > 2000:
                metric_line = metric_line[:2000]
            detail_lines.append(metric_line)

    recent_events = get_alarm_history(cloudwatch, alarm_name)
    if recent_events:
        detail_lines.append("*최근 알람 이벤트:*")
        detail_lines.extend(recent_events)
    else:
        detail_lines.append("_최근 알람 이벤트 없음 또는 조회 실패_")

    alarm_link = f"<https://{aws_console_region}.console.aws.amazon.com/cloudwatch/home?region={aws_console_region}#alarmsV2:|경보 바로가기>"
    dashboard_link = f"<https://{aws_console_region}.console.aws.amazon.com/cloudwatch/home?region={aws_console_region}#dashboards/|대시보드 바로가기>"
    detail_lines.append(f"{alarm_link} | {dashboard_link}")

    slack_message = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": header_text
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "\n".join(detail_lines)
                    }
                ]
            }
        ]
    }

    http = urllib3.PoolManager()
    response = http.request(
        'POST',
        slack_webhook_url,
        body=json.dumps(slack_message).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )

    return {
        'statusCode': response.status,
        'body': response.data.decode('utf-8')
    }
