## How to deploy Unreal Engine multiplayer servers using AWS GameLift

This project provides [instructions](#instructions), supporting [tools](tools) and [assets](assets) to take to your Unreal Engine 5 project and deploy it to the AWS GameLift service.  If you are interested in an integrated GUI, checkout the [GameLiftStarterPlugin](https://github.com/spayne/GameLiftStarterPlugin).

**Tested Configuration:** Unreal Engine 5.0.3 and GameLift Server SDK Release 4.0.2.

The design and steps are based on the AWS video series [Building Games on AWS: Amazon GameLift & UE4](https://www.youtube.com/playlist?list=PLuGWzrvNze7LEn4db8h3Jl325-asqqgP2). This project adds written instructions and a boto3 tool to automate the AWS configuration - so is easier to iterate on.  Episode notes and bookmarks for the video series are on the [Video Series Notes](doc/video_series_notes.md) page.

The intended audience is Unreal Engine developers who are just getting started, have looked at the SDK documentation and reviewed video series above and are wanting to add AWS GameLift into their project.

## Instructions

Follow the instructions on each of the sub-pages:
1. [Review the system design for a view of the scope, components and their responsibilities](doc/system_design.md)
2. [Ensure you have the prerequisites](doc/prerequisites.md)
3. [Build a UE Project with Client and Server Targets](doc/ue_project_setup.md)
4. [Setup the AWS Backend](doc/aws_backend_setup.md)
5. [Test and Teardown](doc/test_and_teardown.md)


## Contact
sean.d.payne@gmail.com

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


