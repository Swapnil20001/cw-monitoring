import boto3
import yaml
import logging
import sys
import xlsxwriter
from datetime import datetime
from ec2 import EC2
from rds import RDS
from Lambda import Lambda
from alb import ALB


logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
logger.addHandler(handler)

class ServicesAlarmChecker:
    def __init__(self, region_name):
        self.obj_ec2 = EC2(self.alarm_json_metrics,self.validation,region_name=region_name)
        self.obj_rds = RDS(self.alarm_json_metrics,self.validation,region_name=region_name)
        self.obj_lambda = Lambda(self.alarm_json_metrics,self.validation,region_name=region_name)
        self.obj_alb = ALB(self.alarm_json_metrics,self.validation,region_name=region_name)
        self.region_name=region_name

    def alarm_json_metrics(self, alarm_configuration, alarms_json, metric, resource_name):
        alarms_json[metric].append({
            'alarmname': ' ',
            'alarmconfig': False,
            'Validation': 'fail',
            'Reason': 'alarm not configured',
            'ResourceName': resource_name, 
            'MetricName': alarm_configuration['MetricName'],    
            'Threshold': alarm_configuration['Threshold'],
            'DatapointsToAlarm': alarm_configuration['DatapointsToAlarm'],
            'Period': alarm_configuration['Period'],
            'EvaluationPeriods': alarm_configuration['EvaluationPeriods'],
            'Statistic': alarm_configuration['Statistic'],
            'ComparisonOperator': alarm_configuration['ComparisonOperator'],
            'TreatMissingData': alarm_configuration['TreatMissingData'],
            'AlarmDescription': alarm_configuration['AlarmDescription'],
            'AlarmThreshold': ' ',
            'AlarmDatapointsToAlarm': ' ',
            'AlarmPeriod': ' ',
            'AlarmEvaluationPeriods': ' ',
            'AlarmStatistic': ' ',
            'AlarmComparisonOperator': ' ',
            'AlarmTreatMissingData': ' ',
        })

    def validation(self, alarm, alarm_configuration, alarmconfig, alarmname,resource_name):
        validation = {
            'alarmname': alarmname,
            'alarmconfig': alarmconfig,
            'Validation': 'pass',
            'Reason': 'Success',
            'ResourceName': resource_name, 
            'MetricName': alarm_configuration['MetricName'],
            'Threshold': alarm_configuration['Threshold'],
            'DatapointsToAlarm': alarm_configuration['DatapointsToAlarm'],
            'Period': alarm_configuration['Period'],
            'EvaluationPeriods': alarm_configuration['EvaluationPeriods'],
            'Statistic': alarm_configuration['Statistic'],
            'ComparisonOperator': alarm_configuration['ComparisonOperator'],
            'TreatMissingData': alarm_configuration['TreatMissingData'],
            'AlarmDescription': alarm_configuration['AlarmDescription'],
            'AlarmThreshold': alarm['Threshold'],
            'AlarmDatapointsToAlarm': alarm['DatapointsToAlarm'],
            'AlarmPeriod': alarm['Period'],
            'AlarmEvaluationPeriods': alarm['EvaluationPeriods'],
            'AlarmStatistic': alarm['Statistic'],
            'AlarmComparisonOperator': alarm['ComparisonOperator'],
            'AlarmTreatMissingData': alarm['TreatMissingData']
        }
        return validation


    def read_yaml_input(self, file_path):
        try:
            with open(file_path, 'r') as f:
                input_data = yaml.safe_load(f)

            return input_data
        except Exception as e:
            logger.error("Error occurred while reading YAML input: %s", str(e))
            return {}

    def separate_services(self, input_data):
        try:
            service_dict = {}

            for service_key, validation_alarm_configurations in input_data['service'].items():
                service_dict[service_key] = validation_alarm_configurations

            return service_dict
        except Exception as e:
            logger.error("Error occurred while separating services: %s", str(e))
            return {}

    def get_service_info(self, service_type, instance_id, resource_name, metrics):
        if service_type == 'EC2':
            return self.obj_ec2.check_ec2_alarms(instance_id, resource_name, metrics)
        elif service_type == 'RDS':
            return self.obj_rds.check_rds_alarms(instance_id, resource_name, metrics)
        elif service_type == 'Lambda':
            return self.obj_lambda.check_lambda_alarms(instance_id, resource_name, metrics)
        elif service_type == 'ALB':
            return self.obj_alb.check_alb_alarms(instance_id, resource_name, metrics)
        else:
            logger.error("Invalid service name: %s", service_type)
            return {}


    def generate_yaml_reports(self, resources_data, instance_dict, check_alarms_func):
        result = {}
        for resource in resources_data:
            resource_id = resource['ResourceID']
            resource_name = resource['ResourceName']

            result[resource_id] = check_alarms_func(resource_id,resource_name, instance_dict)

        return result


    def print_yaml_data(self, yaml_data_str):
        logger.info(yaml_data_str)


    def custom_service_input(self, service_name, service_data):
        output_data = {service_name: {}}
        
        for service_type, instances in service_data.items():
            output_data[service_name][service_type] = {}

            for instance_id, metrics in instances.items():
                for resource in metrics.values():
                    resource_name = resource[0]['ResourceName']
                    service_info = self.get_service_info(service_type, instance_id, resource_name, metrics)

                    instance_service_data = {
                        metric: service_info[metric] for metric in metrics
                    }

                    output_data[service_name][service_type][instance_id] = instance_service_data

        output_yaml = yaml.dump(output_data, sort_keys=False)
        return output_yaml

    def excel_sheet(self, report_data, custom_services_data, file_name):
        workbook = xlsxwriter.Workbook(file_name)
        bold_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter'})
        center_format = workbook.add_format({'align': 'center', 'valign': 'vcenter'})

        for service_name, data in report_data.items():
            worksheet = workbook.add_worksheet(service_name)

            headers = ['Resource Name','ResourceID', 'Metric', 'Alarm Name', 'Validation', "Reason", 'Threshold', 'AlarmThreshold','DatapointsToAlarm', 'AlarmDatapointsToAlarm', 
                    "EvaluationPeriods", 'AlarmEvaluationPeriods', 'Period', 'AlarmPeriod', 'ComparisonOperator', 'AlarmComparisonOperator', 'Statistic', 'AlarmStatistic', 'TreatMissingData', 'AlarmTreatMissingData']

            for col, header in enumerate(headers):
                worksheet.write(0, col, header, bold_format)

            row = 1
            for instance_id, metrics in data.items():
                for metric, alarms in metrics.items():
                    for alarm in alarms:
                        col = 0  
                        for value in [alarm['ResourceName'],instance_id, metric, alarm['alarmname'], alarm['Validation'], alarm['Reason'],
                                    alarm['Threshold'], alarm['AlarmThreshold'], alarm['DatapointsToAlarm'], alarm['AlarmDatapointsToAlarm'],
                                    alarm['EvaluationPeriods'], alarm['AlarmEvaluationPeriods'], alarm['Period'], alarm['AlarmPeriod'],
                                    alarm['ComparisonOperator'], alarm['AlarmComparisonOperator'], alarm['Statistic'], alarm['AlarmStatistic'],
                                    alarm['TreatMissingData'], alarm['AlarmTreatMissingData']]:
                            worksheet.write(row, col, value, center_format)
                            col += 1
                        row += 1

        if custom_services_data:
            custom_sheet = workbook.add_worksheet('Custom Resources')

            custom_headers = ['Resource Type','Resource Name','ResourceID', 'Metric', 'Alarm Name', 'Validation', "Reason", 'Threshold', 'AlarmThreshold',
                            'DatapointsToAlarm', 'AlarmDatapointsToAlarm', "EvaluationPeriods", 'AlarmEvaluationPeriods', 'Period',
                            'AlarmPeriod', 'ComparisonOperator', 'AlarmComparisonOperator', 'Statistic', 'AlarmStatistic',
                            'TreatMissingData', 'AlarmTreatMissingData']

            for col, header in enumerate(custom_headers):
                custom_sheet.write(0, col, header, bold_format)

            custom_row = 1
            for resource_type, instances in custom_services_data.items():
                for instance_id, metrics in instances.items():
                    for metric, alarms in metrics.items():
                        for alarm in alarms:
                            col = 0  
                            for value in [resource_type,alarm['ResourceName'],instance_id, metric, alarm['alarmname'], alarm['Validation'], alarm['Reason'],
                                        alarm['Threshold'], alarm['AlarmThreshold'], alarm['DatapointsToAlarm'], alarm['AlarmDatapointsToAlarm'],
                                        alarm['EvaluationPeriods'], alarm['AlarmEvaluationPeriods'], alarm['Period'], alarm['AlarmPeriod'],
                                        alarm['ComparisonOperator'], alarm['AlarmComparisonOperator'], alarm['Statistic'], alarm['AlarmStatistic'],
                                        alarm['TreatMissingData'], alarm['AlarmTreatMissingData']]:
                                custom_sheet.write(custom_row, col, value, center_format)
                                col += 1
                            custom_row += 1

        workbook.close()
        logger.info(f"{file_name} created successfully.")


    def main(self):
        try:
            while True:
                logger.info("Select an option:")
                logger.info("1. Generate report for alarm validation")
                logger.info("2. Create missing alarms")
                logger.info("3. Exit")
                choice = input("Enter your choice: ")

                file_path = 'input.yaml'
                input_data = self.read_yaml_input(file_path)
                
                prefix = input_data.get('prefix')

                service_dict = self.separate_services(input_data)

                ec2_dict = service_dict.get('EC2')
                rds_dict = service_dict.get('RDS')
                lambda_dict = service_dict.get('Lambda')
                alb_dict = service_dict.get('ALB')

                ec2_tags = input_data.get('Tags', {}).get('ec2_tag', [])
                rds_tags = input_data.get('Tags', {}).get('rds_tag', [])
                alb_tags = input_data.get('Tags', {}).get('alb_tag', [])
                
                sns_action = input_data.get('sns_action', []) 


                instance_ids = self.obj_ec2.get_instance_ids(ec2_tags)

                rds_instances = self.obj_rds.get_rds_instances(rds_tags)

                lambda_functions = self.obj_lambda.get_lambda_functions()

                alb = self.obj_alb.get_albs(alb_tags)
                
                ec2_report_data = {}
                rds_report_data = {}
                lambda_report_data = {}
                alb_report_data = {}

                if choice == '1':
                    logger.info("EC2 Instance IDs with given tags: %s", instance_ids)
                    logger.info("RDS Instances with given tags: %s", rds_instances)
                    logger.info("Lambda Functions: %s", lambda_functions)
                    logger.info("ApplicationLB_ARN: %s", alb)
                    logger.info('')

                    if ec2_dict:
                        ec2_report_data = self.generate_yaml_reports(instance_ids, ec2_dict, self.obj_ec2.check_ec2_alarms)

                        ec2_yaml_data_str = yaml.dump({'service': {'EC2': ec2_report_data}}, sort_keys=False)

                        self.print_yaml_data(ec2_yaml_data_str)

                    if rds_dict:
                        rds_report_data = self.generate_yaml_reports(rds_instances, rds_dict, self.obj_rds.check_rds_alarms)

                        rds_yaml_data_str = yaml.dump({'service': {'RDS': rds_report_data}}, sort_keys=False)

                        self.print_yaml_data(rds_yaml_data_str)

                    if lambda_dict:
                        lambda_report_data = self.generate_yaml_reports(lambda_functions, lambda_dict, self.obj_lambda.check_lambda_alarms)

                        lambda_yaml_data_str = yaml.dump({'service': {'Lambda': lambda_report_data}}, sort_keys=False)

                        self.print_yaml_data(lambda_yaml_data_str)            

                    if alb_dict:
                        alb_report_data = self.generate_yaml_reports(alb, alb_dict, self.obj_alb.check_alb_alarms)

                        alb_yaml_data_str = yaml.dump({'service': {'ALB': alb_report_data}}, sort_keys=False)

                        self.print_yaml_data(alb_yaml_data_str)

                    combined_report_data = {}
                    if ec2_report_data:
                        combined_report_data['EC2'] = ec2_report_data
                    if rds_report_data:
                        combined_report_data['RDS'] = rds_report_data
                    if lambda_report_data:
                        combined_report_data['Lambda'] = lambda_report_data
                    if alb_report_data:
                        combined_report_data['ALB'] = alb_report_data

                    service_name = 'Resources'
                    service_data = input_data.get(service_name, {})

                    custom_services_data = {}

                    if service_data:
                        output_custom_services = self.custom_service_input(service_name, service_data)
                        custom_services_data = yaml.safe_load(output_custom_services)['Resources']
                        
                        logger.info("***************************************")

                        logger.info(output_custom_services)

                        if 'Resources' in custom_services_data:
                            combined_report_data.update(custom_services_data['Resources'])

                    
                    filename = f'CW-Monitoring_{datetime.now():%Y-%m-%d}.xlsx'
                    if combined_report_data:
                        self.excel_sheet(combined_report_data, custom_services_data, filename)
                    
                    logger.info(" ")

                elif choice == '2':

                    ec2_json = self.generate_yaml_reports(instance_ids, ec2_dict, self.obj_ec2.check_ec2_alarms)

                    rds_json = self.generate_yaml_reports(rds_instances, rds_dict, self.obj_rds.check_rds_alarms)

                    lambda_json = self.generate_yaml_reports(lambda_functions, lambda_dict, self.obj_lambda.check_lambda_alarms)

                    alb_json = self.generate_yaml_reports(alb, alb_dict, self.obj_alb.check_alb_alarms)

                    self.obj_ec2.create_ec2_alarms_from_json(ec2_json,sns_action,prefix)
                    self.obj_rds.create_rds_alarms_from_json(rds_json, sns_action,prefix)
                    self.obj_lambda.create_lambda_alarms_from_json(lambda_json, sns_action,prefix)
                    self.obj_alb.create_alb_alarms_from_json(alb_json,sns_action,prefix)


                    service_name = 'Resources'
                    service_data = input_data.get(service_name, {})

                    custom_services_data = {}

                    if service_data:
                        output_custom_services = self.custom_service_input(service_name, service_data)

                        custom_services_data = yaml.safe_load(output_custom_services)['Resources']

                        if custom_services_data:
                            custom_ec2 = custom_services_data.get('EC2', {})
                            custom_alb = custom_services_data.get('ALB', {})
                            custom_rds = custom_services_data.get('RDS', {})
                            custom_lambda = custom_services_data.get('Lambda', {})


                            logger.info("Creating alarms for custom resources")
                            logger.info(" ")

                            if custom_ec2:
                                self.obj_ec2.create_ec2_alarms_from_json(custom_ec2,sns_action,prefix)

                            if custom_alb:
                                self.obj_alb.create_alb_alarms_from_json(custom_alb, sns_action,prefix)

                            if custom_rds:
                                self.obj_rds.create_rds_alarms_from_json(custom_rds, sns_action,prefix)

                            if custom_lambda:
                                self.obj_lambda.create_lambda_alarms_from_json(custom_lambda, sns_action,prefix)

                    logger.info(" ")

                elif choice == '3':
                    logger.info("Exiting...")
                    break
                else:
                    logger.info("Invalid choice. Please try again.")

        except Exception as e:
            logger.error("Error occurred in the main function: %s", str(e))


region_name = input("Enter the region: ")   
alarm_checker = ServicesAlarmChecker(region_name)
alarm_checker.main()