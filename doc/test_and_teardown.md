## Testing both together.
1. **Test one player in GameLift**
   1. Open the Unreal project
   2. Open OfflineMainMenuWidget.cpp and change ApiGatewayEndpoing to use invoke_url from before.  If you need to find it again, use the Amazon API Gateway console and look at Stages/[prefix]-api-test-stage to get it.
   3. Rebuild the Development Editor | Win64 target and test in the client (use Ctrl+Alt+F11 if you have the UE editor up)
   4. Use play in editor and set number of players to 1.
   5. Press Login to GameLift and verify you are now in the Online Map
   6. Using the GameLift console, verify a game session was created and a player is currently in the game session.
      ![player_session_was_created](images/player_session_was_created.png)

## Teardown
1. **Teardown the service**
   1. To tear down the service use the aws_setup command line and use the command **delete all**
   2. Use the AWS console to verify the resources were deleted
