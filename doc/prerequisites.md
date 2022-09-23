## Prerequisites
Ensure you have:
* UE5 on Win64 build from source.  To build dedicated servers, you must be building against an engine built from source and not from the Epic Launcher. [^ue_server_req]
    ![Source build warning](/images/source_build_warning.png)
* C++ project with a similar structure to the Third Person game template.
* An AWS account setup and can run the AWS cli.

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
