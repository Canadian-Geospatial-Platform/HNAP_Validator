#-*- coding: utf-8 -*-
__license__ = "NRCAN"
__email__ = ""
__maintainer__ = "NRCAN"
import string
import random
import time
import json
import boto3
import base64
import os
import sys
import email


# boto3 client 
client_ec2 = boto3.client('ec2')
client_ssm = boto3.client('ssm')
client_s3 = boto3.client('s3')

#
#function to check whether the EC2 instance is running
#
#Args:
#    instanceid: EC2 instance ID that has to be queried
#
#Returns:
#    True if running, false otherwise
#
def IsEC2InstanceRunning(instanceid):
    # getting instance information
    # instanceid = 'i-01b8813c2e20b1a9f'
    describeInstance = client_ec2.describe_instances(InstanceIds=[instanceid])

    instance = describeInstance['Reservations'][0]['Instances'][0]
    if  instance["State"]["Name"] == "running" and instance['InstanceId'] == instanceid:
        return True
    else:
        return False
    
def lambda_handler(event, context):
    #
    # getting instance information
    #
    instanceid = 'i-01b8813c2e20b1a9f'
    if IsEC2InstanceRunning(instanceid):
        #
        #decoding form-data into bytes
        #
        post_data = base64.b64decode(event['body'])
        #
        # fetching content-type to confirm its multipart/form-data
        #
        try:
            content_type = event["headers"]['Content-Type']
        except:
            content_type = event["headers"]['content-type']
        #    
        # concate Content-Type: with content_type from event
        #
        ct = "Content-Type: "+content_type+"\n"
    
        #
        # parsing message from bytes
        #
        msg = email.message_from_bytes(ct.encode()+post_data)
    
        # checking if the message is multipart
        #print("Multipart check : ", msg.is_multipart())
        
        #
        # check if message is multipart/form-data
        #
        userXmlFile = ''
        if msg.is_multipart():
            multipart_content = {}
            #
            # retrieving the filename from the form-data
            #
            for part in msg.get_payload():
                # checking if filename exist as a part of content-disposition header
                if part.get_filename():
                    #
                    # fetching the filename
                    #
                    userXmlFile = part.get_filename()
                    #print (userXmlFile)
                multipart_content[part.get_param('name', header='content-disposition')] = part.get_payload(decode=True)
            
            #
            # if there is no schematron file or the extension is not sch then raise and error
            #
            if len(userXmlFile) == 0 or not userXmlFile.lower().endswith('.sch'):
                errMsg = "Bad Request: Missing input file or input file does not seem to a schematron file. It should have *.sch or *.SCH file extension"
                return {
                    'headers': { "Content-Type": "application/json" },
                    'statusCode': 402,
                    'body': json.dumps({'statusCode': '402', 'body': errMsg})
                }
 
            cmdSucess = True
            outMsg = "Successful Operation: Schematron file has been updated on the server."
            try:
                #load the file in S3/ec2
                s3_upload = client_s3.put_object(Bucket="upload-xml-files", Key="schmatronFile.sch", Body=multipart_content["file"])
            
                cmd0 = 'cd /home/hnapv/apacheant/data/schematron/'
                cmd1 = 'rm -rf *.*'
                cmd2 = 'aws s3 cp  s3://upload-xml-files/schmatronFile.sch  /home/hnapv/apacheant/data/schematron/'
        
                # command to be executed on instance
                # Here its dealing with EC2 file system
                response = client_ssm.send_command(
                                InstanceIds=[instanceid],
                                DocumentName="AWS-RunShellScript",
                                # Add command_to_be_executed with command
                                Parameters={'commands': [cmd0, cmd1, cmd2]}
                            )
                
                # fetching command id for the output
                command_id = response['Command']['CommandId']
                
                time.sleep(4)  #input is in secs
                
                while True:
                    # fetching command output
                    output = client_ssm.get_command_invocation( CommandId=command_id, InstanceId=instanceid )
                    if output['Status'] == 'Success':
                        break
            except  botocore.exceptions.ClientError as error:
                    outMsg = error.response['Error']['Message']
                    cmdSucess = False;
                    
            if cmdSucess == True:
                return {
                    "headers": { "Content-Type": "application/json"},
                    'statusCode': '200',
                    'body': json.dumps({'statusCode': '200', 'body': outMsg})
                }
            else:
                return {
                    'headers': { "Content-Type": "application/json" },
                    'statusCode': 406,
                    'body': json.dumps({'statusCode': '406', 'body': outMsg})
                }
    
        else:
            # on upload failure
            errMsg = "Bad Request: Error in the input data. The Content-Type should be mutipart/form-data."
            return {
                'headers': { "Content-Type": "application/json" },
                'statusCode': 404,
                'body': json.dumps({'statusCode': '404', 'body': errMsg})
            }
        
    else:
        # on upload failure
        errMsg = "Server (EC2) Instance is not running. Start the server and then run again."
        return {
            'headers': { "Content-Type": "application/json" },
            'statusCode': 500,
            'body': json.dumps({'statusCode': '500', 'body': errMsg})
        }
        

