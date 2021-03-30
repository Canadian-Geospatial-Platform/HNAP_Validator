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
import botocore
import logging

# boto3 client
client_ec2 = boto3.client('ec2')
client_ssm = boto3.client('ssm')
client_s3 = boto3.client('s3')

# initializing size of string 
randStrLen = 8

#
#Generate a random string of size 'randStrLen
#
#Returns:
#    a string of size randStrLen
#
def randomStrGenerator():
    # using random.choices() 
    # generating random strings  
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(randStrLen))
    
#
#Generate build.xml file at /tmp directory 
#
#Args:
#    userDir: user directory where the file has to be created
#    schmatronFile: reference to the schematron file
#    xmlFile:  xml file than has to be validated
#    outDir: output directory for the schematron processing
#
#Returns:
#    The name and the absolute path of the created file
#        
def createBuildxmlfile(userDir, schmatronFile, xmlFile, outDir):
    # Create build.xml file- input to ant command
    filename = os.path.join(userDir, "build.xml")
    data_file = open(filename, 'w')
    data_file.write(str("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"))
    data_file.write(str("<project name=\"schematron-ant-test\" default=\"test-fileset\">\n"))
    data_file.write(str("<target name=\"test-fileset\" description=\"Test with a Fileset\">\n"))
    data_file.write(str("<taskdef name=\"schematron\" classname=\"com.schematron.ant.SchematronTask\"/>\n"))
    data_file.write(str("<schematron schema=" + "\"" + schmatronFile + "\"\n"))
    data_file.write(str("file=" + "\"" + xmlFile + "\"\n"))
    #data_file.write(str("outputFilename=\"svrl.xml\"\n"))
    data_file.write(str("OutputDir=" + "\"" + outDir + "\"\n"))
    #data_file.write(str("resolver=\"org.apache.xml.resolver.tools.CatalogResolver\"\n"))
    #data_file.write(str("classpath=\"../../../apache-ant-1.10.9/lib/*.jar\"\n"))
    data_file.write(str("failonerror=\"false\"\n"))
    data_file.write(str("debugmode=\"true\"\n"))
    data_file.write(str("allow_foreign=\"true\"\n"))
    data_file.write(str("queryLanguageBinding=\"xslt2\"\n"))
    data_file.write(str("diagnose=\"true\">\n"))
    data_file.write(str("</schematron>\n"))
    data_file.write(str("</target>\n"))
    data_file.write(str("</project>\n"))
    data_file.close()

    return filename

#
# Normalize the specified path 
#
def norm_path(path):
    return os.path.normpath(path) 

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

    return False

#
#function to remove the files/directories created during validation.
#
#Args:
#    instanceid: EC2 instance ID that has to be queried
#
#Returns: 
#
def CleanUp(instanceid, randStr, key):
    #before returning the output do some cleanup
    try:
        cmd7 = 'aws s3 rm s3://upload-xml-files/{} --recursive'.format(key)
        cmd8 = 'cd /home/hnapv/apacheant/data/xml/'
        cmd9 = 'rm -rf {}'.format(randStr)
    
        # command to be executed on instance
        response = client_ssm.send_command(
                    InstanceIds=[instanceid],
                    DocumentName="AWS-RunShellScript",
                    # Add command_to_be_executed with command
                    Parameters={'commands': [cmd7, cmd8, cmd9]} 
                )
        time.sleep(2)  #input is in secs
        
    except  botocore.exceptions.ClientError as error:
        logging.error(error)

#
# main function handler 
# Steps:
#     1. Create a random dir in /tmp folder of Lambda
#     2. Read a save user input xml file in /tmp/randDir/  of Lambda
#     3. Create build.xml file in /tmp/randDir/
#     4. Get the instance of ec2
#     5. Create folder 'randDir' in s3 bucket 'upload-xml-files' using AWS CLI comand
#     6. upload the files from /tmp/randDir to s3://upload-xml-files/randDir 
#     7. Now fire validator comands
#         1. aws s3 cp s3://upload-xml-files/randDir  /home/hnapv/apacheant/data/  --recursive
#         2. 'source ~/.bash_profile',
#         3. 'cd /home/hnap/apacheant/data', 
#         4. 'ant > ant-output.txt'
        
#     8. Remove the files from s3/ec2 using AWS CLI
#         1. aws s3 rm s3://upload-xml-files/randDir -- recursive
#         2. rm -rf *.* 
#
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
                multipart_content[part.get_param('name', header='content-disposition')] = part.get_payload(decode=True)
            
            #
            # if there is no xml file then raise and error
            #
            if len(userXmlFile) == 0:
                errMsg = "Bad Request: XML file to be validated is mising from the input data. You must provide an input xml file"
                return {
                    'headers': { "Content-Type": "application/json" },
                    'statusCode': 401,
                    'body': json.dumps({'statusCode': '401', 'body': errMsg})
                }
            
            filext = os.path.splitext(userXmlFile)
            if not filext[1].lower().endswith('.xml'):
                errMsg = "Bad Request: Input file does not seem to a XML file. It should have *.xml or *.XML file extension"
                return {
                    'headers': { "Content-Type": "application/json" },
                    'statusCode': 402,
                    'body': json.dumps({'statusCode': '402', 'body': errMsg})
                }
            
            #
            # create Temporary directory on Lambda filesystem to hold build.xml
            # /tmp/randStr/build.xml
            #
            randStr = randomStrGenerator()
            userDir = os.path.join('/tmp', randStr)
            cmd = 'mkdir {}'.format(userDir)
            os.system(cmd)
            
            #
            #create build.xml file into userDir location
            #
            schmatronFile = "../../schematron/schmatronFile.sch"
            outDir = "./"
            
            if len(userXmlFile) == 0:
                userXmlFile = "userXmlFile.xml"
            buildxmlFile = createBuildxmlfile(userDir, schmatronFile, userXmlFile, outDir)
            
            cmdSucess = True
            errMsg = ''
            try:
                #
                #create a folder in s3 bucket 'upload-xml-files'
                #
                key = "{}/".format(randStr)
                #
                # now create empty folder on S3 bucket
                #
                client_s3.put_object(Bucket="upload-xml-files", Key= key)
                
                #
                #copy files form /tmp/randStr/ to s3
                #
                key1 = "{}/{}".format(randStr, "build.xml")
                client_s3.upload_file(buildxmlFile, 'upload-xml-files' , key1)
            
                #
                # Read input xml file and load it to S3
                #
                key2 = "{}/{}".format(randStr, userXmlFile) #"userXmlFile.xm"
                s3_upload = client_s3.put_object(Bucket="upload-xml-files", Key=key2, Body=multipart_content["file"])
                
            except  botocore.exceptions.ClientError as error:
                errMsg = error.response['Error']['Message']
                cmdSucess = False;
            
            file_content = None    
            if cmdSucess == True:
                try:
                    #
                    # command to be executed for validation
                    #
                    cmd0 = 'cd /home/hnapv/apacheant/data/xml'
                    cmd1 = 'mkdir {}'.format(randStr)
                    cmd2 = 'cd /home/hnapv/apacheant/data/xml/{}'.format(randStr)
                    cmd3 = 'aws s3 cp  s3://upload-xml-files/{}  /home/hnapv/apacheant/data/xml/{} --recursive'.format(key, randStr)
                    cmd4 = 'source ~/.bash_profile'
                    cmd5 = 'ant -f ./build.xml > ant-output.txt'
                    cmd6 = 'aws s3 cp  /home/hnapv/apacheant/data/xml/{}/ant-output.txt s3://upload-xml-files/{}'.format(randStr, key)
                    
                    #
                    # run the commands on the EC2 instance
                    # Here its dealing with EC2 file system
                    #
                    response = client_ssm.send_command(
                                    InstanceIds=[instanceid],
                                    DocumentName="AWS-RunShellScript",
                                    # Add command_to_be_executed with command
                                    Parameters={'commands': [cmd0, cmd1, cmd2, cmd3,cmd4,cmd5, cmd6 ]}
                                )
                    
                    # fetching command id for the output
                    command_id = response['Command']['CommandId']
                    
                    time.sleep(4)  #input is in secs
                    
                    #
                    # make sure all commands are done
                    #
                    while True:
                        # fetching command output
                        output = client_ssm.get_command_invocation( CommandId=command_id, InstanceId=instanceid )
                        if output['Status'] == 'Success':
                            break
            
                    # Output the result to the user
                    key1 = "{}/{}".format(randStr, "ant-output.txt")
                    fileObj = client_s3.get_object(Bucket='upload-xml-files', Key=key1)
                    file_content = fileObj["Body"].read()
                    
                except  botocore.exceptions.ClientError as error:
                    errMsg = error.response['Error']['Message']
                    cmdSucess = False;
                
            #Do the cleanup, no matter what
            CleanUp(instanceid, randStr, key)
                
            if cmdSucess == True:
                #
                #remove the path extenstion of the ec2 instance
                #
                workingDir = '/home/hnapv/apacheant/data/xml/{}'.format(randStr)
                normBytepath = norm_path(workingDir).encode()
                byteReplaceStr = '.'.encode()
                file_content = file_content.replace(normBytepath , byteReplaceStr)
                encoded_str = base64.b64encode(file_content)
                encoded_str = base64.b64decode(encoded_str).decode()
                return {
                    "headers": { "Content-Type": "application/json"},
                    'statusCode': '200',
                    'body': json.dumps({'statusCode': '200', 'body': encoded_str}, 
                                        indent=2)
                }
                # return {
                #     'headers': { "Content-Type": "text/html" },
                #     'statusCode': 200,
                #     'body': encoded_str 
                #     #'isBase64Encoded': True
                # }
            else:
               return {
                    'headers': { "Content-Type": "application/json" },
                    'statusCode': 406,
                    'body': json.dumps({'statusCode': '406', 'body': errMsg})
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
        