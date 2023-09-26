import boto3
import logging
import time
from datetime import datetime

logger = logging.getLogger()

class EC2:
    def __init__(self,json_alarm,validation,region_name):
        self.region_name = region_name
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=region_name)
        self.ec2_client = boto3.client('ec2', region_name=self.region_name)
        self.paginator = self.ec2_client.get_paginator('describe_instances')
        self.alarm_json_metrics=json_alarm
        self.validation=validation


    def get_instance_ids(self, ec2_tags):
        try:
            filters = []
            if (len(ec2_tags)):
                for key, values in ec2_tags.items():
                    values_list = values if isinstance(values, list) else [values]
                    tag_filters = {'Name': f'tag:{key}', 'Values': values_list}
                    filters.append(tag_filters)
                
                reservations = self.ec2_client.describe_instances(Filters=filters).get('Reservations', [])
            else:
                reservations = self.ec2_client.describe_instances().get('Reservations', [])

            instances = sum([[i for i in r['Instances']] for r in reservations], [])

            instance_data = []
            for instance in instances:
                instance_id = instance['InstanceId']
                instance_tags = instance.get('Tags', [])
                instance_name = next((tag['Value'] for tag in instance_tags if tag['Key'] == 'Name'), None)
                if instance_name:
                    instance_data.append({'ResourceID': instance_id, 'ResourceName': instance_name})

            return instance_data
        
        except Exception as e:
            logger.error("Error occurred while getting EC2 instance IDs: %s", str(e))
            return []
        

    def check_ec2_alarms(self, instance_id,resource_name, alarms):
        try:
            alarms_json = {}

            for metric, validation_alarm_configurations in alarms.items():
                alarms_json[metric] = []

                for alarm_configuration in validation_alarm_configurations:
                    threshold_alarms = []

                    if metric in ['Memory', 'Disk']:
                        namespace = 'CWAgent'
                    else:
                        namespace = 'AWS/EC2'

                    metric_name = alarm_configuration['MetricName']
                    response = self.cloudwatch_client.describe_alarms_for_metric(
                        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
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
                        # self.alarm_json_metrics(alarm_configuration, alarms_json, metric, resource_name)

            return alarms_json
        except Exception as e:
            logger.error("Error occurred while checking EC2 alarms: %s", str(e))
            return {}
        
    def create_ec2_alarms_from_json(self,json_data, sns_action,prefix):
        try:
            any_alarm_created = False
            for resource, alarms in json_data.items():
                for metric_type, alarm_list in alarms.items():
                    for alarm in alarm_list:
                        validation = alarm.get('Validation')
                        if validation and validation == 'fail':
                            self.create_ec2_alarm(resource, metric_type, alarm, sns_action,prefix)
                            any_alarm_created = True
 
            logger.info(" ")
            if not any_alarm_created:
                logger.info(f"All test cases passed for EC2. No alarms to create.")
                logger.info("")
                logger.info("*********************************************")
                logger.info("")
        except Exception as e:
            logger.error("Error occurred while creating alarms:", str(e))
        
    def create_ec2_alarm(self, resource, metric_name, alarm_configuration, sns_action,prefix):
        try:
            resource_name = alarm_configuration['ResourceName']
            current_timestamp_ms = int(time.time() * 1000)
            alarm_name = f"{prefix}|AWS/EC2|{resource}({resource_name})|{metric_name}|{datetime.now():%Y}|{current_timestamp_ms}"     

            if metric_name in ['Memory', 'Disk']:
                namespace = 'CWAgent'
            else:
                namespace = 'AWS/EC2'
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
                Dimensions=[{'Name': 'InstanceId', 'Value': resource}],
                DatapointsToAlarm=alarm_configuration['DatapointsToAlarm'],
                TreatMissingData=alarm_configuration['TreatMissingData']
            )
            logger.info("Alarm created successfully for instance: %s", alarm_name)
        except Exception as e:
            logger.error("Error occurred while creating an alarm for instance: %s", resource)
            logger.error("Error details: %s", str(e))