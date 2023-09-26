import boto3
import logging
import time
import yaml
from datetime import datetime


logger = logging.getLogger()

class RDS:
    def __init__(self,json_alarm,validation, region_name):
        self.region_name = region_name
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=region_name)
        self.rds_client = boto3.client('rds', region_name=region_name)
        self.alarm_json_metrics=json_alarm
        self.validation=validation

    def get_rds_clusters(self, rds_tags):
        try:
            if isinstance(rds_tags, str):
                rds_tags = yaml.safe_load(rds_tags)

            response = self.rds_client.describe_db_clusters()

            db_clusters = response['DBClusters']

            rds_list = []

            for db_cluster in db_clusters:
            
                db_cluster_arn = db_cluster['DBClusterArn']
                engine = db_cluster['Engine']
                clustername = db_cluster['DBClusterIdentifier']

                engine = db_cluster['Engine']
                if engine=='aurora-mysql' or engine=='aurora-postgresql':
                    for db in db_cluster["DBClusterMembers"]:
                        if db["IsClusterWriter"]:
                            db_role = "WRITER"
                        else:
                            db_role = "READER"

                        db_cluster_tags = self.rds_client.list_tags_for_resource(ResourceName=db_cluster_arn)['TagList']

                        rds_tag_dict = {tag['Key']: tag['Value'] for tag in db_cluster_tags}

                        if len(rds_tags):
                            if all(rds_tag_dict.get(key) in values for key, values in rds_tags.items()):
                                cluster_dict = {'ResourceID': clustername, 'ResourceName': clustername, 'Engine':engine, 'DB_Role': db_role}
                                rds_list.append(cluster_dict)

                        else:
                            cluster_dict = {'ResourceID': clustername, 'ResourceName': clustername, 'Engine':engine, 'DB_Role': db_role}
                            rds_list.append(cluster_dict)

            return rds_list
        except Exception as e:
            logger.error("Error occurred while getting RDS instances: %s", str(e))
            return []


    def get_rds_instances(self, rds_tags):
        try:
            if isinstance(rds_tags, str):
                rds_tags = yaml.safe_load(rds_tags)

            response = self.rds_client.describe_db_instances()

            db_instances = response['DBInstances']
            rds_list = []

            for db_instance in db_instances:
                db_instance_arn = db_instance['DBInstanceArn']

                db_instance_tags = self.rds_client.list_tags_for_resource(ResourceName=db_instance_arn)['TagList']

                rds_tag_dict = {tag['Key']: tag['Value'] for tag in db_instance_tags}
                
                db_name = db_instance['DBInstanceIdentifier']
                engine = db_instance['Engine']

                if len(rds_tags):
                    if all(rds_tag_dict.get(key) in values for key, values in rds_tags.items()):
                        instance_dict = {'ResourceID': db_name, 'ResourceName': db_name, 'Engine':engine}
                        rds_list.append(instance_dict)
                else:

                    instance_dict = {'ResourceID': db_name, 'ResourceName': db_name, 'Engine':engine}
                    rds_list.append(instance_dict)

            return rds_list
        
        except Exception as e:
            logger.error("Error occurred while getting RDS instances: %s", str(e))
            return []

    def check_rds_alarms(self, instance_id, resource_name, alarms, engine):
        try:
            alarms_json = {}

            for metric, validation_alarm_configurations in alarms.items():
                alarms_json[metric] = []

                for alarm_configuration in validation_alarm_configurations:
                    threshold_alarms = []

                    if engine == "docdb":
                        namespace = "AWS/DocDB"
                    else:
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
                        validation = self.validation(alarm, alarm_configuration, alarmconfig, alarmname,resource_name,engine=engine,replica=False)

                        mismatch_reasons = []

                        if metric_name not in ['DatabaseConnections', 'FreeableMemory'] and alarm['Threshold'] != alarm_configuration['Threshold']:
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
                                self.alarm_json_metrics(alarm_configuration, alarms_json, metric,resource_name,engine=engine,replica=False)


            return alarms_json
        except Exception as e:
            logger.error("Error occurred while checking RDS alarms: %s", str(e))
            return {}


    def check_rds_alarms_for_cluster(self, clusterID, resource_name, alarms,replica):
        try:
            alarms_json = {}

            for metric, validation_alarm_configurations in alarms.items():
                alarms_json[metric] = []

                for alarm_configuration in validation_alarm_configurations:
                    threshold_alarms = []

                    namespace = "AWS/RDS"

                    metric_name = alarm_configuration['MetricName']
                    response = self.cloudwatch_client.describe_alarms_for_metric(
                        Dimensions=[
                                    {'Name': 'DBClusterIdentifier', 'Value': clusterID},
                                    {'Name': 'Role', 'Value': replica}
                            ],
                        MetricName=metric_name,
                        Namespace=namespace
                    )
                    
                    for alarm in response['MetricAlarms']:
                        alarmname = alarm['AlarmName']
                        alarmconfig = True
                        validation = self.validation(alarm, alarm_configuration, alarmconfig, alarmname,resource_name,engine=False, replica=replica)

                        mismatch_reasons = []

                        if metric_name not in ['DatabaseConnections', 'FreeableMemory'] and alarm['Threshold'] != alarm_configuration['Threshold']:
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
                                self.alarm_json_metrics(alarm_configuration, alarms_json, metric,resource_name,engine=False, replica=replica)
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
                        engine = alarm.get('Engine')
                        if validation and validation == 'fail':
                            self.create_rds_alarm(resource, metric_type, alarm, sns_action,prefix,engine)
                            any_alarm_created = True
            logger.info(" ")
            if not any_alarm_created:
                logger.info(f"All test cases passed for RDS. No alarms to create.")
                logger.info("")
                logger.info("*********************************************")
                logger.info("")
        except Exception as e:
            logger.error("Error occurred while creating alarms:", str(e))

    def create_rds_cluster_alarms_from_json(self,json_data,sns_action,prefix):
        try:
            any_alarm_created = False
            for resource, alarms in json_data.items():
                for metric_type, alarm_list in alarms.items():
                    for alarm in alarm_list:
                        validation = alarm.get('Validation')
                        replica = alarm.get('Replica')
                        if validation and validation == 'fail':
                            self.create_rds_cluster_alarm(resource, metric_type, alarm, sns_action,prefix,replica)
                            any_alarm_created = True
            logger.info(" ")
            if not any_alarm_created:
                logger.info(f"All test cases passed for RDS Cluster. No alarms to create.")
                logger.info("")
                logger.info("*********************************************")
                logger.info("")
        except Exception as e:
            logger.error("Error occurred while creating alarms:", str(e))

    def create_rds_alarm(self, resource, metric_name, alarm_configuration, sns_action,prefix,engine):
        try:
            resource_name = alarm_configuration['ResourceName']
            current_timestamp_ms = int(time.time() * 1000)

            if engine == "docdb":
                namespace = "AWS/DocDB"
            else:
                namespace = "AWS/RDS"  
            
            alarm_name = f"{prefix}|{namespace}|{resource_name}|{metric_name}|{datetime.now():%Y}|{current_timestamp_ms}" 

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


    def create_rds_cluster_alarm(self, resource, metric_name, alarm_configuration, sns_action,prefix,replica):
        try:
            resource_name = alarm_configuration['ResourceName']
            current_timestamp_ms = int(time.time() * 1000)

            namespace = "AWS/RDS"  
            
            alarm_name = f"{prefix}|{namespace}|{resource_name}-{replica}|{metric_name}|{datetime.now():%Y}|{current_timestamp_ms}" 

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
                Dimensions=[
                                    {'Name': 'DBClusterIdentifier', 'Value': resource_name},
                                    {'Name': 'Role', 'Value': replica}
                            ],
                DatapointsToAlarm=alarm_configuration['DatapointsToAlarm'],
                TreatMissingData=alarm_configuration['TreatMissingData']
            )
            logger.info("Alarm created successfully for RDS Cluster: %s", alarm_name)
        except Exception as e:
            logger.error("Error occurred while creating an alarm for RDS Cluster: %s", resource)
            logger.error("Error details: %s", str(e))   

