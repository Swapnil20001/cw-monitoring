import boto3
import logging
import time
from datetime import datetime


logger = logging.getLogger()

class RDS:
    def __init__(self,json_alarm,validation, region_name):
        self.region_name = region_name
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=region_name)
        self.rds_client = boto3.client('rds', region_name=region_name)
        self.alarm_json_metrics=json_alarm
        self.validation=validation


    def get_rds_instances(self, rds_tags):
        try:
            response = self.rds_client.describe_db_instances()

            db_instances = response['DBInstances']
            # print(rds_tags)
            rds_list = []

            for db_instance in db_instances:
                db_instance_arn = db_instance['DBInstanceArn']
                db_instance_tags = self.rds_client.list_tags_for_resource(ResourceName=db_instance_arn)['TagList']

                rds_tag_dict = {tag['Key']: tag['Value'] for tag in db_instance_tags}

                for tags_json in rds_tags:
                    if all(rds_tag_dict.get(key) == value for key, value in tags_json.items()):

                        db_name = db_instance['DBInstanceIdentifier']

                        instance_dict = {'ResourceID': db_name, 'ResourceName': db_name}
                        rds_list.append(instance_dict)
            return rds_list
        
        except Exception as e:
            logger.error("Error occurred while getting RDS instances: %s", str(e))
            return []

    def check_rds_alarms(self, instance_id, resource_name, alarms):
        try:
            alarms_json = {}

            for metric, validation_alarm_configurations in alarms.items():
                alarms_json[metric] = []

                for alarm_configuration in validation_alarm_configurations:
                    threshold_alarms = []

                    namespace = "AWS/RDS"

                    metric_name = alarm_configuration['MetricName']
                    response = self.cloudwatch_client.describe_alarms_for_metric(
                        Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': instance_id}],
                        MetricName=metric_name,
                        Namespace=namespace
                    )

                    for alarm in response['MetricAlarms']:
                        alarmname = alarm['AlarmName']
                        alarmconfig = True
                        validation = self.validation(alarm, alarm_configuration, alarmconfig, alarmname,resource_name)

                        mismatch_reasons = []
                        if (
                            alarm['Threshold'] != alarm_configuration['Threshold'] or
                            alarm['DatapointsToAlarm'] != alarm_configuration['DatapointsToAlarm'] or
                            alarm['Period'] != alarm_configuration['Period'] or
                            alarm['EvaluationPeriods'] != alarm_configuration['EvaluationPeriods'] or
                            alarm['Statistic'] != alarm_configuration['Statistic'] or
                            alarm['ComparisonOperator'] != alarm_configuration['ComparisonOperator'] or
                            alarm['TreatMissingData'] != alarm_configuration['TreatMissingData']
                        ):
                            validation['Validation'] = 'fail'
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

                            validation['Reason'] = ', '.join(mismatch_reasons) + " not matched"

                        threshold_alarms.append(validation)

                    pass_found = any(a['Validation'] == 'pass' for a in threshold_alarms)

                    if pass_found:
                        alarms_json[metric].extend(a for a in threshold_alarms if a['Validation'] == 'pass')
                    else:
                        alarms_json[metric].extend(threshold_alarms)

                    if not response['MetricAlarms']:
                                self.alarm_json_metrics(alarm_configuration, alarms_json, metric,resource_name)

            return alarms_json
        except Exception as e:
            logger.error("Error occurred while checking RDS alarms: %s", str(e))
            return {}

    def create_rds_alarms_from_json(self,json_data,sns_action,prefix):
        try:
            any_alarm_created = False
            for resource, alarms in json_data.items():
                for metric_type, alarm_list in alarms.items():
                    for alarm in alarm_list:
                        validation = alarm.get('Validation')
                        if validation and validation == 'fail':
                            self.create_rds_alarm(resource, metric_type, alarm, sns_action,prefix)
                            any_alarm_created = True
            logger.info(" ")
            if not any_alarm_created:
                logger.info(f"All test cases passed for RDS. No alarms to create.")
                logger.info("")
                logger.info("*********************************************")
                logger.info("")
        except Exception as e:
            logger.error("Error occurred while creating alarms:", str(e))

    def create_rds_alarm(self, resource, metric_name, alarm_configuration, sns_action,prefix):
        try:
            resource_name = alarm_configuration['ResourceName']
            current_timestamp_ms = int(time.time() * 1000)
            alarm_name = f"{prefix}/AWS-RDS/{resource}({resource_name})/{metric_name}-Critical/{datetime.now():%Y}/{current_timestamp_ms}"   

            namespace = "AWS/RDS"
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
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': resource}],
                DatapointsToAlarm=alarm_configuration['DatapointsToAlarm'],
                TreatMissingData=alarm_configuration['TreatMissingData']
            )
            logger.info("Alarm created successfully for RDS instance: %s", alarm_name)
        except Exception as e:
            logger.error("Error occurred while creating an alarm for RDS instance: %s", resource)
            logger.error("Error details: %s", str(e))