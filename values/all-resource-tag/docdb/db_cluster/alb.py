import boto3
import logging
import time
import yaml
from datetime import datetime

logger = logging.getLogger()

class ALB:
    def __init__(self,json_alarm,validation, region_name):
        self.region_name = region_name
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=region_name)
        
        self.elb_client = boto3.client('elbv2',region_name=region_name)
        self.alarm_json_metrics=json_alarm
        self.validation=validation

    def get_albs(self, alb_tag_input):
        try:
            response = self.elb_client.describe_load_balancers()
            load_balancer_arns = [lb['LoadBalancerArn'] for lb in response['LoadBalancers']]
            arn_list = []
            final_alb_list = []

            if isinstance(alb_tag_input, str):
                alb_tag_input = yaml.safe_load(alb_tag_input)
            
            if len(alb_tag_input):
                for alb in load_balancer_arns:
                    alb_lb = alb.split('/')[1]
                    if alb_lb == 'app':
                        alb_tags = self.elb_client.describe_tags(ResourceArns=[alb])['TagDescriptions'][0]['Tags']

                        tag_dict = {tag['Key']: tag['Value'] for tag in alb_tags}

                        if all(tag_dict.get(key) in values for key, values in alb_tag_input.items()):
                            arn_list.append(alb)
            else:
                for alb in load_balancer_arns:
                    alb_lb = alb.split('/')[1]
                    if alb_lb == 'app':

                        arn_list.append(alb)

            for alb_arn in arn_list:
                resource_arn = alb_arn[alb_arn.index("/") + 1:]
                resource_name = alb_arn.split('/')[-2]
                alb_info = {'ResourceID': resource_arn, 'ResourceName': resource_name}
                final_alb_list.append(alb_info)

            return final_alb_list
        except Exception as e:
            logger.error("Error occurred while separating services: %s", str(e))
            return {}

    def check_alb_alarms(self, alb,resource_name, alarms):
        try:
            alarms_json = {}

            for metric, validation_alarm_configurations in alarms.items():
                alarms_json[metric] = []

                for alarm_configuration in validation_alarm_configurations:
                    threshold_alarms = []

                    namespace = 'AWS/ApplicationELB'
                    metric_name = alarm_configuration['MetricName']
                    response = self.cloudwatch_client.describe_alarms_for_metric(
                        Dimensions=[{'Name': 'LoadBalancer', 'Value': alb}],
                        MetricName=metric_name,
                        Namespace=namespace
                    )

                    for alarm in response['MetricAlarms']:
                        alarmname = alarm['AlarmName']
                        alarmconfig = True
                        validation = self.validation(alarm, alarm_configuration, alarmconfig, alarmname,resource_name,engine=False, replica=False)
                        # validation = self.validation(alarm, alarm_configuration, alarmconfig, alarmname,resource_name)

                        mismatch_reasons = []

                        if metric_name not in ['RequestCount'] and alarm['Threshold'] != alarm_configuration['Threshold']:
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
                        self.alarm_json_metrics(alarm_configuration, alarms_json, metric, resource_name,engine=False, replica=False)
                        # self.alarm_json_metrics(alarm_configuration, alarms_json, metric, resource_name)

            return alarms_json
        except Exception as e:
            logger.error("Error occurred while checking Lambda alarms: %s", str(e))
            return {}

    def create_alb_alarm(self, resource, metric_name, alarm_configuration,sns_action,prefix):
        try:
            resource_name = alarm_configuration['ResourceName']
            current_timestamp_ms = int(time.time() * 1000)
            alarm_name = f"{prefix}|AWS/ALB|{resource_name}|{metric_name}|{datetime.now():%Y}|{current_timestamp_ms}"     
        
            namespace = "AWS/ApplicationELB"
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
                Dimensions=[{'Name': 'LoadBalancer', 'Value': resource}],
                DatapointsToAlarm=alarm_configuration['DatapointsToAlarm'],
                TreatMissingData=alarm_configuration['TreatMissingData']
            )
            logger.info("Alarm created successfully for alb: %s", alarm_name)
        except Exception as e:
            logger.error("Error occurred while creating an alarm for alb: %s", resource)
            logger.error("Error details: %s", str(e))


    def create_alb_alarms_from_json(self,json_data,sns_action,prefix):
        try:
            any_alarm_created = False
            for resource, alarms in json_data.items():
                for metric_type, alarm_list in alarms.items():
                    for alarm in alarm_list:
                        validation = alarm.get('Validation')
                        if validation and validation == 'fail':
                            self.create_alb_alarm(resource, metric_type, alarm, sns_action,prefix)
                            any_alarm_created = True
            logger.info(" ")
            if not any_alarm_created:
                logger.info(f"All test cases passed for alb. No alarms to create.")
                logger.info("")
                logger.info("*********************************************")
                logger.info("")
        except Exception as e:
            logger.error("Error occurred while creating alarms:", str(e))