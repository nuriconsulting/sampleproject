import unittest
from unittest.mock import patch, MagicMock
import boto3
import json
import os
from datetime import datetime, timedelta

# Import functions from the Lambda script
import lambda_function
from lambda_function import get_instance_name, lambda_handler

class TestGetInstanceName(unittest.TestCase):

    def setUp(self):
        # Reset the global cache before each test
        lambda_function.instance_name_cache = {}

    @patch('lambda_function.boto3.client')
    def test_get_instance_name_cache_miss_api_success(self, mock_boto_client):
        mock_ec2 = MagicMock()
        mock_boto_client.return_value = mock_ec2
        mock_ec2.describe_instances.return_value = {
            'Reservations': [{
                'Instances': [{
                    'Tags': [{'Key': 'Name', 'Value': 'TestInstance'}]
                }]
            }]
        }

        instance_id = 'i-12345'
        name = get_instance_name(instance_id)

        self.assertEqual(name, 'TestInstance')
        self.assertIn(instance_id, lambda_function.instance_name_cache)
        self.assertEqual(lambda_function.instance_name_cache[instance_id], 'TestInstance')
        mock_ec2.describe_instances.assert_called_once_with(InstanceIds=[instance_id])

    @patch('lambda_function.boto3.client')
    def test_get_instance_name_cache_hit(self, mock_boto_client):
        mock_ec2 = MagicMock()
        mock_boto_client.return_value = mock_ec2
        instance_id = 'i-cached123'
        cached_name = 'CachedName'
        lambda_function.instance_name_cache[instance_id] = cached_name

        name = get_instance_name(instance_id)

        self.assertEqual(name, cached_name)
        mock_ec2.describe_instances.assert_not_called()

    @patch('lambda_function.boto3.client')
    def test_get_instance_name_api_error(self, mock_boto_client):
        mock_ec2 = MagicMock()
        mock_boto_client.return_value = mock_ec2
        mock_ec2.describe_instances.side_effect = Exception("AWS API Error")

        instance_id = 'i-error123'
        name = get_instance_name(instance_id)

        self.assertEqual(name, instance_id) # Should return instance_id on error
        self.assertIn(instance_id, lambda_function.instance_name_cache)
        self.assertEqual(lambda_function.instance_name_cache[instance_id], instance_id)
        mock_ec2.describe_instances.assert_called_once_with(InstanceIds=[instance_id])

    @patch('lambda_function.boto3.client')
    def test_get_instance_name_instance_not_found_or_no_name_tag(self, mock_boto_client):
        mock_ec2 = MagicMock()
        mock_boto_client.return_value = mock_ec2
        # Simulate instance not found (empty reservations)
        mock_ec2.describe_instances.return_value = {'Reservations': []}
        
        instance_id_not_found = 'i-notfound'
        name_not_found = get_instance_name(instance_id_not_found)
        self.assertEqual(name_not_found, instance_id_not_found)
        self.assertEqual(lambda_function.instance_name_cache[instance_id_not_found], instance_id_not_found)

        # Reset cache for next part of test
        lambda_function.instance_name_cache = {}
        
        # Simulate instance found but no 'Name' tag
        mock_ec2.describe_instances.return_value = {
            'Reservations': [{'Instances': [{'Tags': [{'Key': 'OtherTag', 'Value': 'SomeValue'}]}]}]
        }
        instance_id_no_name = 'i-noname'
        name_no_name = get_instance_name(instance_id_no_name)
        self.assertEqual(name_no_name, instance_id_no_name)
        self.assertEqual(lambda_function.instance_name_cache[instance_id_no_name], instance_id_no_name)


class TestLambdaHandler(unittest.TestCase):

    def setUp(self):
        # Reset the global cache before each test
        lambda_function.instance_name_cache = {}
        self.mock_env_vars = {
            'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX',
            'AWS_CONSOLE_REGION': 'us-east-1'
        }

    @patch('lambda_function.boto3.client')
    @patch('lambda_function.os.getenv')
    @patch('lambda_function.urllib3.PoolManager')
    def test_lambda_handler_successful_sns_event(self, mock_pool_manager, mock_os_getenv, mock_boto_client):
        # Mock os.getenv
        mock_os_getenv.side_effect = lambda k, d=None: self.mock_env_vars.get(k, d)

        # Mock AWS clients
        mock_cloudwatch = MagicMock()
        mock_ec2 = MagicMock()
        # Configure boto3.client to return the correct mock based on service name
        def client_side_effect(service_name, *args, **kwargs):
            if service_name == 'cloudwatch':
                return mock_cloudwatch
            elif service_name == 'ec2':
                return mock_ec2
            return MagicMock() # Default mock for other services if any
        mock_boto_client.side_effect = client_side_effect
        
        # Mock CloudWatch responses
        mock_cloudwatch.describe_alarm_history.return_value = {
            'AlarmHistoryItems': [
                {'Timestamp': datetime.now() - timedelta(minutes=5), 'HistorySummary': 'State updated to ALARM'},
                {'Timestamp': datetime.now() - timedelta(minutes=10), 'HistorySummary': 'State updated to OK'}
            ]
        }
        mock_cloudwatch.get_metric_data.return_value = {
            'MetricDataResults': [{
                'Id': 'm1',
                'Timestamps': [datetime.now() - timedelta(minutes=1)],
                'Values': [100.0]
            }]
        }

        # Mock EC2 response for instance name
        mock_ec2.describe_instances.return_value = {
            'Reservations': [{'Instances': [{'Tags': [{'Key': 'Name', 'Value': 'MyTestInstance'}]}]}]
        }
        
        # Mock urllib3 response
        mock_http_response = MagicMock()
        mock_http_response.status = 200
        mock_http_response.data = b'ok'
        mock_pool_manager.return_value.request.return_value = mock_http_response

        # Sample SNS event
        sns_message_payload = {
            "AlarmName": "Test-Alarm-CPU-High",
            "AlarmDescription": "This is a test alarm for high CPU utilization.",
            "AWSAccountId": "123456789012",
            "NewStateValue": "ALARM",
            "NewStateReason": "Threshold Crossed: [CPUUtilization > 80.0 for 1 datapoints within 5 minutes]",
            "StateChangeTime": (datetime.now() - timedelta(minutes=1)).isoformat() + "Z", # Ensure valid ISO format
            "Region": "US East (N. Virginia)",
            "OldStateValue": "OK",
            "Trigger": {
                "MetricName": "CPUUtilization",
                "Namespace": "AWS/EC2",
                "StatisticType": "Statistic",
                "Statistic": "AVERAGE",
                "Unit": "Percent",
                "Dimensions": [{"name": "InstanceId", "value": "i-abcdef1234567890"}],
                "Period": 300,
                "EvaluationPeriods": 1,
                "ComparisonOperator": "GreaterThanThreshold",
                "Threshold": 80.0,
                "TreatMissingData": "- TreatMissingData:                    NonBreaching",
                "EvaluateLowSampleCountPercentile": "",
                "Metrics": [
                    {
                        "Id": "m1",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "AWS/EC2",
                                "MetricName": "CPUUtilization",
                                "Dimensions": [{"name": "InstanceId", "value": "i-abcdef1234567890"}]
                            },
                            "Period": 60, # Shorter period for testing
                            "Stat": "Average",
                            "Unit": "Percent"
                        },
                        "ReturnData": True
                    }
                ]
            }
        }
        
        # Correct StateChangeTime format to match what AWS sends (with milliseconds and Z)
        # Example: 2023-03-15T10:30:00.123Z
        # For testing, let's use a fixed, correctly formatted string:
        state_change_time_str = "2024-01-01T10:00:00.000Z"
        # Re-parse to ensure it's a valid datetime object for calculations in lambda
        sns_message_payload["StateChangeTime"] = state_change_time_str.replace("Z", "+00:00")


        event = {
            "Records": [{
                "EventSource": "aws:sns",
                "Sns": {
                    "Message": json.dumps(sns_message_payload),
                    "Timestamp": "2024-01-01T10:00:00.000Z"
                }
            }]
        }

        # Call the handler
        response = lambda_handler(event, {})

        # Assertions
        self.assertEqual(response['statusCode'], 200)
        mock_pool_manager.return_value.request.assert_called_once()
        
        # Check Slack message payload
        args, kwargs = mock_pool_manager.return_value.request.call_args
        self.assertEqual(kwargs['method'], 'POST')
        self.assertEqual(kwargs['headers']['Content-Type'], 'application/json')
        
        slack_body = json.loads(kwargs['body'].decode('utf-8'))
        
        self.assertIn(sns_message_payload['AlarmName'], slack_body['blocks'][0]['text']['text'])
        self.assertIn(sns_message_payload['NewStateValue'], slack_body['blocks'][0]['text']['text'])
        
        context_text = slack_body['blocks'][1]['elements'][0]['text']
        self.assertIn(sns_message_payload['AlarmDescription'], context_text)
        self.assertIn("MyTestInstance", context_text) # Check if instance name is resolved
        self.assertIn("CPUUtilization", context_text)
        self.assertIn("100.0", context_text) # Metric value from get_metric_data mock

        # Verify that get_instance_name was called (implicitly by checking ec2.describe_instances)
        mock_ec2.describe_instances.assert_called_with(InstanceIds=['i-abcdef1234567890'])
        mock_cloudwatch.describe_alarm_history.assert_called_once_with(
            AlarmName=sns_message_payload['AlarmName'],
            HistoryItemType='StateUpdate',
            MaxRecords=3,
            ScanBy='TimestampDescending'
        )
        
        # Check if get_metric_data was called with correct parameters
        # We need to check the MetricDataQueries part carefully
        get_metric_data_call_args = mock_cloudwatch.get_metric_data.call_args[1] # kwargs
        self.assertEqual(len(get_metric_data_call_args['MetricDataQueries']), 1)
        query = get_metric_data_call_args['MetricDataQueries'][0]
        self.assertEqual(query['MetricStat']['Metric']['MetricName'], "CPUUtilization")
        self.assertEqual(query['MetricStat']['Metric']['Dimensions'][0]['Value'], "i-abcdef1234567890")

    @patch('lambda_function.os.getenv')
    def test_lambda_handler_missing_webhook_url(self, mock_os_getenv):
        # Mock os.getenv to return None for SLACK_WEBHOOK_URL
        mock_os_getenv.side_effect = lambda k, d=None: None if k == 'SLACK_WEBHOOK_URL' else self.mock_env_vars.get(k, d)

        event = {
            "Records": [{
                "Sns": {
                    "Message": json.dumps({
                        "AlarmName": "Test-Alarm",
                        "NewStateValue": "ALARM",
                        "StateChangeTime": "2024-01-01T10:00:00.000+00:00",
                        "Trigger": {"Metrics": []} # Add empty metrics to avoid other errors
                    })
                }
            }]
        }
        with self.assertRaisesRegex(ValueError, "환경 변수 'SLACK_WEBHOOK_URL'이 설정되지 않았습니다."):
            lambda_handler(event, {})

    @patch('lambda_function.os.getenv')
    @patch('lambda_function.boto3.client') # Mock boto3.client to avoid actual AWS calls
    def test_lambda_handler_malformed_state_change_time(self, mock_boto_client, mock_os_getenv):
        # Mock os.getenv to return a dummy webhook URL
        mock_os_getenv.side_effect = lambda k, d=None: self.mock_env_vars.get(k, d)
        
        # Mock CloudWatch client as it's initialized before StateChangeTime is parsed
        mock_cloudwatch = MagicMock()
        mock_boto_client.return_value = mock_cloudwatch

        event = {
            "Records": [{
                "Sns": {
                    "Message": json.dumps({
                        "AlarmName": "Test-Alarm-MalformedTime",
                        "NewStateValue": "ALARM",
                        "StateChangeTime": "2023-10-26T10:00:00Z-INVALID", # Malformed time
                        "Trigger": {"Metrics": []} 
                    })
                }
            }]
        }
        with self.assertRaisesRegex(ValueError, "StateChangeTime 포맷 오류:"):
            lambda_handler(event, {})


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
