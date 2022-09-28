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

import sys
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

can_cognito_json = {
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

can_execute_lambda_policy_json = {
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

can_gamelift_session_control_policy_json = {
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

logger = logging.getLogger(__name__)

log_debug = logger.debug    # detailed information
log_info = logger.info      # confirmation that things are working
log_warn = logger.warning   # something unexpected but still working
log_error = logger.error    # something failed
log_exception = logger.exception    # level is ERROR. log the exception too
log_critical = logger.critical      # program failed


class AwsBackend:
    def __init__(self, backend_config):
        log_info("initializing boto api interfaces")
        self.session = boto3.Session(
                profile_name=backend_config["profile_name"],
                region_name=backend_config["region_name"])
        self.iam_client = self.session.client('iam')
        self.gamelift_client = self.session.client('gamelift')
        self.cognitoidp_client = self.session.client('cognito-idp')
        self.lambda_client = self.session.client('lambda')
        self.apigateway_client = self.session.client('apigateway')
        self.sts_client = self.session.client('sts')
        self.backend_config = backend_config

    def _lookup_build_id(self, build_name):
        list_builds_response = self.gamelift_client.list_builds()
        builds = list_builds_response["Builds"]
        for build in builds:
            if build["Name"] == build_name:
                return build["BuildId"]
        return None

    def create_build(self):
        log_info(f'creating {self.backend_config["build_root"]}')

        command_list = ["aws",
                    "gamelift", "upload-build",
                    "--operating-system", self.backend_config["build_os"],
                    "--build-root", self.backend_config["build_root"],
                    "--name", self.backend_config["build_name"],
                    "--build-version", self.backend_config["build_version"],
                    "--region", self.backend_config["region_name"],
                    "--profile", self.backend_config["profile_name"]]
        log_info(' '.join(command_list))

        completed_process = subprocess.run(command_list, capture_output=True)

        match = re.search(
            "Build ID: (.*)",
            completed_process.stdout.decode('utf-8'))
        if match:
            build_id = match.group(1)
            log_info("successfully uploaded build ID: " + build_id)
        else:
            log_error("failed")
            log_error(completed_process.stderr.decode('utf-8'))

    def delete_build(self):
        build_id = self._lookup_build_id(self.backend_config["build_name"])
        while build_id:
            log_info(f"deleting build {build_id}")
            self.gamelift_client.delete_build(BuildId=build_id)
            build_id = self._lookup_build_id(self.backend_config["build_name"])

    def _lookup_fleet_id(self, fleet_name):
        response = self.gamelift_client.describe_fleet_attributes()
        fleet_attributes = response["FleetAttributes"]
        for fleet in fleet_attributes:
            if fleet["Name"] == fleet_name:
                fleet_id = fleet["FleetId"]
                return fleet_id
        return None

    def create_fleet(self):
        log_info("creating fleet")
        build_id = self._lookup_build_id(self.backend_config["build_name"])

        # handle the case where the build is so new, that it isn't not be ready to be used in a fleet
        if build_id:
            describe_build_resp = self.gamelift_client.describe_build(BuildId=build_id)
            while describe_build_resp["Build"]["Status"] != "READY":
                log_info("waiting for build to be ready\n")
                time.sleep(1)
                describe_build_resp = self.gamelift_client.describe_build(
                    BuildId=build_id)

            try:
                create_fleet_resp = self.gamelift_client.create_fleet(
                    Name=self.backend_config["fleet_name"],
                    BuildId=build_id,
                    ServerLaunchPath=self.backend_config["fleet_launch_path"],
                    EC2InstanceType=self.backend_config["fleet_ec2_instance_type"],
                    FleetType="ON_DEMAND",
                    EC2InboundPermissions=[
                    {
                        'FromPort': 7777,
                        'ToPort': 7777,
                        'Protocol': 'UDP',
                        'IpRange': '0.0.0.0/0'}])
            except self.gamelift_client.exceptions.LimitExceededException as e:
                log_error(e)
                log_error(' * if the limit is the instance types: then try again later; try a different region; or try specifying a different instance type (e.g. use --fleet_ec2_instance_type)')
                log_error(' * if limit is fleet limit: delete the existing fleet.')
        else:
            log_error(f'could not find build: {self.backend_config["build_name"]}')

    def delete_fleet(self):
        fleet_id = self._lookup_fleet_id(self.backend_config["fleet_name"])
        if fleet_id:
            try:
                log_info(f"deleting fleet {fleet_id}")
                self.gamelift_client.delete_fleet(FleetId=fleet_id)
            except ClientError as e:
                log_warn(e)

    def _lookup_user_pool_id(self, pool_name):
        response = self.cognitoidp_client.list_user_pools(MaxResults=60)
        for pool in response["UserPools"]:
            if pool["Name"] == pool_name:
                pool_id = pool["Id"]
                return pool_id
        return None

    def _lookup_user_pool_arn(self,pool_name):
        pool_id = self._lookup_user_pool_id(pool_name)
        response = self.cognitoidp_client.describe_user_pool(UserPoolId=pool_id)
        arn = response["UserPool"]["Arn"]
        return arn

    def _lookup_user_pool_client_id(self, pool_name, client_name):
        pool_id = self._lookup_user_pool_id(pool_name)
        if pool_id:
            response = self.cognitoidp_client.list_user_pool_clients(
                UserPoolId=pool_id,
                MaxResults=60)
            for client in response["UserPoolClients"]:
                if client["ClientName"] == client_name:
                    client_id = client["ClientId"]
                    return client_id
        return None

    def create_user_pool(self):
        log_info("creating cognito user pool")

        if self._lookup_user_pool_id(self.backend_config["user_pool_name"]):
            log_warn("not creating - user pool already exists\n")
            return

        create_user_pool_resp = self.cognitoidp_client.create_user_pool(
            PoolName=self.backend_config["user_pool_name"],
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
        create_user_pool_client_resp = self.cognitoidp_client.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName=self.backend_config["user_pool_login_client_name"],
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
        log_debug(f"create_user_pool_client_resp {create_user_pool_client_resp}")

        update_user_pool_resp = self.cognitoidp_client.update_user_pool(
            UserPoolId=user_pool_id,
            AutoVerifiedAttributes=["email"])
        log_debug(f"update_user_pool_resp {update_user_pool_resp}")

        log_info("creating cognito user pool domain")
        # go to App client settings, setup the callback URLs and hosted UI
        subdomain = self.backend_config["user_pool_subdomain_prefix"]
        create_user_pool_resp = self.cognitoidp_client.create_user_pool_domain(
            Domain=subdomain,
            UserPoolId=user_pool_id)

        log_info("users can create new accounts using the ui at:")
        login_url = f'https://{subdomain}.auth.{self.backend_config["region_name"]}.amazoncognito.com/'
        login_url = login_url + \
            f'login?client_id={create_user_pool_client_resp["UserPoolClient"]["ClientId"]}'
        login_url = login_url + \
            f'&response_type=Token&scope=email+openid&redirect_uri={redirect_uri}'
        log_info(login_url)

        log_info("creating test users")
        for index in range(32):
            user_name = 'user' + str(index)
            self.cognitoidp_client.admin_create_user(
                UserPoolId=user_pool_id,
                Username=user_name,
                UserAttributes=[
                    {"Name": "email", "Value": "test@test.com"}
                ],
                TemporaryPassword="test12",
                MessageAction='SUPPRESS'
            )
            self.cognitoidp_client.admin_set_user_password(
                UserPoolId=user_pool_id,
                Username=user_name,
                Password="test12",
                Permanent=True
            )

    def delete_user_pool(self):
        pool_id = self._lookup_user_pool_id(self.backend_config["user_pool_name"])
        if pool_id:
            response = self.cognitoidp_client.describe_user_pool(UserPoolId=pool_id)
            if "Domain" in response["UserPool"]:
                pool_domain = response["UserPool"]["Domain"]
                log_info(f"deleting pool domain {pool_domain}")
                response = self.cognitoidp_client.delete_user_pool_domain(
                    Domain=pool_domain, UserPoolId=pool_id)
            response = self.cognitoidp_client.delete_user_pool(UserPoolId=pool_id)

    def _lookup_lambda_function_arn(self, lambda_name):
        try:
            get_function_resp = self.lambda_client.get_function(
                FunctionName=lambda_name)
            lambda_arn = get_function_resp["Configuration"]["FunctionArn"]
            return lambda_arn
        except ClientError:
            return None

    def _lookup_role_arn(self, role_name):
        try:
            response = self.iam_client.get_role(RoleName=role_name)
            role_arn = response["Role"]["Arn"]
            return role_arn
        except ClientError:
            return None

    #
    # for details about assume_role_policy, see ref https://hands-on.cloud/working-with-aws-lambda-in-python-using-boto3/
    #
    def _create_lambda_role(
        self,
        role_name,
        assume_role_policy,
        other_policy_name,
        other_policy_json):
        '''returns role_arn of the newly created role'''
        role_arn = self._lookup_role_arn(role_name)
        if role_arn != None:
            log_warn('role already exists arn ' + role_arn)
        else:
            log_debug('role does not exist: creating')
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy))
            role_arn = response["Role"]["Arn"]
            log_debug(response)

        response = self.iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=other_policy_name,
            PolicyDocument=json.dumps(other_policy_json))

        return role_arn

    def _create_lambda_function_from_file(
        self,
        function_name,
        role_arn,
        filename,
        replace_old=None,
        replace_new=None):

        with open(filename, 'r') as inputfile:
            filedata = inputfile.read()

        # apply string substitutions 
        if replace_old:
            filedata = filedata.replace(replace_old, replace_new)

        # to upload, need it to be in zip format
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as tempzip:
            tempzip.writestr('handler.py', filedata)
        zipped_code = zip_buffer.getvalue()

        log_info(f"creating {function_name} lambda")
        success = False
        for create_attempt in range(10):
            try: 
                create_function_response = self.lambda_client.create_function(
                    FunctionName=function_name,
                    Runtime="python3.9",
                    Publish=True,
                    PackageType="Zip",
                    Role=role_arn,
                    Code=dict(ZipFile=zipped_code),
                    Handler="handler.lambda_handler"
                )
                success = True
                log_debug(f"create_function_response {create_function_response}")
                break
            except ClientError as e:
                log_warn(e)
                log_warn(f"create attempt {create_attempt} failed - sometimes InvalidParameterException is returned if the role is too new - sleeping and trying again")
                time.sleep(3)
        if success:
            log_info(f"success after {create_attempt+1} attempts")


    def _create_lambda_roles_and_function(self, 
            role_name, 
            other_policy_name,
            other_policy_json,
            function_name,
            filename,
            replace_old,
            replace_new):

        # setup the role: able to lambda and able to the other policy 
        role_arn = self._create_lambda_role(
            role_name,
            can_execute_lambda_policy_json,
            other_policy_name,
            other_policy_json)

        self._create_lambda_function_from_file(
            function_name,
            role_arn,
            filename,
            replace_old,
            replace_new)

    # create the login and startsession lambdas
    def create_lambdas(self):
        # need the client id to string-replace in the login function 
        cognito_app_client_id = self._lookup_user_pool_client_id(
            self.backend_config["user_pool_name"],
            self.backend_config["user_pool_login_client_name"])

        self._create_lambda_roles_and_function(
            self.backend_config["lambda_login_role_name"],
            self.backend_config["lambda_login_other_policy_name"],
            can_cognito_json,
            self.backend_config["lambda_login_function_name"],
            "GameLiftUnreal-CognitoLogin.py",
            "USER_POOL_APP_CLIENT_ID = ''",
            "USER_POOL_APP_CLIENT_ID = \"" + cognito_app_client_id + "\"")

        # need the fleet id to string-replace in the session function
        fleet_id = self._lookup_fleet_id(self.backend_config["fleet_name"])
        log_debug("got fleet_id" + fleet_id)

        self._create_lambda_roles_and_function(
            self.backend_config["lambda_start_session_role_name"],
            self.backend_config["lambda_start_session_other_policy_name"],
            can_gamelift_session_control_policy_json,
            self.backend_config["lambda_start_session_function_name"],
            "GameLiftUnreal-StartGameLiftSession.py",
            'GAMELIFT_FLEET_ID = ""',
            "GAMELIFT_FLEET_ID = \"" + fleet_id + "\"")

    def _delete_lambda(self, function_name, policy_name, role_name):
        function_arn = self._lookup_lambda_function_arn(function_name)
        if function_arn: 
            self.lambda_client.delete_function(FunctionName=function_name)
        try:
            response = self.iam_client.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
        except ClientError as e:
            log_warn(e)
            pass

        role_arn = self._lookup_role_arn(role_name)
        if role_arn:
            self.iam_client.delete_role(RoleName=role_name)


    def delete_lambdas(self):
        log_info("deleting lambdas")
        self._delete_lambda(
            self.backend_config["lambda_start_session_function_name"],
            self.backend_config["lambda_start_session_other_policy_name"],
            self.backend_config["lambda_start_session_role_name"])
        self._delete_lambda(
            self.backend_config["lambda_login_function_name"],
            self.backend_config["lambda_login_other_policy_name"],
            self.backend_config["lambda_login_role_name"])

    # create the resource for the API gateway and bind it to the corresponding lambda
    def _create_rest_resource(
        self,
        rest_api_id,
        apigateway_client, path_part, http_method,
        account_id, lambda_function_arn,
        authorizer_id):

        # get Root ID
        try:
            response = self.apigateway_client.get_resources(restApiId=rest_api_id)
            root_id = next(item['id']
                        for item in response['items'] if item['path'] == '/')
        except ClientError:
            log_exception(
                "Couldn't get the ID of the root resource of the REST API.")
            raise

        # create the resource under root
        try:
            response = self.apigateway_client.create_resource(
                restApiId=rest_api_id, parentId=root_id, pathPart=path_part)
            resource_id = response['id']
        except ClientError:
            log_exception("Couldn't create pathPart path for %s.", path_part)
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
            self.apigateway_client.put_method(
                restApiId=rest_api_id,
                resourceId=resource_id,
                httpMethod=http_method,
                authorizationType=authorization_type,
                authorizerId=authorizer_id)
        except ClientError:
            log_exception("Couldn't create a method for the base resource.")
            raise

        #
        # Bind the method to the lambda
        #
        lambda_uri = \
            f'arn:aws:apigateway:{self.apigateway_client.meta.region_name}:' \
            f'lambda:path/2015-03-31/functions/{lambda_function_arn}/invocations'
        log_debug(lambda_uri)  
        try:
            # NOTE: You must specify 'POST' for integrationHttpMethod or this will
            # not work.
            self.apigateway_client.put_integration(
                restApiId=rest_api_id,
                resourceId=resource_id,
                httpMethod=http_method,
                type='AWS',
                integrationHttpMethod='POST',
                uri=lambda_uri)
        except ClientError:
            log_exception(
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
            self.lambda_client.add_permission(
                FunctionName=lambda_function_arn,
                StatementId=uuid.uuid4().hex,  # todo do I need to clean these up
                Action='lambda:InvokeFunction', Principal='apigateway.amazonaws.com',
                SourceArn=source_arn)
        except ClientError:
            log_exception(
                "Couldn't add permission to let Amazon API Gateway invoke %s.",
                lambda_function_arn)
            raise

        #
        # Fill out response details
        #
        self.apigateway_client.put_integration_response(
            restApiId=rest_api_id,
            resourceId=resource_id,
            httpMethod=http_method,
            statusCode="200",
            selectionPattern=".*"
        )
    
        self.apigateway_client.put_method_response(
            restApiId=rest_api_id,
            resourceId=resource_id,
            httpMethod=http_method,
            statusCode="200")

    def _create_login_resource(self, rest_api_id, authorizer_id):
        account_id = self.sts_client.get_caller_identity()["Account"]
        lambda_name = self.backend_config["lambda_login_function_name"]
        lambda_arn = self._lookup_lambda_function_arn(lambda_name)

        self._create_rest_resource(
            rest_api_id,
            self.apigateway_client,
            self.backend_config["rest_api_login_path_part"],
            'POST',
            account_id,
            lambda_arn,
            authorizer_id)

    # the gateway resource to invoke the session labmda
    def _create_start_session_resource(self, rest_api_id, authorizer_id):
        account_id = self.sts_client.get_caller_identity()["Account"]
        lambda_name = self.backend_config["lambda_start_session_function_name"]
        lambda_arn = self._lookup_lambda_function_arn(lambda_name)

        self._create_rest_resource(
            rest_api_id,
            self.apigateway_client,
            self.backend_config["rest_api_start_session_path_part"],
            'GET',
            account_id,
            lambda_arn,
            authorizer_id)

    def _lookup_rest_api_id(self, rest_api_name):
        response = self.apigateway_client.get_rest_apis()
        rest_apis = response["items"]
        for rest_api in rest_apis:
            if rest_api_name == rest_api["name"]:
                rest_api_id = rest_api["id"]
                return rest_api_id
        return None

    # create_rest_api: create the api, authorizer and methods
    #
    # ref: https://youtu.be/EfIuC5-wdeo?t=822
    #      Amazon GameLift-UE4 Episode 6: Amazon Cognito and API Gateway
    #        * has some details on configuring lambda invocation using boto3
    #
    def create_rest_api(self):
        if self._lookup_rest_api_id(self.backend_config["rest_api_name"]):
            log_info("not creating rest api because it already exists")
            return

        # create the rest API
        try:
            response = self.apigateway_client.create_rest_api(
                name=self.backend_config["rest_api_name"])
            rest_api_id = response['id']
        except ClientError:
            log_exception(
                f'Could not create REST API {self.backend_config["rest_api_name"]}.')
            raise

        # create the cognito authorizer
        cognito_arn = self._lookup_user_pool_arn(self.backend_config["user_pool_name"])

        # ref: https://youtu.be/EfIuC5-wdeo?t=1012
        create_authorizer_response = self.apigateway_client.create_authorizer(
            restApiId=rest_api_id,
            name=self.backend_config["rest_api_cognito_authorizer_name"],
            type='COGNITO_USER_POOLS',
            providerARNs=[cognito_arn],
            identitySource="method.request.header.Authorization"
        )
        authorizer_id = create_authorizer_response["id"]

        # create the login and start session gateway
        self._create_login_resource(rest_api_id, None)
        self._create_start_session_resource(rest_api_id, authorizer_id)

        # deploy the API to the requested stage name
        try:
            create_deployment_resp = self.apigateway_client.create_deployment(
                restApiId=rest_api_id,
                stageName=self.backend_config["rest_api_stage_name"])
            log_debug(f"create_deployment_resp {create_deployment_resp}")
        except ClientError:
            log_exception("Couldn't deploy REST API %s.", rest_api_id)
            raise

        invoke_url = f'https://{rest_api_id}.execute-api.{self.backend_config["region_name"]}.amazonaws.com/{self.backend_config["rest_api_stage_name"]}'
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

    def delete_rest_api(self):
        log_info("deleting rest_api")
        rest_api_id = self._lookup_rest_api_id(self.backend_config["rest_api_name"])
        while rest_api_id:
            self.apigateway_client.delete_rest_api(restApiId=rest_api_id)
            rest_api_id = self._lookup_rest_api_id(self.backend_config["rest_api_name"])


def process_create_commands(backend, commands):
    while len(commands) > 0:
        command = commands.pop(0)
        if command == "build":
            backend.create_build()
        elif command == "fleet":
            backend.create_fleet()
        elif command == "user_pool":
            backend.create_user_pool()
        elif command == "lambdas":
            backend.create_lambdas()
        elif command == "rest_api":
            backend.create_rest_api()
        else:
            log_warn("urecognized command" + command)


def process_delete_commands(backend, commands):
    while len(commands) > 0:
        command = commands.pop(0)
        if command == "build":
            backend.delete_build()
        elif command == "fleet":
            backend.delete_fleet()
        elif command == "user_pool":
            backend.delete_user_pool()
        elif command == "lambdas":
            backend.delete_lambdas()
        elif command == "rest_api":
            backend.delete_rest_api()
        else:
            log_warn("urecognized command" + command)


def process_backend_config(backend_config):
    if len(backend_config["commands"]) > 0:
        log_info(f'using AWS profile: {backend_config["profile_name"]}')
        a = AwsBackend(backend_config)

        main_command = backend_config["commands"].pop(0)
        sub_commands = backend_config["commands"]

        if len(sub_commands) > 0 and sub_commands[0] == "all":
            sub_commands = [
                "build",
                "fleet",
                "user_pool",
                "lambdas",
                "rest_api"]

        if main_command == "create":
            process_create_commands(a, sub_commands)
        elif main_command == "delete":
            process_delete_commands(a, sub_commands)
        else:
            log_warn(f"unrecognized_command: {main_command}")


class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


def make_backend_config_from_args(argv):
    '''return a backend_config'''

    example_text = '''create examples:
       python aws_backend.py create build
       python aws_backend.py create fleet
       python aws_backend.py create user_pool
       python aws_backend.py create lambdas
       python aws_backend.py create rest_api

delete examples:
       python aws_backend.py delete build
       python aws_backend.py delete all

override default example:
       python aws_backend.py --prefix=potato --build_root=E:/unreal_projects/ue5_gamelift_plugin_test/MyProject/ServerBuild/WindowsServer -- fleet_launch_path=C:/game/MyProject/Binaries/Win64/MyProjectServer.exe --profile=dave --region=us-west-2
       '''

    parser = argparse.ArgumentParser(
        description='Configure AWS Services to provide login, session and server management for dedicated UE servers',
        epilog=example_text,
        formatter_class=Formatter)
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
        help="what kind of EC2s to allocate.  Currently c5.large, c4.large and c3.large qualify for the GameLift free tier")

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
        '--lambda_login_function_name',
        default="[prefix]-lambda-login-function",
        help="name of the login lamda function")
    parser.add_argument(
        '--lambda_login_role_name',
        default="[prefix]-lambda-login-role",
        help="name of the role used by the login lamda")
    parser.add_argument(
        '--lambda_login_other_policy_name',
        default="[prefix]-lambda-login-other-policy-name",
        help="name of specific policies that lets login work (i.e. cognito policies)")

    parser.add_argument(
        '--lambda_start_session_function_name',
        default="[prefix]-lambda-start-session-function",
        help="name of the start-session lambda function")
    parser.add_argument(
        '--lambda_start_session_role_name',
        default="[prefix]-lambda-start-session-role",
        help="name of the role used by the start-session lambda")
    parser.add_argument(
        '--lambda_start_session_other_policy_name',
        default="[prefix]-lambda-start-session-other-policy-name",
        help="name of specific policies that lets start-session work (i.e. gamelift policies)")

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
        '--profile_name',
        default='sean_backend',
        help="AWS credentials to use")
    parser.add_argument('--region_name',
            default='us-west-2',
            help='AWS region')

    args = parser.parse_args(argv)

    backend_config = vars(args)

    # walk through the build config and replace [prefix] with the prefix
    # these final configuration parameters are what is used as the resource
    # names during creation and deletion.
    log_debug("Backend Configuration:")
    prefix = backend_config["prefix"]
    for key, value in backend_config.items():
        if type(value) == str:
            backend_config[key] = value.replace("[prefix]", prefix)
        log_debug(f"    {key}:{backend_config[key]}")

    return backend_config

# ref: https://docs.python.org/3/howto/logging-cookbook.html#logging-to-multiple-destinations 
# python docs on how to send INFO and above to console and DEBUG, INFO and above to logfile 
def setup_logger():
    logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='aws_backend.log',
                    filemode='w')
    # define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)

    # set a format which is simpler for console use
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger('').addHandler(console)



def run_main(argv):
    setup_logger()
    backend_config = make_backend_config_from_args(argv)
    process_backend_config(backend_config)


if __name__ == '__main__':
    run_main(sys.argv[1:])
