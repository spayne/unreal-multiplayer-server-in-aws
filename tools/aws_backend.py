#!/usr/bin/env python

# Copyright 2022 Sean Payne
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import argparse
import time
import logging
import json
import zipfile
import io
import subprocess
import re
import uuid

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)
log_info = logger.info


# globals
global iam_client, gamelift_client, lambda_client, apigateway_client, cognitoidp_client


def global_setup(profile_name, region_name):
    boto3.setup_default_session(
        profile_name=profile_name,
        region_name=region_name)

    log_info("initializing boto api interfaces")
    global iam_client, gamelift_client, lambda_client, apigateway_client, cognitoidp_client
    iam_client = boto3.client('iam')
    gamelift_client = boto3.client('gamelift')
    lambda_client = boto3.client('lambda')
    apigateway_client = boto3.client('apigateway')
    cognitoidp_client = boto3.client('cognito-idp')
    log_info("...ok")


def get_groups_by_username(username):
    groups_json = iam_client.list_groups_for_user(UserName=username)['Groups']
    group_names = []
    for group in groups_json:
        group_names.append(group['GroupName'])
    return group_names


def get_group_policies(user_groups):
    policy_names = []
    for group in user_groups:
        attached_group_policies = (
            iam_client.list_attached_group_policies(
                GroupName=group)['AttachedPolicies'])
        for policy in attached_group_policies:
            policy_names.append(policy['PolicyName'])
        group_policies = (
            iam_client.list_group_policies(
                GroupName=group)['PolicyNames'])
        policy_names.extend(group_policies)
    return policy_names


def get_user_policies(username):
    attached_user_policies = (
        iam_client.list_attached_user_policies(
            UserName=username)['AttachedPolicies'])
    policy_names = []
    for policy in attached_user_policies:
        policy_names.append(policy['PolicyName'])
    user_policies = (
        iam_client.list_user_policies(
            UserName=username)['PolicyNames'])
    policy_names.extend(user_policies)
    return policy_names


def get_policies_for_user_including_groups(user_name):
    policy_names = []
    group_names = get_groups_by_username(user_name)
    group_policy_names = get_group_policies(group_names)
    user_policy_names = get_user_policies(user_name)
    policy_names.extend(group_policy_names)
    policy_names.extend(user_policy_names)
    return policy_names


def check_user_policies(user_name):
    log_info(f"checking {user_name} policies")
    policy_names = get_policies_for_user_including_groups(user_name)
    if 'AdministratorAccess' in policy_names:
        log_info("... has AdministratorAccess ...ok")
    else:
        log_info(
            f"... NO AdministratorAccess ... {user_name} may have issues ...fail")


def create_build(build_config):
    log_info(f'creating {build_config["build_root"]}')

    command_list = ["aws",
                    "gamelift", "upload-build",
                    "--operating-system", build_config["build_os"],
                    "--build-root", build_config["build_root"],
                    "--name", build_config["build_name"],
                    "--build-version", build_config["build_version"],
                    "--region", build_config["region"],
                    "--profile", build_config["profile"]]
    log_info(' '.join(command_list))

    completed_process = subprocess.run(command_list, capture_output=True)

    match = re.search(
        "Build ID: (.*)",
        completed_process.stdout.decode('utf-8'))
    if match:
        build_id = match.group(1)
        log_info("Build ID: " + build_id)
    else:
        log_info("failed")
        log_info(completed_process.stderr.decode('utf-8'))


def create_fleet(build_config):
    log_info("creating fleet")
    build_id = lookup_build_id(build_config["build_name"])

    if build_id:

        describe_build_resp = gamelift_client.describe_build(BuildId=build_id)
        while describe_build_resp["Build"]["Status"] != "READY":
            log_info("waiting for build to be ready\n")
            time.sleep(1)
            describe_build_resp = gamelift_client.describe_build(
                BuildId=build_id)

        create_fleet_resp = gamelift_client.create_fleet(
            Name=build_config["fleet_name"],
            BuildId=build_id,
            ServerLaunchPath=build_config["fleet_launch_path"],
            EC2InstanceType=build_config["fleet_ec2_instance_type"],
            FleetType="ON_DEMAND",
            EC2InboundPermissions=[
                {
                    'FromPort': 7777,
                    'ToPort': 7777,
                    'Protocol': 'UDP',
                    'IpRange': '0.0.0.0/0'}])
    else:
        log_info(f'could not find build: {build_config["build_name"]}')

    log_info(f'create_fleet_resp: {create_fleet_resp}')


# ref https://hands-on.cloud/working-with-aws-lambda-in-python-using-boto3/
def create_lambda_role(
        role_name,
        assume_role_policy,
        other_policy_name,
        other_policy):
    try:
        response = iam_client.get_role(RoleName=role_name)
        role_arn = response["Role"]["Arn"]
        log_info('role already exists arn ' + role_arn)
    except BaseException:
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy))
        role_arn = response["Role"]["Arn"]
        log_info(response)

    response = iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName=other_policy_name,
        PolicyDocument=json.dumps(other_policy))

    return role_arn


def create_lambda(
        function_name,
        role_arn,
        filename,
        replace_old=None,
        replace_new=None):
    with open(filename, 'r') as inputfile:
        filedata = inputfile.read()

    if replace_old:
        filedata = filedata.replace(replace_old, replace_new)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as tempzip:
        tempzip.writestr('handler.py', filedata)

    zipped_code = zip_buffer.getvalue()

    log_info(f"creating {function_name} lambda")
    create_function_response = lambda_client.create_function(
        FunctionName=function_name,
        Runtime="python3.9",
        Publish=True,
        PackageType="Zip",
        Role=role_arn,
        Code=dict(ZipFile=zipped_code),
        Handler="handler.lambda_handler"
    )
    log_info(f"create_function_response {create_function_response}")


def create_lambdas(build_config):

    lambda_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    # ref:
    # https://github.com/aws-samples/amazon-gamelift-unreal-engine/blob/main/lambda/GameLiftUnreal-StartGameLiftSession.json

    gamelift_session_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "gamelift:CreateGameSession",
                    "gamelift:CreatePlayerSession",
                    "gamelift:CreatePlayerSessions",
                    "gamelift:DescribeGameSessionDetails",
                    "gamelift:DescribeGameSessions",
                    "gamelift:ListFleets",
                    "gamelift:ListGameServerGroups",
                    "gamelift:SearchGameSessions"
                ],
                "Resource": "*"
            }
        ]
    }

    cognito_auth = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "VisualEditor0",
                "Effect": "Allow",
                "Action": "cognito-idp:InitiateAuth",
                "Resource": "*"
            }
        ]
    }

    # todo: session_role =
    # create_lambda_role(build_config["lambda_session_role"], lambda_policy,
    session_role = create_lambda_role(
        "gl_session_lambda_role",
        lambda_policy,
        "gl_session_policy",
        gamelift_session_policy)
    # todo: debug this login_role =
    # create_lambda_role(build_config["lambda_cognito_role"], lambda_policy,
    login_role = create_lambda_role("gl_cognito_lambda_role", lambda_policy,
                                    "cognito_auth", cognito_auth)

    fleet_id = lookup_fleet_id(build_config["fleet_name"])
    log_info("got fleet_id" + fleet_id)

    create_lambda(
        build_config["lambda_start_session_name"],
        session_role,
        "GameLiftUnreal-StartGameLiftSession.py",
        'GAMELIFT_FLEET_ID = ""',
        "GAMELIFT_FLEET_ID = \"" + fleet_id + "\"")

    cognito_app_client_id = lookup_cognito_pool_client_id(
        build_config["user_pool_name"],
        build_config["user_pool_login_client_name"])

    create_lambda(
        build_config["lambda_login_name"],
        login_role,
        "GameLiftUnreal-CognitoLogin.py",
        "USER_POOL_APP_CLIENT_ID = ''",
        "USER_POOL_APP_CLIENT_ID = \"" +
        cognito_app_client_id +
        "\"")


def lookup_build_id(build_name):
    list_builds_response = gamelift_client.list_builds()
    builds = list_builds_response["Builds"]
    for build in builds:
        if build["Name"] == build_name:
            return build["BuildId"]
    return None


def lookup_fleet_id(fleet_name):
    response = gamelift_client.describe_fleet_attributes()
    fleet_attributes = response["FleetAttributes"]
    for fleet in fleet_attributes:
        if fleet["Name"] == fleet_name:
            fleet_id = fleet["FleetId"]
            return fleet_id
    return None


def lookup_cognito_pool_id(pool_name):
    response = cognitoidp_client.list_user_pools(MaxResults=60)
    for pool in response["UserPools"]:
        if pool["Name"] == pool_name:
            pool_id = pool["Id"]
            return pool_id
    return None


def lookup_cognito_arn(pool_name):
    pool_id = lookup_cognito_pool_id(pool_name)
    response = cognitoidp_client.describe_user_pool(UserPoolId=pool_id)
    arn = response["UserPool"]["Arn"]
    return arn


def lookup_cognito_pool_client_id(pool_name, client_name):
    pool_id = lookup_cognito_pool_id(pool_name)

    if pool_id:
        response = cognitoidp_client.list_user_pool_clients(
            UserPoolId=pool_id,
            MaxResults=60)
        for client in response["UserPoolClients"]:
            if client["ClientName"] == client_name:
                client_id = client["ClientId"]
                return client_id
    return None


def lookup_lambda_arn(lambda_name):
    try:
        get_function_resp = lambda_client.get_function(
            FunctionName=lambda_name)
        lambda_arn = get_function_resp["Configuration"]["FunctionArn"]
        return lambda_arn
    except BaseException:
        return None


def lookup_rest_api_id(rest_api_name):
    response = apigateway_client.get_rest_apis()
    rest_apis = response["items"]
    for rest_api in rest_apis:
        if rest_api_name == rest_api["name"]:
            rest_api_id = rest_api["id"]
            return rest_api_id
    return None


def create_rest_resource(
        rest_api_id,
        apigateway_client, path_part, http_method,
        account_id, lambda_client, lambda_function_arn,
        authorizer_id):

    #
    # Get Root ID
    #
    try:
        response = apigateway_client.get_resources(restApiId=rest_api_id)
        root_id = next(item['id']
                       for item in response['items'] if item['path'] == '/')
    except ClientError:
        logger.exception(
            "Couldn't get the ID of the root resource of the REST API.")
        raise

    #
    # Create the resource under root
    #
    try:
        response = apigateway_client.create_resource(
            restApiId=rest_api_id, parentId=root_id, pathPart=path_part)
        resource_id = response['id']
    except ClientError:
        logger.exception("Couldn't create pathPart path for %s.", path_part)
        raise

    #
    # Create the method for the resource
    #
    # ref: https://youtu.be/EfIuC5-wdeo?t=1095
    #      * shows setting the Authorizor on the method

    if authorizer_id:
        authorization_type = 'COGNITO_USER_POOLS'
    else:
        authorization_type = 'NONE'
        authorizer_id = ''

    try:
        apigateway_client.put_method(
            restApiId=rest_api_id,
            resourceId=resource_id,
            httpMethod=http_method,
            authorizationType=authorization_type,
            authorizerId=authorizer_id)
    except ClientError:
        logger.exception("Couldn't create a method for the base resource.")
        raise

    #
    # Bind the method to the lambda
    #
    lambda_uri = \
        f'arn:aws:apigateway:{apigateway_client.meta.region_name}:' \
        f'lambda:path/2015-03-31/functions/{lambda_function_arn}/invocations'
    try:
        # NOTE: You must specify 'POST' for integrationHttpMethod or this will
        # not work.
        apigateway_client.put_integration(
            restApiId=rest_api_id,
            resourceId=resource_id,
            httpMethod=http_method,
            type='AWS',
            integrationHttpMethod='POST',
            uri=lambda_uri)
    except ClientError:
        logger.exception(
            "Couldn't set function %s as integration destination.",
            lambda_function_arn)
        raise

    #
    # Add permission so the method is able to invoke the lambda
    #
    source_arn = \
        f'arn:aws:execute-api:{apigateway_client.meta.region_name}:' \
        f'{account_id}:{rest_api_id}/*/*/{path_part}'
    try:
        lambda_client.add_permission(
            FunctionName=lambda_function_arn,
            StatementId=uuid.uuid4().hex,  # todo do I need to clean these up
            Action='lambda:InvokeFunction', Principal='apigateway.amazonaws.com',
            SourceArn=source_arn)
    except ClientError:
        logger.exception(
            "Couldn't add permission to let Amazon API Gateway invoke %s.",
            lambda_function_arn)
        raise

    #
    # Fill out response details
    #
    apigateway_client.put_integration_response(
        restApiId=rest_api_id,
        resourceId=resource_id,
        httpMethod=http_method,
        statusCode="200",
        selectionPattern=".*"
    )

    apigateway_client.put_method_response(
        restApiId=rest_api_id,
        resourceId=resource_id,
        httpMethod=http_method,
        statusCode="200")


def create_login_resource(rest_api_id, build_config, authorizer_id):
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    lambda_name = build_config["lambda_login_name"]
    lambda_arn = lookup_lambda_arn(lambda_name)

    create_rest_resource(
        rest_api_id,
        apigateway_client,
        build_config["rest_api_login_path_part"],
        'POST',
        account_id,
        lambda_client,
        lambda_arn,
        authorizer_id)


def create_start_session_resource(rest_api_id, build_config, authorizer_id):
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    lambda_name = build_config["lambda_start_session_name"]
    lambda_arn = lookup_lambda_arn(lambda_name)

    create_rest_resource(
        rest_api_id,
        apigateway_client,
        build_config["rest_api_start_session_path_part"],
        'GET',
        account_id,
        lambda_client,
        lambda_arn,
        authorizer_id)


##########################################################################
# create_rest_api: create the api, authorizer and methods
#
# ref: https://youtu.be/EfIuC5-wdeo?t=822
#        * has some details on configuring lambda invocation using boto3
#
def create_rest_api(build_config):
    if lookup_rest_api_id(build_config["rest_api_name"]):
        log_info("not creating rest api because it already exists")
        return

    #
    # Create the Rest API
    #
    try:
        response = apigateway_client.create_rest_api(
            name=build_config["rest_api_name"])
        rest_api_id = response['id']
    except ClientError:
        logger.exception(
            f'Could not create REST API {build_config["rest_api_name"]}.')
        raise

    #
    # Create the cognito authorizer
    #
    cognito_arn = lookup_cognito_arn(build_config["user_pool_name"])

    # ref: https://youtu.be/EfIuC5-wdeo?t=1012
    create_authorizer_response = apigateway_client.create_authorizer(
        restApiId=rest_api_id,
        name=build_config["rest_api_cognito_authorizer_name"],
        type='COGNITO_USER_POOLS',
        providerARNs=[cognito_arn],
        identitySource="method.request.header.Authorization"
    )

    authorizer_id = create_authorizer_response["id"]

    #
    # Create the login and start session gateway
    #
    create_login_resource(rest_api_id, build_config, None)
    create_start_session_resource(rest_api_id, build_config, authorizer_id)

    #
    # Deploy the API to the requested stage name
    #
    try:
        create_deployment_resp = apigateway_client.create_deployment(
            restApiId=rest_api_id,
            stageName=build_config["rest_api_stage_name"])
    except ClientError:
        logger.exception("Couldn't deploy REST API %s.", rest_api_id)
        raise
    log_info(f"create_deployment_resp {create_deployment_resp}")

    invoke_url = f'https://{rest_api_id}.execute-api.{build_config["region"]}.amazonaws.com/{build_config["rest_api_stage_name"]}'
    log_info('invoke_url: ' + invoke_url)
    log_info('to login try:')
    login_curl = 'curl -X POST -d "{\\"username\\":\\"user0\\", \\"password\\":\\"test12\\"}" ' + \
        invoke_url + '/login'
    log_info(login_curl)
    log_info("")
    log_info('to start a session,  use the [IdToken] from the above login')
    start_curl = 'curl -X GET -H "Authorization: Bearer [IdToken]\" ' + \
        invoke_url + '/startsession'
    log_info(start_curl)


def create_user_pool(build_config):
    log_info("creating cognito user pool")

    if lookup_cognito_pool_id(build_config["user_pool_name"]):
        log_info("not creating - already exists\n")
        return

    create_user_pool_resp = cognitoidp_client.create_user_pool(
        PoolName=build_config["user_pool_name"],
        Policies={
            "PasswordPolicy": {
                "MinimumLength": 6,
                "RequireUppercase": False,
                "RequireLowercase": False,
                "RequireNumbers": False,
                "RequireSymbols": False
            }
        },
        Schema=[{"Name": "email",
                 "AttributeDataType": "String",
                 "DeveloperOnlyAttribute": False,
                 "Mutable": True,
                 "Required": True,
                 "StringAttributeConstraints": {
                     "MinLength": "0",
                     "MaxLength": "2048"
                 }}]
    )
    user_pool_id = create_user_pool_resp["UserPool"]["Id"]

    log_info("creating cognito app client")
    # ref: https://youtu.be/EfIuC5-wdeo?t=137
    # uncheck generate client secret
    # just using ALLOW_USER_PASSWORD_AUTH.  API also wants: "ALLOW_REFRESH_TOKEN_AUTH"
    #
    # ref https://youtu.be/EfIuC5-wdeo?t=172
    # Enabled Identity Providers: Cognito User Pools
    # Callback and Signout URLs: Use AWS home page
    # implicit grant,
    # email and openid OAuth scopes

    redirect_uri = "https://aws.amazon.com"

    create_user_pool_client_resp = cognitoidp_client.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName=build_config["user_pool_login_client_name"],
        GenerateSecret=False,
        ExplicitAuthFlows=[
            "ALLOW_USER_PASSWORD_AUTH",
            "ALLOW_REFRESH_TOKEN_AUTH"],
        SupportedIdentityProviders=["COGNITO"],
        CallbackURLs=[redirect_uri],
        LogoutURLs=[redirect_uri],
        AllowedOAuthFlows=["implicit"],
        AllowedOAuthFlowsUserPoolClient=True,
        AllowedOAuthScopes=[
            "email",
            "openid"],
    )
    log_info(f"create_user_pool_client_resp {create_user_pool_client_resp}")

    update_user_pool_resp = cognitoidp_client.update_user_pool(
        UserPoolId=user_pool_id,
        AutoVerifiedAttributes=["email"])

    log_info(f"update_user_pool_resp {update_user_pool_resp}")

    log_info("creating cognito user pool domain")
    # go to App client settings, setup the callback URLs and hosted UI
    subdomain = build_config["user_pool_subdomain_prefix"]

    create_user_pool_resp = cognitoidp_client.create_user_pool_domain(
        Domain=subdomain,
        UserPoolId=user_pool_id)

    log_info("users can create new accounts using the ui at:")
    login_url = f'https://{subdomain}.auth.{build_config["region"]}.amazoncognito.com/'
    login_url = login_url + \
        f'login?client_id={create_user_pool_client_resp["UserPoolClient"]["ClientId"]}'
    login_url = login_url + \
        f'&response_type=Token&scope=email+openid&redirect_uri={redirect_uri}'
    log_info(login_url)

    log_info("creating test users")
    for index in range(32):
        user_name = 'user' + str(index)
        cognitoidp_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=user_name,
            UserAttributes=[
                {"Name": "email", "Value": "test@test.com"}
            ],
            TemporaryPassword="test12",
            MessageAction='SUPPRESS'
        )
        cognitoidp_client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=user_name,
            Password="test12",
            Permanent=True
        )


def delete_build(build_config):
    build_id = lookup_build_id(build_config["build_name"])
    while build_id:
        log_info(f"deleting build {build_id}")
        gamelift_client.delete_build(BuildId=build_id)
        build_id = lookup_build_id(build_config["build_name"])


def delete_fleet(build_config):
    fleet_id = lookup_fleet_id(build_config["fleet_name"])
    if fleet_id:
        try:
            log_info(f"deleting fleet {fleet_id}")
            gamelift_client.delete_fleet(FleetId=fleet_id)
        except ClientError as e:
            log_info(e)


def delete_user_pool(build_config):
    pool_id = lookup_cognito_pool_id(build_config["user_pool_name"])
    if pool_id:
        response = cognitoidp_client.describe_user_pool(UserPoolId=pool_id)
        if "Domain" in response["UserPool"]:
            pool_domain = response["UserPool"]["Domain"]
            log_info(f"deleting pool domain {pool_domain}")
            response = cognitoidp_client.delete_user_pool_domain(
                Domain=pool_domain, UserPoolId=pool_id)
        response = cognitoidp_client.delete_user_pool(UserPoolId=pool_id)


def delete_lambdas(build_config):
    log_info("deleting lambdas")
    start_session_arn = lookup_lambda_arn(
        build_config["lambda_start_session_name"])
    if start_session_arn:
        lambda_client.delete_function(FunctionName=start_session_arn)

    login_arn = lookup_lambda_arn(build_config["lambda_login_name"])
    if login_arn:
        lambda_client.delete_function(FunctionName=login_arn)


def delete_rest_api(build_config):
    log_info("deleting rest_api")
    rest_api_id = lookup_rest_api_id(build_config["rest_api_name"])
    while rest_api_id:
        apigateway_client.delete_rest_api(restApiId=rest_api_id)
        rest_api_id = lookup_rest_api_id(build_config["rest_api_name"])


def process_create_commands(commands, build_config):
    log_info("creating...")
    while len(commands) > 0:
        command = commands.pop(0)
        match command:
            case "build":
                create_build(build_config)
            case "fleet":
                create_fleet(build_config)
            case "user_pool":
                create_user_pool(build_config)
            case "lambdas":
                create_lambdas(build_config)
            case "rest_api":
                create_rest_api(build_config)
            case _:
                log_info("urecognized command" + command)


def process_delete_commands(commands, build_config):
    log_info("deleting...")
    while len(commands) > 0:
        command = commands.pop(0)
        match command:
            case "build":
                delete_build(build_config)
            case "fleet":
                delete_fleet(build_config)
            case "user_pool":
                delete_user_pool(build_config)
            case "lambdas":
                delete_lambdas(build_config)
            case "rest_api":
                delete_rest_api(build_config)
            case _:
                log_info("urecognized command: " + command)


def process_build_config(build_config):
    if len(build_config["commands"]) > 0:
        log_info(f'Using profile: {build_config["profile"]}')
        global_setup(build_config["profile"], build_config["region"])

        create_or_delete_command = build_config["commands"].pop(0)
        sub_commands = build_config["commands"]

        if len(sub_commands) > 0 and sub_commands[0] == "all":
            sub_commands = [
                "build",
                "fleet",
                "user_pool",
                "lambdas",
                "rest_api"]

        match create_or_delete_command:
            case "create":
                process_create_commands(sub_commands, build_config)
            case "delete":
                process_delete_commands(sub_commands, build_config)


def parse_args():
    '''return a build_config'''
    parser = argparse.ArgumentParser(
        description='Configure AWS Services to provide login, session and server management for dedicated UE servers',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('commands', nargs='*')
    parser.add_argument('--prefix', default="test1", help="prefix used below")

    parser.add_argument(
        '--build_name',
        default="[prefix]-build",
        help="name associated with the build (visible in the GameLift console")
    parser.add_argument(
        '--build_version',
        default="build0.42",
        help="a version number")
    parser.add_argument(
        '--build_os',
        default="WINDOWS_2012",
        help="the os to install on the EC2 instances")
    parser.add_argument(
        '--build_root',
        default="E:/unreal_projects/MyProject/x64 Builds/WindowsServer",
        help="path to the server package on your local machine")

    parser.add_argument(
        '--fleet_name',
        default="[prefix]-fleet",
        help="name associated with the fleet")
    parser.add_argument(
        '--fleet_launch_path',
        default="C:/game/MyProject/Binaries/Win64/MyProjectServer.exe",
        help="the EC2 path to the server.  Must start with c:/game")

    parser.add_argument(
        '--fleet_ec2_instance_type',
        default="c5.large",
        help="what kind of EC2s to allocate.")

    parser.add_argument(
        '--user_pool_name',
        default="[prefix]-user-pool",
        help="pool name")
    parser.add_argument(
        '--user_pool_login_client_name',
        default="[prefix]-user-pool-login-client",
        help="pool client name")
    parser.add_argument(
        '--user_pool_subdomain_prefix',
        default="[prefix]-login",
        help="name the subdomain")

    parser.add_argument(
        '--lambda_start_session_name',
        default="[prefix]-lambda-start-session",
        help="name the lambda")
    parser.add_argument(
        '--lambda_login_name',
        default="[prefix]-lambda-login",
        help="name the lambda")
    parser.add_argument(
        '--lambda_session_role',
        default="[prefix]-lambda-session-role",
        help="name the role")
    parser.add_argument(
        '--lambda_cognito_role',
        default="[prefix]-lambda-cognito-role",
        help="name the role")

    parser.add_argument(
        '--rest_api_name',
        default="[prefix]-rest-api",
        help="name the api")
    parser.add_argument(
        '--rest_api_stage_name',
        default="[prefix]-api-test-stage",
        help="name the stage")
    parser.add_argument(
        '--rest_api_login_path_part',
        default="login",
        help="name the suffix")
    parser.add_argument(
        '--rest_api_start_session_path_part',
        default="startsession",
        help="name the suffix")
    parser.add_argument(
        '--rest_api_cognito_authorizer_name',
        default="[prefix]-cognito-authorizer",
        help="name the authorizer")

    parser.add_argument(
        '--profile',
        default='sean_gl',
        help="AWS credentials to use")
    parser.add_argument('--region', default='us-west-2', help='AWS region')

    args = parser.parse_args()

    build_config = vars(args)

    # walk through the build config and replace [prefix] with the prefix
    # these final configuration parameters are what is used as the resource
    # names during creation and deletion.
    log_info("Configuration:")
    prefix = build_config["prefix"]
    for key, value in build_config.items():
        if type(value) == str:
            build_config[key] = value.replace("[prefix]", prefix)
        log_info(f" {key}:{build_config[key]}")

    return build_config


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format=f'%(asctime)s %(levelname)s %(message)s'
    )

build_config = parse_args()
process_build_config(build_config)
