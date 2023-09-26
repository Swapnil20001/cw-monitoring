{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "rds:DescribeDBInstances",
                "rds:ListTagsForResource",
                "lambda:ListFunctions",
                "lambda:Get*",
                "lambda:list*",
                "elasticloadbalancing:Describe*",
                "elasticloadbalancing:describe*",
                "cloudwatch:DescribeAlarmsForMetric",
                "cloudwatch:describe*",
                "cloudwatch:list*",
                "ecs:list*",
                "ecs:ListTagsForResource"
            ],
            "Resource": "*"
        }
    ]
}