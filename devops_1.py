#!/usr/bin/env python3

import boto3
import webbrowser
import os 
import subprocess
import random 
import string
import json
import time

ec2 = boto3.resource('ec2')
ec2Client = boto3.client('ec2')

s3 = boto3.resource('s3')
s3Client = boto3.client('s3')

SecGroups = ec2Client.describe_security_groups()

security_group_name = 'Assignment1Group'
security_group_exists = False

# Check if the security group already exists
for group in SecGroups['SecurityGroups']:
    if group['GroupName'] == security_group_name:
        print('Security Group already exists - Using this instead of creating a new one')
        security_group_exists = True
        break
        
# If the security group does not exist, create a new one
if not security_group_exists:
    DevOpsAssignment1 = ec2.create_security_group(
        GroupName=security_group_name,
        Description='SSH and HTTP access across all IPs'
    )
    print("Creating new group: ", security_group_name)
    # Making machine accessible from anywhere on port 22 and 80
    DevOpsAssignment1.authorize_ingress(
        IpPermissions=[
            {
                'IpProtocol': 'tcp',
                'FromPort': 22,
                'ToPort': 22,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            },
            {
               'IpProtocol': 'tcp',
               'FromPort': 80,
               'ToPort': 80,
               'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            }
        ]
    )
    print("\nPermissions for HTTP and SSH access set.\n", security_group_name ,"successfully created!")

# create a new EC2 instance
new_instances = ec2.create_instances(
    ImageId='ami-0bb4c991fa89d4b9b',
    MinCount=1,
    MaxCount=1,
    InstanceType='t2.nano',
    KeyName='DevOpsAssignment1key',
    SecurityGroups=[security_group_name],
    UserData="""
        #!/bin/bash
        yum install httpd -y
        systemctl enable httpd
        systemctl start httpd

        cd /var/www/html

        echo '<html>' > index.html
        echo 'Availability Zone: ' >> index.html
        curl http://169.254.169.254/latest/meta-data/placement/availability-zone >> index.html
        echo '<br>' >> index.html

        echo 'Instance ID: ' >> index.html
        curl http://169.254.169.254/latest/meta-data/instance-id >> index.html
        echo '<br>' >> index.html

        echo 'Instance Type: ' >> index.html
        curl http://169.254.169.254/latest/meta-data/instance-type >> index.html
        echo '<br>' >> index.html

        echo '<h1>This is my DevOps Assignment 1 - Liam Doocey' >> index.html
    """
)

#Add name tag to instance
tags = [
    {
        'Key': 'Name',
        'Value': 'DevOps-Assignment-1'
    }
]

new_instances[0].create_tags(Tags = tags)

print("\nNew instance successfully created: ", new_instances[0].id, "\n")


#Create random string for bucket name
random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k = 6))

bucket_name = 'ldoocey' + random_string

#Try to make bucket, throw error if not
try:
    s3.create_bucket(
        Bucket = bucket_name
        )
    print('New bucket created: ', bucket_name)
except Exception as e:
    print('Error creating bucket: ', str(e), '(',bucket_name,')')


s3Client.delete_public_access_block(
    Bucket = bucket_name
    )

#Open Bucket Policy
bucket_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": ["s3:GetObject"],
            "Resource": f"arn:aws:s3:::{bucket_name}/*"
        }
    ]
}

#Adding policy to new bucket to ensure it is open to public connections
try:
    s3.Bucket(bucket_name).Policy().put(Policy = json.dumps(bucket_policy))
    print('Added public policy to bucket: ', bucket_name)
except Exception as e:
    print('Error adding Policy: ', str(e))

#Downloading image needed for website and creating index.html 
subprocess.run(["curl http://devops.witdemo.net/logo.jpg > logo.jpg"], shell = True)
subprocess.run(["echo '<html> <img src = logo.jpg>' > index.html"], shell = True)

#Content Need for s3 site
content = {
    'logo.jpg': 'image/jpeg',
    'index.html': 'text/html'
}

#Uploading files to bucket
for file in content:
    try:
        content_type = content.get(file, 'application/octet-stream')
        s3.Object(bucket_name, file).put(Body = open (file, 'rb'), ContentType = content_type)
        print(file, 'successfully uploaded.')
    except Exception as e:
        print('Error uploading', file , 'to bucket', str(e))

#Clean up any files created / Downloaded
subprocess.run(['rm index.html logo.jpg'], shell = True)

website_config = {
    'ErrorDocument': {'Key': 'error.html'},
    'IndexDocument': {'Suffix': 'index.html'}
}

bucket_site = s3.BucketWebsite(bucket_name)
bucket_site.put(WebsiteConfiguration = website_config)

EC2site = new_instances[0].public_ip_address
S3site = bucket_name + '.s3-website.us-east-1.amazonaws.com'

#Write URLs to file
outFile = 'ldoocey-websites.txt'
with open(outFile, 'w') as file:
    file.write(EC2site + '\n')
    file.write(S3site + '\n') 

print('\nWaiting for Instance to start.....')
new_instances[0].wait_until_running()

#Wait for startup commands to run on EC2 Instance
time.sleep(15)

webbrowser.open_new_tab(EC2site)
webbrowser.open_new_tab(S3site)

print('Uploading monitoring script to EC2 instance....')

#Upload Monitoring.sh to Instance
SCPcmd = "scp -o StrictHostKeyChecking=no -i DevOpsAssignment1key.pem monitoring.sh ec2-user@" + new_instances[0].public_ip_address + ":."
subprocess.run(SCPcmd, shell = True)

#Configure permissions for script
SSHcmd = "ssh -i DevOpsAssignment1key.pem ec2-user@" + new_instances[0].public_ip_address + " 'chmod 700 monitoring.sh'"
subprocess.run(SSHcmd, shell = True)

#Run Script
SSHcmd2 = "ssh -i DevOpsAssignment1key.pem ec2-user@" + new_instances[0].public_ip_address + " './monitoring.sh'"
subprocess.run(SSHcmd2, shell = True)

print('Monitoring script uploaded.')