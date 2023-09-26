import boto3
import logging
import time
from datetime import datetime

logger = logging.getLogger()

class Lambda:
    def __init__(self,json_alarm,validation,region_name):
        self.region_name = region_name
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=region_name)
        self.lambda_client = boto3.client('lambda', region_name=region_name)
        self.alarm_json_metrics=json_alarm
        self.validation=validation

    def get_lambda_functions(self):
        try:
            response = self.lambda_client.list_functions()

            functions = response['Functions']
            lambda_functions = []

            for function in functions:
                function_name = function['FunctionName']
                instance_dict = {'ResourceID': function_name, 'ResourceName': function_name}
                lambda_functions.append(instance_dict)

            return lambda_functions
        except Exception as e:
            logger.error("Error occurred while getting Lambda functions: %s", str(e))
            return []


    def check_lambda_alarms(self, function_name, resource_name, alarms):
        try:
            alarms_json = {}

            for metric, validation_alarm_configurations in alarms.items():
                alarms_json[metric] = []

                for alarm_configuration in validation_alarm_configurations:
                    threshold_alarms = []

                    namespace = 'AWS/Lambda'
                    metric_name = alarm_configuration['MetricName']
                    response = self.cloudwatch_client.describe_alarms_for_metric(
                        Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                        MetricName=metric_name,
                        Namespace=namespace
                    )

                    for alarm in response['MetricAlarms']:
                        alarmname = alarm['AlarmName']
                        alarmconfig = True
                        validation = self.validation(alarm, alarm_configuration, alarmconfig, alarmname,resource_name,engine=False, replica=False)
                        # validation = self.validation(alarm, alarm_configuration, alarmconfig, alarmname,resource_name)

                        mismatch_reasons = []
                        if alarm['Threshold'] != alarm_configuration['Threshold']:
                            mismatch_reasons.append('Threshold')
                        if alarm['DatapointsToAlarm'] != alarm_configuration['DatapointsToAlarm']:
                            mismatch_reasons.append('Datapoints')
                        if alarm['Period'] != alarm_configuration['Period']:
                            mismatch_reasons.append('Period')
                        if alarm['EvaluationPeriods'] != alarm_configuration['EvaluationPeriods']:
                            mismatch_reasons.append('Evaluation Periods')
                        if alarm['Statistic'] != alarm_configuration['Statistic']:
                            mismatch_reasons.append('Statistic')
                        if alarm['ComparisonOperator'] != alarm_configuration['ComparisonOperator']:
                            mismatch_reasons.append('Comparison Operator')
                        if alarm['TreatMissingData'] != alarm_configuration['TreatMissingData']:
                            mismatch_reasons.append('Treat Missing Data')

                        if mismatch_reasons:
                            validation['Validation'] = 'fail'
                            validation['Reason'] = ', '.join(mismatch_reasons) + " not matched"

                        threshold_alarms.append(validation)

                    pass_found = any(a['Validation'] == 'pass' for a in threshold_alarms)

                    if pass_found:
                        alarms_json[metric].extend(a for a in threshold_alarms if a['Validation'] == 'pass')
                    else:
                        alarms_json[metric].extend(threshold_alarms)

                    if not response['MetricAlarms']:
                        self.alarm_json_metrics(alarm_configuration, alarms_json, metric,resource_name,engine=False, replica=False)
                        # self.alarm_json_metrics(alarm_configuration, alarms_json, metric,resource_name)   

            return alarms_json
        except Exception as e:
            logger.error("Error occurred while checking Lambda alarms: %s", str(e))
            return {}

    def create_lambda_alarm(self, resource, metric_name, alarm_configuration, sns_action, prefix):
        try:
            resource_name = alarm_configuration['ResourceName']
            current_timestamp_ms = int(time.time() * 1000)
            alarm_name = f"{prefix}|AWS-LAMBDA|{resource_name}|{metric_name}|{datetime.now():%Y}|{current_timestamp_ms}"     
     
            namespace = "AWS/Lambda"
            response = self.cloudwatch_client.put_metric_alarm(
                AlarmName=alarm_name,
                ComparisonOperator=alarm_configuration['ComparisonOperator'],
                EvaluationPeriods=alarm_configuration['EvaluationPeriods'],
                MetricName=alarm_configuration['MetricName'],
                Namespace=namespace,
                Period=alarm_configuration['Period'],
                Statistic=alarm_configuration['Statistic'],
                Threshold=alarm_configuration['Threshold'],
                ActionsEnabled=True,
                AlarmActions=sns_action,
                AlarmDescription=alarm_configuration['AlarmDescription'],
                Dimensions=[{'Name': 'FunctionName', 'Value': resource}],
                DatapointsToAlarm=alarm_configuration['DatapointsToAlarm'],
                TreatMissingData=alarm_configuration['TreatMissingData']
            )
            logger.info("Alarm created successfully for Lambda function: %s", alarm_name)
        except Exception as e:
            logger.error("Error occurred while creating an alarm for Lambda function: %s", resource)
            logger.error("Error details: %s", str(e))

    def create_lambda_alarms_from_json(self,json_data, sns_action,prefix):
        try:
            any_alarm_created = False
            for resource, alarms in json_data.items():
                for metric_type, alarm_list in alarms.items():
                    for alarm in alarm_list:
                        validation = alarm.get('Validation')
                        if validation and validation == 'fail':
                            self.create_lambda_alarm(resource, metric_type, alarm, sns_action,prefix)
                            any_alarm_created = True
            logger.info(" ")
            if not any_alarm_created:
                logger.info(f"All test cases passed for lambda. No alarms to create.")
                logger.info("")
                logger.info("*********************************************")
                logger.info("")
        except Exception as e:
            logger.error("Error occurred while creating alarms:", str(e))   