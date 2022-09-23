The following steps will show you how to get your UE project such that:
* **Client Targets** to make https requests to the server to login and start the session
* **Server Targets** to be installable by and connect to GameLift on statup

Note that since the initial steps require project level changes, you will be needing to restart the Unreal Editor a few times.

**Troubleshooting** If you see an error message when loading your project in Unreal Editor about CDO Constructors failing to find the ThirdPersonCharacter, this may be because your project is not based on the Third Person Template.  You can either fix the dependency in the C++ game modes or you could import the Third Person Template into your project.  To import the Third Person Template, (press OK on the error messsage dialog), right click in the Content Browser and choose "Add Feature or Content Pack...", select Third Person and press "Add to Project"

## Steps:
1. **Add the GameLiftServerSDK Plugin.** For your game server to be able to talk to the GameLift servers it needs to link against the GameLiftServerSDK that is packaged in the plugin: 
   1. Copy the Plugins folder from assets/SkeletonProject from this repo to the Plugins folder of your game project.  The Plugins folder should be at the same level as your [ProjectName].sln
   2. Reopen your project in the Unreal Editor, Open Edit/Plugins and enable the "GameLiftServerSDK".
   3. Unreal Editor will prompt you to restart.
   4. If you see a dialog box to ask to rebuild missing modules, select Yes.
   5. In a few seconds Unreal Editor will finished restarting, you should now see in the Plugins Window that the GameLiftServerSDK is marked as enabled.

2. **Add Game Modes and Widget C++ classes.**  Your game needs to be able to support the different logic when offline vs online.  To do this we add a couple game modes and a widget:
   1. Exit Unreal Editor
   2. Copy the the contents of the SkeletonProject/Source/SkeletonProject to your [ProjectName]/Source/[ProjectName] folder.  You should now have  OfflineMainMenuWidget, OfflineGameMode and GameModeWithGameLift sources at the same level as your [ProjectName].Build.cs file.
   3. Open your [ProjectName].Build.cs file and add "UMG" "GameLiftServerSDK", "Http", "Json", "JsonUtilities" to your PublicDependencyNames.  E.g. 
       ```C#
       PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", 
       "HeadMountedDisplay", "UMG", "GameLiftServerSDK","HTTP", "Json", "JsonUtilities"});
       ```
   4. Right click on your [ProjectName].uproject and select Generate Visual Studio project files
   5. In Visual Studio, rebuild the Development Editor | Win64 target for your game. It should build without error.
 
3. **Add Server Target: [^ue_setup_dedicated_server]:**
   1. In Visual Studio, Select the Source/[ProjectName].Target.cs.  Right click on the tab and Open Containing Folder.
   2. Using Windows Explorer, duplicate the [ProjectName].Target.cs file and rename it to [ProjectName]Server.Target.cs
   3. Using a text editor (don't try regenerating until the next step), edit the [ProjectName].ServerTarget.cs:
       * change the Type from TargetType.Game to TargetType.Server 
       * change the name of the class to match the name of the new file. i.e.:
      
         ![Create Server Target.cs](/images/create_server_target_cs.png)
   3. Right click on your [ProjectName].uproject and select Generate Visual Studio project files
   4. In Visual Studio build and run the Development Server | Win64 target
   5. Check that when you open Platforms/Windows/Build Target you can now see the new server target:
      ![new server target](/images/new_server_target.png)

4. **Add Maps and Modes and MainMenuWidget to your project:**
   1. In Unreal Editor, navigate to the Maps folder in the Content Browser and duplicate (ctrl-d) the ThirdPersonMap twice to create an OfflineMap and OnlineMap
   2. In the Offline Map - make it obvious you are in the Offline Map:
      * Select and Delete all the Static Mesh Actors in the "Block00" folders
      * Duplicate the TextRenderActor
         * position it so it is visible in the scene from the player camera
         * set the text value to "Offline Map"
   3. (optional) In the Online Map you can modify it if you like.
   4. In Project Settings|Maps and Modes, set the values to:
   
      | Setting | Value |
      | --- | --- |
      | Default GameMode | OfflineGameMode |
      | Global Default Server Game Mode | GameModeWithGameLift |
      | Editor Startup Map | OfflineMap |
      | Game Default Map | OfflineMap |
      | Server Default Map | OnlineMap |
      
   5. In Project Settings|Packaging|Advanced, use the '...' to add  the List of maps to include in a packaged build
      | Setting | Value |
      | --- | --- |
      | Index[0] | OfflineMap |
      | Index[1] | OnlineMap |
      
      **Troubleshooting**: If you see an error about paths being too long, check that Windows Explorer is showing and you are choosing maps from your project directory.

4. **Build the Server Image**
   1. Copy the ServerBuild folder from assets/SkeletonProject to your project folder
   2. In Unreal Editor, choose Platforms/Windows and check that the Build Target is the Server
   3. Then choose Platforms/Windows/Package Project.  In the dialog that pops up, choose the ServerBuild directory.
   4. Check the log to verify the build was successful.

      **Troubleshooting**: Note that you must be using an engine that was built from source to do a server build.  So if the Unreal Engine you are using was downloaded from the Epic Launcher this will not work.  Build an engine from source, then right click on your [ProjectName].uproject and choose the source build of Unreal Engine.
      ![select_unreal_engine_built_from_source](/images/select_unreal_engine_built_from_source.png)
      
   6. Assuming you now have a successful build, open the ServerBuild/WindowsServer directory to create a shortcut to the built Server to include a -log on the command line
   7. Duplicate that shorcut to create a second shortcut and name it NoGameLift.  In it's Properties specify -log and -NoGameLift for it's the Target.  So you should have the following kind of setup in your WindowsServer directory:
     ![shortcuts](/images/windows_server_directory_with_shortcuts.png)
   9. Because we don't have the backend setup yet, use the NoGameLift shortcut to start the server and confirm that you see that it is listening on a port.   e.g.
      ![Listening](/images/dedicated_server_is_listening.png)
   9. Start a client in Unreal Editor and use the ~, open 127.0.0.1 command.  Verify that the map in the client view changes from the Offline map to the Online map.
         **Troubleshooting**: If the map doesn't change, try pressing the carriage return in the server log in case it is in scrolled suspend.

5. **Add Main Menu to the Offline Map**
   1. Create an empty widget blueprint called WBP_OfflineMainMenu.  
   * UE will ask for the root widget:  use **OfflineMainMenuWidget** as the root widget
   3. In the Offline Map, edit the level blueprint to add two nodes onto BeginPlay to create the widget and add it to the viewport:
      ![Add Widget to Viewport](/images/create_menu_and_add_to_viewport.png)
   3. Create a Hierarchy with Canvas Panel; VerticalBox; TextBlock; UsernameEditableText; TextBlock; GameLiftLoginButton; LocalLoginButton
   4. Set the Vertical Box anchor point to the bottom right and set Position X to -250 and Position Y to -250
   5. Update the labels to read Username, Password.  Add Text children to the buttons to read "Login To GameLift" and "Login to Localhost"
   6. Tweak layout
      | Setting | Value |
      | --- | --- |
      |Vertical Box Position| -320, -360
      |Vertical Box Size|300
      |Font Size|24
      |Add 20 top and bottom padding to text input fields|
      |Username|user0|
      |Password|pass12|
   7. Add an On Clicked Event to the Login to GameLift button.  In the event graph read from editable text to Set "User" and Set "Pass" and then execute OnLoginClicked:
      ![On Login to GameLift clicked](/images/on_clicked_game_lift_login.png)
   8. Add an On Clicked Event to the Login to Localhost button and connect it to an "open" console command:
      ![On Login to localhost clicked](/images/on_clicked_localhost_login.png)
   9. In the BP_FirstPersonCharacter set the input mode to Game And UI.  This is to make testing multiple instances easier:
      ![input mode](/images/bp_third_person_character_input_mode.png)
   

6. **Test the UE setup**
   1. Rebuild the server package to ensure you are in sync
   2. Start the NoGameLift server
   3. Start some number of 'Standalone' clients
   4. Verify that you can use the LoginToLocalHost to put them into multiplayer

7. **Create the install script and package**
   1. create an install.bat from these sources to your server build folder:
      * ```Engine\Extras\Redist\en-us\UEPrereqSetup_x64.exe /install/quiet/norestart /log c:\game\UEPrereqSetup.log```
   2. That's it.   Because we aren't using the S3 method to upload, this doesn't need to be put into a .zip file


[^ue_server_req]: https://docs.unrealengine.com/5.0/en-US/setting-up-dedicated-servers-in-unreal-engine/#1.requiredsetup
[^ue_setup_dedicated_server]: [Unreal Engine 5.0 Documentation: Setting Up Dedicated Servers](https://docs.unrealengine.com/5.0/en-US/setting-up-dedicated-servers-in-unreal-engine/)
[^aws_gamelift_episode_1]: [Amazon GameLift-UE4 Episode 1: Intro and Architecture Review](https://youtu.be/3_iBuko39JA)
[^aws_gamelift_episode_2]: [Amazon GameLift-UE4 Episode 2: UE4 Dedicated Server](https://youtu.be/cUcTJjqSCos)
[^aws_gamelift_episode_3]: [Amazon GameLift-UE4 Episode 3: Integrate GameLiftServer SDK with UE4](https://youtu.be/Sl_i6YIgQqg)
[^aws_gamelift_episode_4]: [Amazon GameLift-UE4 Episode 4: Testing and Uploading Server Build to GameLift](https://youtu.be/Q6kOpObWsUI)
[^aws_gamelift_episode_5]: [Amazon GameLift-UE4 Episode 5: StartGameLiftSession](https://youtu.be/\_EynplPECNk)
[^aws_gamelift_episode_6]: [Amazon GameLift-UE4 Episode 6: Amazon Cognito and API Gateway](https://youtu.be/EfIuC5-wdeo)
[^aws_gamelift_episode_7]: [Amazon GameLift-UE4 Episode 7: API Requests from the Game Client](https://youtu.be/lhABExDSpHE)
[^aws_gamelift_episode_8]: [Amazon GameLift-UE4 Episode 8: Next Steps](https://youtu.be/lwYFZFYvSgE)
