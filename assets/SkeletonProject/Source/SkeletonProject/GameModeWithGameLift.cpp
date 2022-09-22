// Copyright Epic Games, Inc. All Rights Reserved.

#include "GameModeWithGameLift.h"
//#include "MyProjectCharacter.h"
#include "UObject/ConstructorHelpers.h"

#if defined(WITH_GAMELIFT)
#include "GameLiftServerSDK.h"
#endif

DEFINE_LOG_CATEGORY(LogGameLift);

AGameModeWithGameLift::AGameModeWithGameLift()
{
	// set default pawn class to our Blueprinted character
    // sean: Note that this path changed in UE5
	static ConstructorHelpers::FClassFinder<APawn> PlayerPawnBPClass(TEXT("/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter"));
	if (PlayerPawnBPClass.Class != NULL)
	{
		DefaultPawnClass = PlayerPawnBPClass.Class;
	}

#if defined(WITH_GAMELIFT)
    //Let's run this code only if GAMELIFT is enabled. Only with Server targets!
    if (!FParse::Param(FCommandLine::Get(), TEXT("NoGameLift")))
    {
        UE_LOG(LogGameLift, Warning, TEXT("Starting GameLift"));
        SetupGameLift();
    }
    else
    {
        UE_LOG(LogGameLift, Warning, TEXT("Skipping GameLift because of command line"));
    }
#endif
}

//
// The game server will setup some callbacks and tell Gamelift that it's ready
//
void AGameModeWithGameLift::SetupGameLift()
{
#if defined(WITH_GAMELIFT)
    //Getting the module first.
    FGameLiftServerSDKModule* gameLiftSdkModule = &FModuleManager::LoadModuleChecked<FGameLiftServerSDKModule>(FName("GameLiftServerSDK"));

    //InitSDK establishes a local connection with GameLift's agent to enable communication.
    gameLiftSdkModule->InitSDK();

    //Respond to new game session activation request. GameLift sends activation request 
    //to the game server along with a game session object containing game properties 
    //and other settings. Once the game server is ready to receive player connections, 
    //invoke GameLiftServerAPI.ActivateGameSession()
    auto onGameSession = [=](Aws::GameLift::Server::Model::GameSession gameSession)
    {
        gameLiftSdkModule->ActivateGameSession();
    };

    FProcessParameters* params = new FProcessParameters();
    params->OnStartGameSession.BindLambda(onGameSession);

    //OnProcessTerminate callback. GameLift invokes this before shutting down the instance 
    //that is hosting this game server to give it time to gracefully shut down on its own. 
    //In this example, we simply tell GameLift we are indeed going to shut down.
    params->OnTerminate.BindLambda([=]() {gameLiftSdkModule->ProcessEnding(); });

    //HealthCheck callback. GameLift invokes this callback about every 60 seconds. By default, 
    //GameLift API automatically responds 'true'. A game can optionally perform checks on 
    //dependencies and such and report status based on this info. If no response is received  
    //within 60 seconds, health status is recorded as 'false'. 
    //In this example, we're always healthy!
    params->OnHealthCheck.BindLambda([]() {return true; });

    //Here, the game server tells GameLift what port it is listening on for incoming player 
    //connections. In this example, the port is hardcoded for simplicity. Since active game
    //that are on the same instance must have unique ports, you may want to assign port values
    //from a range, such as:
    //const int32 port = FURL::UrlConfig.DefaultPort;
    //params->port;
    params->port = 7777;

    //Here, the game server tells GameLift what set of files to upload when the game session 
    //ends. GameLift uploads everything specified here for the developers to fetch later.
    TArray<FString> logfiles;
    logfiles.Add(TEXT("aLogFile.txt"));
    params->logParameters = logfiles;

    //Call ProcessReady to tell GameLift this game server is ready to receive game sessions!
    gameLiftSdkModule->ProcessReady(*params);
#endif
}
