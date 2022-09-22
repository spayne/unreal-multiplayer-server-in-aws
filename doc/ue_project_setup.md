We want our UE project to support:
* **Client Targets** to make https requests to the server to login and start the session
* **Server Targets** to be installable by and connect to GameLift on statup

## Steps:
1. **Add the GameLiftServerSDK Plugin.** For your game server to be able to talk to the GameLift servers it needs to link agains the GameLiftServerSDK that is packaged in the plugin: 
   1. Copy the GameLiftServerSDK folder from this repo to the Plugins folder of your game project.
   2. Reopen your project in the Unreal Editor and enable the "GameLiftServerSDK" in the Plugins.
   3. Unreal Editor will prompt you to restart.
   4. If you see a dialog box to ask to rebuild missing modules, select yes.
   5. Once Unreal Editor finishes restarting, look in the Output Log and you will see "LogPluginManager: Mounting Project plugin GameLiftServerSDK"

2. **Add Game Modes and Widget C++ classes.**  Your game needs to be able to support the different logic when offline vs online.  To do this we add a couple game modes and a widget:
   1. Exit Unreal Editor
   2. Copy the OfflineMainMenuWidget, OfflineGameMode and GameModeWithGameLift sources to your game project folder
   3. Add  "GameLiftServerSDK", "Http", "Json", "JsonUtilities" to your project's Build.cs file.  E.g. 
       ```C#
       PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", 
       "HeadMountedDisplay", "UMG", "GameLiftServerSDK","HTTP", "Json", "JsonUtilities"});
       ```
   4. Right click on your uproject and Generate Visual Studio project files
   5. In Visual Studio clean and build the Development Editor | Win64 target
 
3. **Add Server Target: [^ue_setup_dedicated_server]:**
   1. Duplicate the [ProjectName]Target.cs file to create a [ProjectName]ServerTarget.cs
   2. Inside [ProjectName]ServerTarget.cs
       * change the Type from TargetType.Game to TargetType.Server 
       * change the name of the class to match the name of the new file. i.e.:
      
         ![Create Server Target.cs](/images/create_server_target_cs.png)
   3. Right click on your uproject and Generate Visual Studio project files
   4. In Visual Studio build the Development Server | Win64 target

4. **Add Maps and Modes and MainMenuWidget to your project:**
   1. In Unreal Editor, duplicate (ctrl-d) the ThirdPersonMap twice to create an OfflineMap and OnlineMap
   2. In the Offline Map - make it obvious you are in the Offline Map:
      * Select and Delete all the Static Mesh Actors in the "Block00" folders
      * Duplicate the TextRenderActor
         * position it so it is visible in the scene from the player camera
         * set the text value to "Offline Map"
   3. In Project Settings|Maps and Modes, set the values to:
   
      | Setting | Value |
      | --- | --- |
      | Default GameMode | OfflineGameMode |
      | Global Default Server Game Mode | GameModeWithGameLift |
      | Editor Startup Map | OfflineMap |
      | Game Default Map | OfflineMap |
      | Server Default Map | OnlineMap |
      
   4. In Project Settings|Packaging|Advanced, add to the List of maps to include in a packaged build
      | Setting | Value |
      | --- | --- |
      | Index[0] | OfflineMap |
      | Index[1] | OnlineMap |

4. **Build the Server Image**
   1. In Unreal Editor, choose Platforms/Windows and check that the Build Target is the Server
   2. Then choose Platforms/Windows/Package Project to package into a ServerBuild directory
   3. Create a shortcut to the built Server to include a -log on the command line
   4. Duplicate that shorcut to create one called called NoGameLift with -log and -NoGameLift on the command line
   5. Use the NoGameLift shortcut to start the server and confirm that you see that it is listening on a port.   e.g.
      ![Listening](images/dedicated_server_is_listening.png)
   6. Start a client in Unreal Editor and use the ~, open 127.0.0.1 command.  Verify that the map in the client view changes from the Offline map to the Online map.

5. **Add Main Menu to the Offline Map**
   1. Create an empty widget blueprint called WBP_OfflineMainMenu.  
   * UE will ask for the root widget:  use **OfflineMainMenuWidget** as the root widget
   3. In the Offline Map, edit the level blueprint to add two nodes onto BeginPlay to create the widget and add it to the viewport:
      ![Add Widget to Viewport](images/create_menu_and_add_to_viewport.png)
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
      ![On Login to GameLift clicked](images/on_clicked_game_lift_login.png)
   8. Add an On Clicked Event to the Login to Localhost button and connect it to an "open" console command:
      ![On Login to localhost clicked](images/on_clicked_localhost_login.png)
   9. In the BP_FirstPersonCharacter set the input mode to Game And UI.  This is to make testing multiple instances easier:
      ![input mode](images/bp_third_person_character_input_mode.png)
   

6. **Test the UE setup**
   1. Rebuild the server package to ensure you are in sync
   2. Start the NoGameLift server
   3. Start some number of 'Standalone' clients
   4. Verify that you can use the LoginToLocalHost to put them into multiplayer

7. **Create the install script and package**
   1. create an install.bat from these sources to your server build folder:
      * ```Engine\Extras\Redist\en-us\UEPrereqSetup_x64.exe /install/quiet/norestart /log c:\game\UEPrereqSetup.log```
   2. That's it.   Because we aren't using the S3 method to upload, this doesn't need to be put into a .zip file
