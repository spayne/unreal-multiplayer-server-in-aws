# System Design
![System View](/images/system_view.png)

The system includes:
* **UE5 Game Client** with an online map, an offline map and a special offline game mode.  The offline map and game mode logs in and starts a game session using https requests to get the server ip and port from the AWS stack.
* **UE5 Dedicated Game Server** runs with a default game mode that communicates with GameLift.  This server uses the GameLift Server SDK for communications.
* **AWS API Gateway** to process login and start session REST requests from the UE5 client.
* **AWS Lambda** with two functions to process the login and start session requests.
* **AWS Cognito Service** with a user pool to handle registration and authentication of users.
* **AWS GameLift Service** configured with:
   * An uploaded Win64 build of the UE5 server
   * A fleet running that build (default: one on-demand c.5 instance)
* **boto3 script** to create and delete the AWS setup above.

This system is based on Amazon's series [Building Games on AWS: Amazon GameLift & UE4](https://www.youtube.com/playlist?list=PLuGWzrvNze7LEn4db8h3Jl325-asqqgP2).  Differences are captured here: [series_notes.md](series_notes.md).
